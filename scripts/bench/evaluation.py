"""Cœur du harnais d'évaluation Exact Number Accuracy (story 5.2).

Rejoue **le même** pipeline que l'API (via ``app.pipeline.recognition``) sur
chaque entrée du manifest 5.1, puis agrège :

- **Exact Number Accuracy** (métrique de décision, *pas* le WER) — global et
  ventilé par ``condition`` / tag (``short``/``long``/``confusion``) / ``split`` ;
- **matrice de confusions** des nombres, paires proches marquées via
  ``asr_confusions`` (helper public, jamais de fuzzy matching) ;
- **taux** de rejet / fausse acceptation / confirmation / acceptation correcte ;
- **latence ASR** (mêmes agrégats que l'endpoint ``/metrics``).

Source ASR **interchangeable** (NFR9) : un ``SpeechRecognizer`` obtenu par
configuration, ou un **rejeu** d'hypothèses pré-calculées (JSONL) — aucun modèle
n'est appelé en dur, aucun GPU requis pour un rejeu.

Story 6.1 — **Exact Expression Accuracy**
-----------------------------------------

Quand le manifest porte des expressions, une entrée n'est comptée juste que si
**l'opération entière** l'est : les deux opérandes *et* l'opérateur *et* le
résultat (reste de division compris). Reconnaître « 23 » dans « 23 + 15 » ne
vaut rien pour l'utilisateur — d'où une métrique tout-ou-rien, ventilée par
opérateur et par longueur d'opérandes.

Les entrées volontairement **hors domaine** (résultat négatif, dépassement) ne
sont pas des échecs : la bonne réponse y est un **refus**, avec le bon code. Le
taux de refus correct est donc mesuré à part, et c'est lui qui atteste que
« jamais de résultat inventé » (FR21/NFR14) tient sur le terrain.
"""

from __future__ import annotations

import json
import os
import wave
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import zarma_numbers
from app.api.v1.metrics import _summarize_latency
from app.asr.base import AsrResult, AudioInput, Candidate, SpeechRecognizer
from app.config import Settings
from app.pipeline.confidence import is_known_asr_confusion
from app.pipeline.recognition import run_recognition_pipeline
from benchmark_corpus import (
    ManifestEntry,
    classify,
    confusable_forms,
    parse_expression_spec,
)
from zarma_numbers import Lexicon

#: Version du harnais (métadonnée de reproductibilité, NFR12).
#: 6.1.0 — ajout de l'Exact Expression Accuracy et du taux de refus correct.
HARNESS_VERSION = "6.1.0"

#: Frontière courts/longs pour les opérandes (même seuil que le corpus 5.1).
SHORT_OPERAND_MAX_EXCLUSIVE = 100

#: Une source ASR mappe une entrée de manifest vers un ``AsrResult``.
AsrSource = Callable[[ManifestEntry], AsrResult]


class EvaluationError(Exception):
    """Erreur contrôlée du harnais (fail-closed)."""


@dataclass(frozen=True, slots=True)
class EntryEvaluation:
    audio_path: str
    expected_number: int | None
    recognized_number: int | None
    decision: str
    condition: str
    split: str
    tags: frozenset[str]
    correct: bool
    latency_ms: int
    model_version: str
    #: Spécification attendue (``"23+15"``) — ``None`` pour un « nombre seul ».
    expected_expression: str | None = None
    #: Spécification effectivement reconnue, ``None`` si aucune.
    recognized_expression: str | None = None
    #: Code de refus attendu (entrée volontairement hors domaine).
    expected_refusal: str | None = None
    #: Code de refus effectivement produit.
    recognized_refusal: str | None = None

    @property
    def is_expression(self) -> bool:
        return self.expected_expression is not None

    @property
    def expects_refusal(self) -> bool:
        return self.expected_refusal is not None


@dataclass(frozen=True, slots=True)
class GroupAccuracy:
    total: int
    correct: int

    @property
    def accuracy(self) -> float:
        return round(self.correct / self.total, 4) if self.total else 0.0


