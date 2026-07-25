"""Constitution reproductible d'un corpus de benchmark (story 5.1).

Sans GPU ni inférence : cet outil ne fait que **planifier**, **assembler** et
**valider** un corpus d'évaluation étiqueté en vérité terrain, avec un **split
strict par locuteur** (anti-fuite, NFR10).

Sources uniques (jamais de règle dupliquée) :
- les **cibles** numériques et leurs formes canoniques viennent de
  ``zarma_numbers.generate`` ;
- les **paires de confusion** sont dérivées de ``Lexicon.asr_confusions`` — donc
  la couverture « confusion » grandit automatiquement quand le lexique s'enrichit.

Trois étapes :
- ``select_target_numbers`` / ``build_recording_plan`` : *quoi* enregistrer
  (couverture courts/longs/confusion, plusieurs locuteurs, calme/bruit) ;
- ``build_manifest`` : assemble le manifest versionné depuis un index des audios
  réellement enregistrés, avec split déterministe par locuteur ;
- ``validate_manifest`` : intégrité (vérité terrain, non-fuite, couverture).

Story 6.1 — le corpus couvre aussi des **expressions** (« 23 + 15 »).

⚠️ Un opérateur prononcé seul ne sonne pas comme le même opérateur au milieu
d'une phrase (coarticulation) : les enregistrements d'opérateurs isolés servent
au *lexique*, **jamais** au benchmark. Le plan produit ici demande donc des
**énoncés complets**. Les cas volontairement **hors domaine** (résultat négatif,
division non entière) y figurent : sans eux, le taux de refus correct — donc la
garantie « jamais de résultat inventé » — ne se mesure pas.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import zarma_numbers
from zarma_numbers import Lexicon

MAX_NUMBER = 1_000_000

#: Conditions d'enregistrement attendues (AC3).
CONDITIONS: tuple[str, ...] = ("calme", "bruit")

#: Splits du benchmark ; un locuteur ne peut apparaître que dans un seul.
DEFAULT_SPLITS: tuple[tuple[str, float], ...] = (("test", 0.8), ("dev", 0.2))

#: Seed documentée du split par locuteur (versionnée avec le code).
DEFAULT_SPLIT_SEED = "zarma-benchmark-split-v1"

#: Frontière courts/longs : moins de 100 = « court » (unités/dizaines).
SHORT_MAX_EXCLUSIVE = 100

#: Cibles « courtes » : unités, adolescents et dizaines rondes + combinaisons.
_SHORT_TARGETS: tuple[int, ...] = (
    *range(0, 21),
    21,
    25,
    30,
    42,
    50,
    60,
    70,
    80,
    90,
    99,
)

#: Cibles « longues » : centaines, milliers et grandes échelles.
_LONG_TARGETS: tuple[int, ...] = (
    100,
    101,
    110,
    111,
    200,
    372,
    500,
    999,
    1_000,
    1_234,
    2_025,
    5_000,
    10_000,
    12_345,
    100_000,
    500_000,
    999_999,
    1_000_000,
)

_SPLIT_TOLERANCE = 1e-9


class CorpusError(Exception):
    """Erreur contrôlée de constitution/validation du corpus."""


@dataclass(frozen=True, slots=True)
class TargetNumber:
    """Une cible d'enregistrement : nombre + forme canonique + catégories."""

    value: int
    prompt: str
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class PlanItem:
    """Une consigne d'enregistrement (locuteur × cible × condition)."""

    speaker: str
    expected_number: int
    expected_prompt: str
    condition: str
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class TargetExpression:
    """Une cible d'expression : opération + forme canonique + vérité terrain.

    ``expected_number`` porte le résultat attendu (le quotient si
    ``expected_remainder`` est non nul), ou ``None`` quand l'opération sort du
    domaine — auquel cas ``expected_refusal`` porte le code de refus attendu.
    C'est **cette** vérité terrain qui permet de mesurer un refus correct.
    """

    spec: str
    prompt: str
    expected_number: int | None
    expected_remainder: int
    expected_refusal: str | None
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class ExpressionPlanItem:
    """Une consigne d'enregistrement d'**expression complète**."""

    speaker: str
    expected_expression: str
    expected_prompt: str
    expected_number: int | None
    expected_remainder: int
    expected_refusal: str | None
    condition: str
    tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """Une ligne de manifest (audio étiqueté, prêt pour l'évaluation).

    Deux natures d'entrée cohabitent, distinguées par ``expected_expression`` :

    - **nombre seul** (epics 1–5) : ``expected_expression is None`` et
      ``expected_number`` est le nombre attendu ;
    - **expression** (story 6.1) : ``expected_expression`` porte la spécification
      canonique (``"23+15"``) et ``expected_number`` le **résultat** attendu, ou
      ``None`` si l'opération doit être refusée (``expected_refusal``).
    """

    audio_path: str
    expected_number: int | None
    expected_prompt: str
    speaker_key: str
    region: str | None
    condition: str
    split: str
    expected_expression: str | None = None
    expected_remainder: int = 0
    expected_refusal: str | None = None

    @property
    def is_expression(self) -> bool:
        return self.expected_expression is not None


@dataclass(frozen=True, slots=True)
class BuildError:
    """Motif opaque d'exclusion d'une entrée source (aucune PII)."""

    audio_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class ManifestResult:
    written: bool
    output_path: Path | None
    entries: list[ManifestEntry]
    errors: list[BuildError]
    seed: str


@dataclass(slots=True)
class CorpusReport:
    """Rapport de validation d'intégrité d'un corpus/manifest."""

    total_audios: int
    speakers: int
    per_split: dict[str, int]
    per_condition: dict[str, int]
    per_tag: dict[str, int]
    leaking_speakers: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and not self.leaking_speakers


# --------------------------------------------------------------------------- #
# Dérivations depuis la source unique (zarma_numbers)
# --------------------------------------------------------------------------- #


def confusable_forms(lexicon: Lexicon) -> frozenset[str]:
    """Ensemble des formes acoustiquement confusables (clés ⋃ valeurs)."""

    return frozenset(lexicon.asr_confusions.keys()) | frozenset(lexicon.asr_confusions.values())


def classify(value: int, prompt: str, confusables: frozenset[str]) -> frozenset[str]:
    """Étiquette une cible : ``short``/``long`` (+ ``confusion`` si applicable)."""

    tags = {"short" if value < SHORT_MAX_EXCLUSIVE else "long"}
    if set(prompt.split()) & confusables:
        tags.add("confusion")
    return frozenset(tags)


def select_target_numbers(lexicon: Lexicon | None = None) -> list[TargetNumber]:
    """Sélection déterministe des cibles couvrant courts/longs/confusion.

    L'ordre est stable (par valeur) → reproductible. Les paires de confusion sont
    dérivées de ``asr_confusions`` : toute cible dont la forme canonique contient
    une forme confusable est taguée ``confusion``.
    """

    lex = lexicon or zarma_numbers.load_lexicon()
    confusables = confusable_forms(lex)
    values = sorted(dict.fromkeys((*_SHORT_TARGETS, *_LONG_TARGETS)))
    targets: list[TargetNumber] = []
    for value in values:
        if not 0 <= value <= MAX_NUMBER:
            raise CorpusError(f"cible hors plage : {value}")
        prompt = zarma_numbers.generate(value)
        targets.append(
            TargetNumber(value=value, prompt=prompt, tags=classify(value, prompt, confusables))
        )
    return targets


# --------------------------------------------------------------------------- #
# Cibles d'expressions (story 6.1)
# --------------------------------------------------------------------------- #

#: Couples d'opérandes **courts** (deux nombres < 100).
_SHORT_OPERANDS: tuple[tuple[int, int], ...] = ((2, 3), (12, 7), (23, 15), (40, 8), (99, 9))

#: Couples d'opérandes **longs** (au moins un ≥ 100) — exercent la composition.
_LONG_OPERANDS: tuple[tuple[int, int], ...] = ((105, 7), (372, 28), (1_234, 6), (12_345, 5))

#: Couples choisis pour tomber **hors domaine** — ils testent le refus.
#: Le symbole est imposé : c'est lui qui provoque le cas.
_OUT_OF_DOMAIN: tuple[tuple[str, int, int], ...] = (
    ("-", 3, 5),  # résultat négatif
    ("-", 12, 40),  # résultat négatif, opérandes plus longs
    ("*", 2_000, 2_000),  # dépassement
    ("+", 999_999, 100),  # dépassement par l'addition
)