@dataclass(frozen=True, slots=True)
class ConfusionPair:
    expected_number: int
    predicted_number: int | None
    count: int
    close: bool


@dataclass(frozen=True, slots=True)
class DecisionRates:
    total: int
    counts: dict[str, int]
    rejection_rate: float
    false_acceptance_rate: float
    confirmation_rate: float
    correct_acceptance_rate: float


@dataclass(frozen=True, slots=True)
class RefusalRates:
    """Comportement du système sur les entrées volontairement hors domaine.

    ``correct`` = a refusé **avec le bon code**. ``wrong_code`` = a refusé, mais
    en invoquant autre chose. ``answered`` = a produit un résultat là où il n'en
    existe pas : c'est le seul cas réellement grave (FR21).
    """

    total: int
    correct: int
    wrong_code: int
    answered: int

    @property
    def correct_rate(self) -> float:
        return round(self.correct / self.total, 4) if self.total else 0.0

    @property
    def invented_rate(self) -> float:
        return round(self.answered / self.total, 4) if self.total else 0.0


@dataclass(slots=True)
class EvaluationResult:
    total: int
    correct: int
    by_condition: dict[str, GroupAccuracy]
    by_tag: dict[str, GroupAccuracy]
    by_split: dict[str, GroupAccuracy]
    decision_rates: DecisionRates
    latency: dict[str, object]
    confusion_pairs: list[ConfusionPair]
    model_versions: list[str]
    entries: list[EntryEvaluation] = field(default_factory=list)
    #: Ventilations propres aux expressions (vides sur un corpus « nombres »).
    by_operator: dict[str, GroupAccuracy] = field(default_factory=dict)
    by_operand_length: dict[str, GroupAccuracy] = field(default_factory=dict)
    expression_total: int = 0
    expression_correct: int = 0
    refusals: RefusalRates = field(
        default_factory=lambda: RefusalRates(total=0, correct=0, wrong_code=0, answered=0)
    )

    @property
    def accuracy(self) -> float:
        return round(self.correct / self.total, 4) if self.total else 0.0

    @property
    def exact_expression_accuracy(self) -> float:
        """Part d'opérations **entièrement** justes (opérandes, opérateur, résultat)."""
        if not self.expression_total:
            return 0.0
        return round(self.expression_correct / self.expression_total, 4)


# --------------------------------------------------------------------------- #
# Sources ASR (interface uniquement, jamais un modèle en dur)
# --------------------------------------------------------------------------- #


def asr_result_to_dict(audio_path: str, result: AsrResult) -> dict[str, object]:
    """Sérialise un ``AsrResult`` pour un dump d'hypothèses réutilisable en rejeu."""

    return {
        "audio_path": audio_path,
        "text": result.text,
        "acoustic_score": result.acoustic_score,
        "candidates": [
            {"text": c.text, "score": c.score, "number": c.number} for c in result.candidates
        ],
        "latency_ms": result.latency_ms,
        "model_version": result.model_version,
    }


def _asr_result_from_dict(row: dict) -> AsrResult:
    return AsrResult(
        text=row["text"],
        acoustic_score=row["acoustic_score"],
        candidates=[
            Candidate(text=c["text"], score=c["score"], number=c.get("number"))
            for c in row.get("candidates", [])
        ],
        latency_ms=row["latency_ms"],
        model_version=row["model_version"],
    )


def load_hypotheses(path: Path) -> dict[str, AsrResult]:
    """Charge un JSONL d'hypothèses ASR indexé par ``audio_path`` (mode rejeu)."""

    hypotheses: dict[str, AsrResult] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        hypotheses[row["audio_path"]] = _asr_result_from_dict(row)
    return hypotheses


def replay_source(hypotheses: dict[str, AsrResult]) -> AsrSource:
    """Source de rejeu : renvoie l'hypothèse enregistrée pour chaque ``audio_path``."""

    def source(entry: ManifestEntry) -> AsrResult:
        try:
            return hypotheses[entry.audio_path]
        except KeyError as exc:
            raise EvaluationError(f"missing_hypothesis:{entry.audio_path}") from exc

    return source