def _target_expression(symbol: str, left: int, right: int, size_tag: str) -> TargetExpression:
    """Construit une cible d'expression et sa vérité terrain (jamais devinée)."""
    expression = zarma_numbers.Expression(left, symbol, right)
    prompt = zarma_numbers.render_expression(expression)
    tags = {size_tag, f"operator:{expression.operator_name}"}
    try:
        result = zarma_numbers.evaluate(expression)
    except zarma_numbers.DomainError as exc:
        return TargetExpression(
            spec=f"{left}{symbol}{right}",
            prompt=prompt,
            expected_number=None,
            expected_remainder=0,
            expected_refusal=exc.code,
            tags=frozenset(tags | {"out_of_domain"}),
        )
    if result.remainder:
        tags.add("remainder")
    return TargetExpression(
        spec=f"{left}{symbol}{right}",
        prompt=prompt,
        expected_number=result.value,
        expected_remainder=result.remainder,
        expected_refusal=None,
        tags=frozenset(tags),
    )


def select_target_expressions(lexicon: Lexicon | None = None) -> list[TargetExpression]:
    """Cibles d'expressions couvrant opérateurs × longueurs × cas hors domaine.

    Seuls les opérateurs **résolus** au lexique sont couverts : une forme non
    validée par un locuteur natif n'est pas devinée, donc pas enregistrable
    (elle apparaîtra d'elle-même quand le lexique sera complété). L'ordre est
    stable → plan reproductible.
    """
    lex = lexicon or zarma_numbers.load_lexicon()
    symbols = sorted(op.symbol for op in lex.operators.values() if op.resolved)
    if not symbols:
        raise CorpusError(
            "aucun opérateur résolu dans le lexique : aucun énoncé d'expression "
            "ne peut être planifié (cf. docs/lexique-operateurs-a-valider.md)"
        )

    targets: list[TargetExpression] = []
    for symbol in symbols:
        for left, right in _SHORT_OPERANDS:
            targets.append(_target_expression(symbol, left, right, "short"))
        for left, right in _LONG_OPERANDS:
            targets.append(_target_expression(symbol, left, right, "long"))

    for symbol, left, right in _OUT_OF_DOMAIN:
        if symbol in symbols:
            size_tag = "short" if max(left, right) < SHORT_MAX_EXCLUSIVE else "long"
            targets.append(_target_expression(symbol, left, right, size_tag))

    # Dédoublonnage stable : un même énoncé ne s'enregistre pas deux fois.
    unique: dict[str, TargetExpression] = {}
    for target in targets:
        unique.setdefault(target.spec, target)
    return sorted(unique.values(), key=lambda t: t.spec)


def build_expression_recording_plan(
    targets: Sequence[TargetExpression],
    speakers: Sequence[str],
    *,
    conditions: Sequence[str] = CONDITIONS,
) -> list[ExpressionPlanItem]:
    """Assigne chaque expression à chaque locuteur, condition alternée.

    Même construction que ``build_recording_plan`` — donc même garantie de
    reproductibilité — mais les consignes sont des **énoncés complets**.
    """
    if not speakers:
        raise CorpusError("au moins un locuteur est requis")
    if not targets:
        raise CorpusError("au moins une cible est requise")

    plan: list[ExpressionPlanItem] = []
    for speaker_index, speaker in enumerate(speakers):
        for target_index, target in enumerate(targets):
            condition = conditions[(speaker_index + target_index) % len(conditions)]
            plan.append(
                ExpressionPlanItem(
                    speaker=speaker,
                    expected_expression=target.spec,
                    expected_prompt=target.prompt,
                    expected_number=target.expected_number,
                    expected_remainder=target.expected_remainder,
                    expected_refusal=target.expected_refusal,
                    condition=condition,
                    tags=target.tags,
                )
            )
    return plan


# --------------------------------------------------------------------------- #
# Plan d'enregistrement (quoi enregistrer, pour atteindre ≥ 100 audios)
# --------------------------------------------------------------------------- #