def recognizer_source(recognizer: SpeechRecognizer, audio_root: Path) -> AsrSource:
    """Source live : lit le WAV canonique et appelle ``recognizer.transcribe`` (NFR9)."""

    def source(entry: ManifestEntry) -> AsrResult:
        path = audio_root / entry.audio_path
        if not path.is_file():
            raise EvaluationError(f"audio_missing:{entry.audio_path}")
        try:
            with wave.open(str(path), "rb") as reader:
                pcm = reader.readframes(reader.getnframes())
        except (wave.Error, OSError, EOFError) as exc:
            raise EvaluationError(f"audio_unreadable:{entry.audio_path}") from exc
        return recognizer.transcribe(AudioInput(data=pcm, format="pcm_s16le"))

    return source


class CapturingSource:
    """Enveloppe une source pour capturer les ``AsrResult`` (dump d'hypothèses)."""

    def __init__(self, inner: AsrSource) -> None:
        self._inner = inner
        self.captured: dict[str, AsrResult] = {}

    def __call__(self, entry: ManifestEntry) -> AsrResult:
        result = self._inner(entry)
        self.captured[entry.audio_path] = result
        return result


# --------------------------------------------------------------------------- #
# Évaluation
# --------------------------------------------------------------------------- #


def _group_accuracy(pairs: Sequence[tuple[str, bool]]) -> dict[str, GroupAccuracy]:
    totals: Counter[str] = Counter()
    corrects: Counter[str] = Counter()
    for key, correct in pairs:
        totals[key] += 1
        if correct:
            corrects[key] += 1
    return {key: GroupAccuracy(total=totals[key], correct=corrects[key]) for key in sorted(totals)}


def _decision_rates(entries: Sequence[EntryEvaluation]) -> DecisionRates:
    total = len(entries)
    counts = Counter(entry.decision for entry in entries)
    repeat = counts.get("repeat", 0)
    confirm = counts.get("confirm", 0)
    false_accept = sum(1 for e in entries if e.decision == "accept" and not e.correct)
    correct_accept = sum(1 for e in entries if e.decision == "accept" and e.correct)

    def ratio(n: int) -> float:
        return round(n / total, 4) if total else 0.0

    return DecisionRates(
        total=total,
        counts={name: counts.get(name, 0) for name in ("accept", "confirm", "repeat")},
        rejection_rate=ratio(repeat),
        false_acceptance_rate=ratio(false_accept),
        confirmation_rate=ratio(confirm),
        correct_acceptance_rate=ratio(correct_accept),
    )


def _refusal_rates(entries: Sequence[EntryEvaluation]) -> RefusalRates:
    """Agrège le comportement sur les entrées attendues hors domaine."""
    expected = [entry for entry in entries if entry.expects_refusal]
    correct = sum(1 for e in expected if e.recognized_refusal == e.expected_refusal)
    answered = sum(1 for e in expected if e.recognized_number is not None)
    wrong_code = sum(
        1
        for e in expected
        if e.recognized_refusal is not None and e.recognized_refusal != e.expected_refusal
    )
    return RefusalRates(
        total=len(expected), correct=correct, wrong_code=wrong_code, answered=answered
    )


def _confusion_pairs(
    entries: Sequence[EntryEvaluation],
    lexicon: Lexicon,
    top_n: int,
) -> list[ConfusionPair]:
    counter: Counter[tuple[int, int | None]] = Counter()
    for entry in entries:
        # Les entrées sans nombre attendu (refus) n'ont pas de « confusion de
        # nombres » à documenter : elles sont couvertes par ``RefusalRates``.
        if entry.expected_number is None:
            continue
        if entry.recognized_number != entry.expected_number:
            counter[(entry.expected_number, entry.recognized_number)] += 1

    confusions = lexicon.asr_confusions
    pairs: list[ConfusionPair] = []
    for (expected, predicted), count in counter.items():
        close = False
        if predicted is not None:
            close = is_known_asr_confusion(
                zarma_numbers.generate(expected),
                zarma_numbers.generate(predicted),
                confusions,
            )
        pairs.append(
            ConfusionPair(
                expected_number=expected,
                predicted_number=predicted,
                count=count,
                close=close,
            )
        )

    # Tri stable : fréquence décroissante, puis expected, puis predicted (None en dernier).
    def _key(p: ConfusionPair) -> tuple[int, int, bool, int]:
        return (-p.count, p.expected_number, p.predicted_number is None, p.predicted_number or -1)

    pairs.sort(key=_key)
    return pairs[:top_n]