def build_recording_plan(
    targets: Sequence[TargetNumber],
    speakers: Sequence[str],
    *,
    conditions: Sequence[str] = CONDITIONS,
) -> list[PlanItem]:
    """Assigne chaque cible à chaque locuteur, condition alternée déterministe.

    Produit ``len(speakers) × len(targets)`` consignes ; avec plusieurs locuteurs
    et la liste de cibles par défaut, on dépasse largement 100 audios (AC1). La
    condition alterne calme/bruit pour couvrir les deux par locuteur.
    """

    if not speakers:
        raise CorpusError("au moins un locuteur est requis")
    if not targets:
        raise CorpusError("au moins une cible est requise")
    plan: list[PlanItem] = []
    for speaker_index, speaker in enumerate(speakers):
        for target_index, target in enumerate(targets):
            condition = conditions[(speaker_index + target_index) % len(conditions)]
            plan.append(
                PlanItem(
                    speaker=speaker,
                    expected_number=target.value,
                    expected_prompt=target.prompt,
                    condition=condition,
                    tags=target.tags,
                )
            )
    return plan


# --------------------------------------------------------------------------- #
# Split par locuteur (déterministe, anti-fuite)
# --------------------------------------------------------------------------- #


def speaker_key_for(speaker: str) -> str:
    """Dérive une clé locuteur anonyme et stable depuis un label opaque."""

    # Déjà une clé (64 hex) ? on la garde telle quelle.
    stripped = speaker.strip()
    if len(stripped) == 64 and all(c in "0123456789abcdef" for c in stripped.lower()):
        return stripped.lower()
    return hashlib.sha256(stripped.encode("utf-8")).hexdigest()


def _validate_splits(splits: Sequence[tuple[str, float]]) -> None:
    if not splits:
        raise CorpusError("au moins un split est requis")
    names = [name for name, _ in splits]
    if len(set(names)) != len(names):
        raise CorpusError("les noms de split doivent être uniques")
    if any(ratio < 0 for _, ratio in splits):
        raise CorpusError("les ratios de split doivent être positifs")
    total = sum(ratio for _, ratio in splits)
    if abs(total - 1.0) > _SPLIT_TOLERANCE:
        raise CorpusError(f"les ratios de split doivent sommer à 1.0 (reçu {total})")


def assign_split(
    speaker_key: str,
    seed: str = DEFAULT_SPLIT_SEED,
    splits: Sequence[tuple[str, float]] = DEFAULT_SPLITS,
) -> str:
    """Affecte un locuteur à un split unique, fonction pure de ``(seed, key)``.

    Un même locuteur tombe toujours dans le même split ; ajouter des locuteurs ne
    déplace jamais les existants → aucune fuite entre splits (NFR10).
    """

    digest = hashlib.sha256(f"{seed}:{speaker_key}".encode()).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    cumulative = 0.0
    for name, ratio in splits:
        cumulative += ratio
        if fraction < cumulative:
            return name
    return splits[-1][0]


# --------------------------------------------------------------------------- #
# Assemblage du manifest depuis un index des audios enregistrés
# --------------------------------------------------------------------------- #


def parse_expression_spec(spec: str) -> zarma_numbers.Expression:
    """Lit une spécification ``"<gauche><symbole><droite>"`` (ex. ``"23+15"``).

    Format **interne** au corpus (chiffres, jamais du zarma) : il fixe la vérité
    terrain sans dépendre de l'orthographe d'un énoncé.
    """
    for symbol in ("+", "-", "*", "/"):
        left, found, right = spec.partition(symbol)
        if found and left.strip().isdigit() and right.strip().isdigit():
            return zarma_numbers.Expression(int(left), symbol, int(right))
    raise CorpusError(f"spécification d'expression illisible : {spec!r}")


def _expression_truth(spec: str) -> tuple[str, int | None, int, str | None]:
    """(forme canonique, résultat, reste, code de refus) d'une spécification."""
    expression = parse_expression_spec(spec)
    prompt = zarma_numbers.render_expression(expression)
    try:
        result = zarma_numbers.evaluate(expression)
    except zarma_numbers.DomainError as exc:
        return prompt, None, 0, exc.code
    return prompt, result.value, result.remainder, None