def _expression_spec(expression: zarma_numbers.Expression) -> str:
    """Spécification canonique d'une opération (``"23+15"``) — comparable telle quelle."""
    return f"{expression.left}{expression.symbol}{expression.right}"


def _operand_length_tag(entry: ManifestEntry) -> str:
    """``short`` / ``long`` d'après l'opérande le plus grand de l'expression."""
    expression = parse_expression_spec(entry.expected_expression or "")
    largest = max(expression.left, expression.right)
    return "short" if largest < SHORT_OPERAND_MAX_EXCLUSIVE else "long"


def _evaluate_expression_entry(
    entry: ManifestEntry, outcome, asr_result: AsrResult
) -> EntryEvaluation:
    """Vérité tout-ou-rien : l'opération **entière** est-elle juste ?

    Reconnaître un seul opérande ne vaut rien pour l'utilisateur : opérandes,
    opérateur, résultat et reste doivent tous correspondre. Sur une entrée
    attendue hors domaine, la bonne réponse est au contraire le **bon code de
    refus** — produire un nombre y est l'échec le plus grave.
    """
    recognized_spec = (
        _expression_spec(outcome.expression) if outcome.expression is not None else None
    )
    result = outcome.expression_result

    if entry.expected_refusal is not None:
        correct = (
            recognized_spec == entry.expected_expression
            and outcome.refusal_code == entry.expected_refusal
        )
    else:
        correct = (
            recognized_spec == entry.expected_expression
            and result is not None
            and result.value == entry.expected_number
            and result.remainder == entry.expected_remainder
        )

    expression = parse_expression_spec(entry.expected_expression or "")
    tags = {
        "expression",
        f"operator:{expression.operator_name}",
        _operand_length_tag(entry),
    }
    if entry.expected_refusal is not None:
        tags.add("out_of_domain")
    if entry.expected_remainder:
        tags.add("remainder")

    return EntryEvaluation(
        audio_path=entry.audio_path,
        expected_number=entry.expected_number,
        recognized_number=result.value if result is not None else None,
        decision=outcome.decision,
        condition=entry.condition,
        split=entry.split,
        tags=frozenset(tags),
        correct=correct,
        latency_ms=asr_result.latency_ms,
        model_version=asr_result.model_version,
        expected_expression=entry.expected_expression,
        recognized_expression=recognized_spec,
        expected_refusal=entry.expected_refusal,
        recognized_refusal=outcome.refusal_code,
    )