def _validate_expression_row(row: dict) -> str | None:
    """Valide une ligne source d'**expression** (story 6.1)."""
    spec = row.get("expected_expression")
    if not isinstance(spec, str) or not spec.strip():
        return "expected_expression_invalid"
    try:
        canonical, _number, _remainder, _refusal = _expression_truth(spec)
    except (CorpusError, ValueError):
        return "expected_expression_invalid"
    except zarma_numbers.DomainError:
        # L'opérateur n'a pas de forme zarma validée : l'énoncé n'est pas
        # prononçable, donc pas enregistrable. Refus explicite.
        return "operator_unresolved"
    prompt = row.get("expected_prompt")
    if prompt is not None and prompt != canonical:
        return "prompt_mismatch"
    if row.get("condition") not in CONDITIONS:
        return "condition_invalid"
    return None


def _validate_source_row(row: dict, lexicon: Lexicon) -> str | None:
    audio_path = row.get("audio_path")
    if not audio_path or not isinstance(audio_path, str):
        return "audio_path_missing"
    if "/" in audio_path or "\\" in audio_path or Path(audio_path).is_absolute():
        return "audio_path_not_relative"
    speaker = row.get("speaker") or row.get("speaker_key")
    if not speaker or not isinstance(speaker, str):
        return "speaker_missing"
    if row.get("expected_expression") is not None:
        return _validate_expression_row(row)
    number = row.get("expected_number")
    if not isinstance(number, int) or isinstance(number, bool) or not (0 <= number <= MAX_NUMBER):
        return "expected_number_invalid"
    try:
        canonical = zarma_numbers.generate(number)
    except (zarma_numbers.OutOfRangeError, zarma_numbers.UnresolvedFormError):
        return "ground_truth_unresolved"
    prompt = row.get("expected_prompt")
    if prompt is not None and prompt != canonical:
        return "prompt_mismatch"
    if row.get("condition") not in CONDITIONS:
        return "condition_invalid"
    return None


def build_manifest(
    source_rows: Iterable[dict],
    *,
    lexicon: Lexicon | None = None,
    splits: Sequence[tuple[str, float]] = DEFAULT_SPLITS,
    seed: str = DEFAULT_SPLIT_SEED,
    audio_root: Path | None = None,
    allow_partial: bool = False,
) -> ManifestResult:
    """Assemble le manifest versionné depuis l'index des audios enregistrés.

    Valide la vérité terrain de chaque entrée, affecte un split **strict** par
    locuteur, et refuse toute entrée invalide (fail-closed par défaut). L'ordre de
    sortie est stable → deux exécutions produisent un manifest identique.
    """

    _validate_splits(splits)
    lex = lexicon or zarma_numbers.load_lexicon()
    rows = list(source_rows)

    valid: list[dict] = []
    errors: list[BuildError] = []
    for row in rows:
        reason = _validate_source_row(row, lex)
        if reason is None and audio_root is not None:
            if not (audio_root / row["audio_path"]).is_file():
                reason = "audio_missing"
        if reason is not None:
            errors.append(BuildError(audio_path=str(row.get("audio_path") or "?"), reason=reason))
        else:
            valid.append(row)

    if errors and not allow_partial:
        return ManifestResult(written=False, output_path=None, entries=[], errors=errors, seed=seed)

    speaker_split: dict[str, str] = {}
    entries: list[ManifestEntry] = []
    for row in valid:
        speaker_key = speaker_key_for(row.get("speaker") or row["speaker_key"])
        split = speaker_split.setdefault(speaker_key, assign_split(speaker_key, seed, splits))
        spec = row.get("expected_expression")
        if spec is not None:
            prompt, number, remainder, refusal = _expression_truth(spec)
            entries.append(
                ManifestEntry(
                    audio_path=row["audio_path"],
                    expected_number=number,
                    expected_prompt=prompt,
                    speaker_key=speaker_key,
                    region=row.get("region"),
                    condition=row["condition"],
                    split=split,
                    expected_expression=spec,
                    expected_remainder=remainder,
                    expected_refusal=refusal,
                )
            )
            continue
        number = row["expected_number"]
        entries.append(
            ManifestEntry(
                audio_path=row["audio_path"],
                expected_number=number,
                expected_prompt=zarma_numbers.generate(number),
                speaker_key=speaker_key,
                region=row.get("region"),
                condition=row["condition"],
                split=split,
            )
        )

    # Le tri reste total et stable malgré les entrées sans nombre attendu
    # (cas hors domaine) : elles se rangent en tête de leur locuteur.
    entries.sort(
        key=lambda e: (
            e.split,
            e.speaker_key,
            e.expected_number is not None,
            e.expected_number or 0,
            e.audio_path,
        )
    )
    return ManifestResult(written=True, output_path=None, entries=entries, errors=errors, seed=seed)