def evaluate(
    entries: Sequence[ManifestEntry],
    asr_source: AsrSource,
    settings: Settings,
    *,
    lexicon: Lexicon | None = None,
    top_confusions: int = 20,
) -> EvaluationResult:
    """Exécute le pipeline complet sur chaque entrée et agrège les métriques."""

    lex = lexicon or zarma_numbers.load_lexicon()
    confusables = confusable_forms(lex)

    evaluations: list[EntryEvaluation] = []
    for entry in entries:
        asr_result = asr_source(entry)
        outcome = run_recognition_pipeline(asr_result, settings)
        if entry.is_expression:
            evaluations.append(_evaluate_expression_entry(entry, outcome, asr_result))
            continue
        tags = classify(entry.expected_number, entry.expected_prompt, confusables)
        evaluations.append(
            EntryEvaluation(
                audio_path=entry.audio_path,
                expected_number=entry.expected_number,
                recognized_number=outcome.number,
                decision=outcome.decision,
                condition=entry.condition,
                split=entry.split,
                tags=tags,
                correct=outcome.number == entry.expected_number,
                latency_ms=asr_result.latency_ms,
                model_version=asr_result.model_version,
            )
        )

    correct = sum(1 for e in evaluations if e.correct)
    by_tag = _group_accuracy([(tag, e.correct) for e in evaluations for tag in sorted(e.tags)])
    latency = _summarize_latency([e.latency_ms for e in evaluations]).model_dump()

    expressions = [e for e in evaluations if e.is_expression]
    by_operator = _group_accuracy(
        [
            (tag.removeprefix("operator:"), e.correct)
            for e in expressions
            for tag in sorted(e.tags)
            if tag.startswith("operator:")
        ]
    )
    by_operand_length = _group_accuracy(
        [
            (tag, e.correct)
            for e in expressions
            for tag in sorted(e.tags)
            if tag in {"short", "long"}
        ]
    )

    return EvaluationResult(
        total=len(evaluations),
        correct=correct,
        by_condition=_group_accuracy([(e.condition, e.correct) for e in evaluations]),
        by_tag=by_tag,
        by_split=_group_accuracy([(e.split, e.correct) for e in evaluations]),
        decision_rates=_decision_rates(evaluations),
        latency=latency,
        confusion_pairs=_confusion_pairs(evaluations, lex, top_confusions),
        model_versions=sorted({e.model_version for e in evaluations}),
        entries=evaluations,
        by_operator=by_operator,
        by_operand_length=by_operand_length,
        expression_total=len(expressions),
        expression_correct=sum(1 for e in expressions if e.correct),
        refusals=_refusal_rates(evaluations),
    )


# --------------------------------------------------------------------------- #
# Rapport versionné (reproductible)
# --------------------------------------------------------------------------- #


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _group_dict(groups: dict[str, GroupAccuracy]) -> dict[str, dict[str, float | int]]:
    return {
        name: {"total": g.total, "correct": g.correct, "accuracy": g.accuracy}
        for name, g in groups.items()
    }