# --------------------------------------------------------------------------- #
# Validation d'intégrité
# --------------------------------------------------------------------------- #


def _validate_number_entry(
    entry: ManifestEntry, confusables: frozenset[str], problems: list[str]
) -> frozenset[str]:
    """Vérité terrain d'une entrée « nombre seul » (comportement 5.1 inchangé)."""
    if entry.expected_number is None:
        problems.append(f"expected_number_missing:{entry.audio_path}")
        return frozenset()
    try:
        canonical = zarma_numbers.generate(entry.expected_number)
    except (zarma_numbers.OutOfRangeError, zarma_numbers.UnresolvedFormError):
        problems.append(f"ground_truth_unresolved:{entry.audio_path}")
        return frozenset()
    if entry.expected_prompt != canonical:
        problems.append(f"prompt_mismatch:{entry.audio_path}")
    return classify(entry.expected_number, canonical, confusables)


def _validate_expression_entry(entry: ManifestEntry, problems: list[str]) -> frozenset[str]:
    """Vérité terrain d'une entrée « expression » — recalculée, jamais crue sur parole."""
    assert entry.expected_expression is not None  # garanti par ``is_expression``
    try:
        prompt, number, remainder, refusal = _expression_truth(entry.expected_expression)
    except (CorpusError, ValueError, zarma_numbers.DomainError):
        problems.append(f"expression_unresolved:{entry.audio_path}")
        return frozenset()

    if entry.expected_prompt != prompt:
        problems.append(f"prompt_mismatch:{entry.audio_path}")
    if (entry.expected_number, entry.expected_remainder, entry.expected_refusal) != (
        number,
        remainder,
        refusal,
    ):
        problems.append(f"expression_truth_mismatch:{entry.audio_path}")

    expression = parse_expression_spec(entry.expected_expression)
    tags = {
        "expression",
        f"operator:{expression.operator_name}",
        "short" if max(expression.left, expression.right) < SHORT_MAX_EXCLUSIVE else "long",
    }
    if refusal is not None:
        tags.add("out_of_domain")
    if remainder:
        tags.add("remainder")
    return frozenset(tags)


def validate_manifest(
    entries: Sequence[ManifestEntry],
    *,
    lexicon: Lexicon | None = None,
    min_audios: int = 100,
    min_speakers: int = 3,
    required_tags: Sequence[str] = ("short", "long", "confusion"),
) -> CorpusReport:
    """Vérifie vérité terrain, non-fuite de locuteur et couverture du corpus."""

    lex = lexicon or zarma_numbers.load_lexicon()
    confusables = confusable_forms(lex)
    per_split: dict[str, int] = {}
    per_condition: dict[str, int] = {}
    per_tag: dict[str, int] = {}
    speaker_to_splits: dict[str, set[str]] = {}
    problems: list[str] = []

    for entry in entries:
        per_split[entry.split] = per_split.get(entry.split, 0) + 1
        per_condition[entry.condition] = per_condition.get(entry.condition, 0) + 1
        speaker_to_splits.setdefault(entry.speaker_key, set()).add(entry.split)

        if entry.is_expression:
            tags = _validate_expression_entry(entry, problems)
        else:
            tags = _validate_number_entry(entry, confusables, problems)
        if entry.condition not in CONDITIONS:
            problems.append(f"condition_invalid:{entry.audio_path}")
        for tag in tags:
            per_tag[tag] = per_tag.get(tag, 0) + 1

    leaking = sorted(key for key, s in speaker_to_splits.items() if len(s) > 1)
    report = CorpusReport(
        total_audios=len(entries),
        speakers=len(speaker_to_splits),
        per_split=per_split,
        per_condition=per_condition,
        per_tag=per_tag,
        leaking_speakers=leaking,
    )
    if report.total_audios < min_audios:
        problems.append(f"too_few_audios:{report.total_audios}<{min_audios}")
    if report.speakers < min_speakers:
        problems.append(f"too_few_speakers:{report.speakers}<{min_speakers}")
    for tag in required_tags:
        if per_tag.get(tag, 0) == 0:
            problems.append(f"missing_coverage:{tag}")
    report.problems = problems
    return report


# --------------------------------------------------------------------------- #
# Entrées/sorties JSONL (écriture atomique, lecture)
# --------------------------------------------------------------------------- #


def _entry_dict(entry: ManifestEntry) -> dict[str, object]:
    record: dict[str, object] = {
        "audio_path": entry.audio_path,
        "expected_number": entry.expected_number,
        "expected_prompt": entry.expected_prompt,
        "speaker_key": entry.speaker_key,
        "region": entry.region,
        "condition": entry.condition,
        "split": entry.split,
    }
    # Champs additifs : absents d'une entrée « nombre seul », de sorte qu'un
    # manifest 5.1 déjà produit reste identique octet pour octet.
    if entry.is_expression:
        record["expected_expression"] = entry.expected_expression
        record["expected_remainder"] = entry.expected_remainder
        record["expected_refusal"] = entry.expected_refusal
    return record


def write_jsonl(output_path: Path, records: Iterable[dict[str, object]]) -> None:
    """Écrit un JSONL de façon atomique (fichier temporaire puis renommage)."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.parent / f".{output_path.name}.{uuid4().hex}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=False))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_manifest(output_path: Path, entries: Sequence[ManifestEntry]) -> None:
    write_jsonl(output_path, [_entry_dict(entry) for entry in entries])


def read_manifest(path: Path) -> list[ManifestEntry]:
    """Relit un manifest JSONL en objets ``ManifestEntry``."""

    entries: list[ManifestEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        entries.append(
            ManifestEntry(
                audio_path=record["audio_path"],
                expected_number=record["expected_number"],
                expected_prompt=record["expected_prompt"],
                speaker_key=record["speaker_key"],
                region=record.get("region"),
                condition=record["condition"],
                split=record["split"],
                expected_expression=record.get("expected_expression"),
                expected_remainder=record.get("expected_remainder", 0),
                expected_refusal=record.get("expected_refusal"),
            )
        )
    return entries


def read_source(path: Path) -> list[dict]:
    """Relit un index source JSONL (audios enregistrés) en dictionnaires."""

    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def plan_dict(item: PlanItem) -> dict[str, object]:
    return {
        "speaker": item.speaker,
        "expected_number": item.expected_number,
        "expected_prompt": item.expected_prompt,
        "condition": item.condition,
        "tags": sorted(item.tags),
    }


def expression_plan_dict(item: ExpressionPlanItem) -> dict[str, object]:
    """Consigne d'enregistrement d'une expression, prête pour le JSONL.

    ``expected_prompt`` est ce qu'il faut **dire** ; ``expected_expression`` est
    la vérité terrain en chiffres, qui sert à mesurer.
    """
    return {
        "speaker": item.speaker,
        "expected_expression": item.expected_expression,
        "expected_prompt": item.expected_prompt,
        "expected_number": item.expected_number,
        "expected_remainder": item.expected_remainder,
        "expected_refusal": item.expected_refusal,
        "condition": item.condition,
        "tags": sorted(item.tags),
    }


__all__ = [
    "CONDITIONS",
    "DEFAULT_SPLITS",
    "DEFAULT_SPLIT_SEED",
    "BuildError",
    "CorpusError",
    "CorpusReport",
    "ExpressionPlanItem",
    "ManifestEntry",
    "ManifestResult",
    "PlanItem",
    "TargetExpression",
    "TargetNumber",
    "assign_split",
    "build_expression_recording_plan",
    "build_manifest",
    "build_recording_plan",
    "classify",
    "confusable_forms",
    "expression_plan_dict",
    "parse_expression_spec",
    "select_target_expressions",
    "plan_dict",
    "read_manifest",
    "read_source",
    "select_target_numbers",
    "speaker_key_for",
    "validate_manifest",
    "write_jsonl",
    "write_manifest",
]