def build_report(
    result: EvaluationResult,
    *,
    manifest_path: Path,
    settings: Settings,
    asr_mode: str,
    latency_source: str,
    split: str,
    lexicon: Lexicon | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    """Assemble le rapport machine (dict) avec toutes les métadonnées de repro."""

    lex = lexicon or zarma_numbers.load_lexicon()
    return {
        "harness_version": HARNESS_VERSION,
        "generated_at": timestamp or datetime.now(UTC).isoformat(),  # exempté du diff repro
        "split_evaluated": split,
        "manifest": {
            "name": manifest_path.name,
            "sha256": _sha256_file(manifest_path),
            "entries": result.total,
        },
        "asr": {
            "mode": asr_mode,
            "latency_source": latency_source,
            "model_versions": result.model_versions,
        },
        "versions": {
            "grammar_version": lex.grammar_version,
            "model_versions": result.model_versions,
        },
        "settings": {
            "asr_mode": asr_mode,
            "conf_weights": {
                "acoustic": settings.CONF_WEIGHT_ACOUSTIC,
                "grammar": settings.CONF_WEIGHT_GRAMMAR,
                "variant": settings.CONF_WEIGHT_VARIANT,
                "margin": settings.CONF_WEIGHT_MARGIN,
                "confusion": settings.CONF_WEIGHT_CONFUSION,
            },
            "policy_thresholds": {
                "accept": settings.POLICY_ACCEPT_THRESHOLD,
                "confirm": settings.POLICY_CONFIRM_THRESHOLD,
                "margin": settings.POLICY_MARGIN_THRESHOLD,
            },
        },
        "metrics": {
            "exact_number_accuracy": result.accuracy,
            "total": result.total,
            "correct": result.correct,
            # Story 6.1 — présent même à zéro sur un corpus « nombres seuls » :
            # une métrique absente se lit comme une mesure oubliée.
            "exact_expression_accuracy": result.exact_expression_accuracy,
            "expression_total": result.expression_total,
            "expression_correct": result.expression_correct,
            "by_operator": _group_dict(result.by_operator),
            "by_operand_length": _group_dict(result.by_operand_length),
            "refusals": {
                "total": result.refusals.total,
                "correct": result.refusals.correct,
                "wrong_code": result.refusals.wrong_code,
                "answered": result.refusals.answered,
                "correct_rate": result.refusals.correct_rate,
                "invented_rate": result.refusals.invented_rate,
            },
            "by_condition": _group_dict(result.by_condition),
            "by_tag": _group_dict(result.by_tag),
            "by_split": _group_dict(result.by_split),
            "decision_rates": {
                "total": result.decision_rates.total,
                "counts": result.decision_rates.counts,
                "rejection_rate": result.decision_rates.rejection_rate,
                "false_acceptance_rate": result.decision_rates.false_acceptance_rate,
                "confirmation_rate": result.decision_rates.confirmation_rate,
                "correct_acceptance_rate": result.decision_rates.correct_acceptance_rate,
            },
            "asr_latency_ms": result.latency,
        },
        "confusion_pairs": [
            {
                "expected_number": p.expected_number,
                "predicted_number": p.predicted_number,
                "count": p.count,
                "close": p.close,
            }
            for p in result.confusion_pairs
        ],
    }


def atomic_write_text(path: Path, text: str) -> None:
    """Écrit ``text`` dans ``path`` de façon atomique (temporaire + renommage)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


#: Alias interne rétro-compatible (comportement identique).
_atomic_write_text = atomic_write_text


def report_to_json(report: dict[str, object]) -> str:
    """Sérialise le rapport de façon **stable** (clés triées) → reproductible."""

    return json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _expression_sections(metrics: dict) -> list[str]:
    """Sections « expressions » du rapport — omises si le corpus n'en contient pas."""
    if not metrics.get("expression_total"):
        return []

    lines = [
        "",
        f"## Exact Expression Accuracy : **{metrics['exact_expression_accuracy']:.4f}** "
        f"({metrics['expression_correct']}/{metrics['expression_total']})",
        "",
        "> Tout-ou-rien : les deux opérandes, l'opérateur et le résultat "
        "(reste compris) doivent être justes.",
        "",
        "### Par opérateur",
        "",
        "| opérateur | accuracy | correct/total |",
        "|---|---|---|",
    ]
    for name, g in metrics["by_operator"].items():
        lines.append(f"| {name} | {g['accuracy']:.4f} | {g['correct']}/{g['total']} |")

    lines += [
        "",
        "### Par longueur d'opérandes",
        "",
        "| longueur | accuracy | correct/total |",
        "|---|---|---|",
    ]
    for name, g in metrics["by_operand_length"].items():
        lines.append(f"| {name} | {g['accuracy']:.4f} | {g['correct']}/{g['total']} |")

    refusals = metrics["refusals"]
    if refusals["total"]:
        lines += [
            "",
            "### Cas hors domaine (la bonne réponse est un refus)",
            "",
            f"- refus correct : {refusals['correct_rate']:.4f} "
            f"({refusals['correct']}/{refusals['total']})",
            f"- refus au mauvais motif : {refusals['wrong_code']}",
            f"- **résultat inventé** : {refusals['invented_rate']:.4f} "
            f"({refusals['answered']}/{refusals['total']}) — doit rester à 0 (FR21)",
        ]
    return lines


def report_to_markdown(report: dict[str, object]) -> str:
    """Rend un rapport Markdown lisible pour la revue QA."""

    metrics = report["metrics"]  # type: ignore[index]
    lines = [
        f"# Benchmark — Exact Number Accuracy ({report['split_evaluated']})",
        "",
        f"- **Harnais** : {report['harness_version']}",
        f"- **Manifest** : `{report['manifest']['name']}` "  # type: ignore[index]
        f"(sha256 `{report['manifest']['sha256'][:12]}…`, {report['manifest']['entries']} audios)",  # type: ignore[index]
        f"- **ASR** : mode `{report['asr']['mode']}`, latence `{report['asr']['latency_source']}`, "  # type: ignore[index]
        f"modèles {report['asr']['model_versions']}",  # type: ignore[index]
        f"- **grammar_version** : {report['versions']['grammar_version']}",  # type: ignore[index]
        f"- **Généré le** : {report['generated_at']}",
        "",
        f"## Exact Number Accuracy : **{metrics['exact_number_accuracy']:.4f}** "  # type: ignore[index]
        f"({metrics['correct']}/{metrics['total']})",  # type: ignore[index]
        "",
        "### Par condition",
        "",
        "| condition | accuracy | correct/total |",
        "|---|---|---|",
    ]
    for name, g in metrics["by_condition"].items():  # type: ignore[index]
        lines.append(f"| {name} | {g['accuracy']:.4f} | {g['correct']}/{g['total']} |")
    lines += ["", "### Par tag", "", "| tag | accuracy | correct/total |", "|---|---|---|"]
    for name, g in metrics["by_tag"].items():  # type: ignore[index]
        lines.append(f"| {name} | {g['accuracy']:.4f} | {g['correct']}/{g['total']} |")

    lines += _expression_sections(metrics)

    rates = metrics["decision_rates"]  # type: ignore[index]
    lines += [
        "",
        "### Taux de décision",
        "",
        f"- rejet : {rates['rejection_rate']:.4f}",
        f"- fausse acceptation : {rates['false_acceptance_rate']:.4f}",
        f"- confirmation : {rates['confirmation_rate']:.4f}",
        f"- acceptation correcte : {rates['correct_acceptance_rate']:.4f}",
        "",
        "### Latence ASR (ms)",
        "",
        f"- p50 {metrics['asr_latency_ms']['p50_ms']} · "  # type: ignore[index]
        f"p95 {metrics['asr_latency_ms']['p95_ms']} · "  # type: ignore[index]
        f"avg {metrics['asr_latency_ms']['avg_ms']}",  # type: ignore[index]
        "",
        "### Top paires de confusion (hors diagonale)",
        "",
        "| attendu | prédit | count | paire proche |",
        "|---|---|---|---|",
    ]
    for pair in report["confusion_pairs"]:  # type: ignore[index]
        predicted = "∅ (rejet)" if pair["predicted_number"] is None else pair["predicted_number"]
        lines.append(
            f"| {pair['expected_number']} | {predicted} | {pair['count']} | "
            f"{'✅' if pair['close'] else ''} |"
        )
    return "\n".join(lines) + "\n"


def write_report(out_base: Path, report: dict[str, object]) -> tuple[Path, Path]:
    """Écrit ``<out_base>.json`` + ``<out_base>.md`` atomiquement. Retourne les chemins."""

    json_path = out_base.with_suffix(".json")
    md_path = out_base.with_suffix(".md")
    _atomic_write_text(json_path, report_to_json(report))
    _atomic_write_text(md_path, report_to_markdown(report))
    return json_path, md_path


def write_hypotheses(path: Path, captured: dict[str, AsrResult]) -> None:
    """Dumpe les ``AsrResult`` capturés (rejouables sans GPU), écriture atomique."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            for audio_path in sorted(captured):
                record = asr_result_to_dict(audio_path, captured[audio_path])
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


__all__ = [
    "HARNESS_VERSION",
    "AsrSource",
    "CapturingSource",
    "ConfusionPair",
    "DecisionRates",
    "EntryEvaluation",
    "EvaluationError",
    "EvaluationResult",
    "GroupAccuracy",
    "RefusalRates",
    "SHORT_OPERAND_MAX_EXCLUSIVE",
    "asr_result_to_dict",
    "atomic_write_text",
    "build_report",
    "evaluate",
    "load_hypotheses",
    "recognizer_source",
    "replay_source",
    "report_to_json",
    "report_to_markdown",
    "write_hypotheses",
    "write_report",
]
