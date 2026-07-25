"""Fixtures de logits pour tester le décodeur **sans modèle ni GPU** (task 6).

Deux provenances, un seul format (``.npz`` compressé, clés ``logits`` /
``expected_number`` / ``expected_prompt`` / ``provenance``) :

- ``synthetic`` — générées **déterministement** par ce module (aucun binaire
  volumineux dans Git, aucune dépendance réseau). Elles couvrent les cas qui
  comptent : nombre net, nombre bruité, entrée non numérique.
- ``model`` — logits **réels** (``omniASR_CTC_300M_v2``, forme ``(T, 10288)``)
  dumpés par ``scripts/bench/decode_constrained.py --dump-logits`` dans
  ``services/asr/tests/fixtures/``. Dès qu'un tel fichier est présent, il est
  automatiquement pris en compte par les tests, sans modification de code.

Chaque provenance a **son** lexique de tokens :

- les fixtures synthétiques utilisent un tokenizer **jouet** (un id par
  caractère, ids spéciaux ``0..3`` réservés comme chez Omnilingual) ;
- les fixtures réelles utilisent le lexique **réel** sauvegardé en
  ``fixtures/token-lexicon.json`` (33 mots → ids du BPE Omnilingual, séparateur
  de mots = id ``4``), sondé une fois sur le vrai tokenizer.

Le décodeur est agnostique du tokenizer : seul le contrat « mot → séquences
d'ids » compte, ce que ces deux lexiques illustrent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from zarma_numbers.generator import generate

#: Répertoire des fixtures réelles (dumpées depuis le modèle ; vide par défaut).
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

#: Lexique de tokens **réel** (sondé sur le tokenizer Omnilingual).
REAL_LEXICON_PATH = FIXTURES_DIR / "token-lexicon.json"

#: Séparateur de mots du tokenizer Omnilingual (l'espace) — vérifié.
REAL_SEPARATOR_IDS: tuple[int, ...] = (4,)

_ALPHABET = "abcdefghijklmnopqrstuvwxyz "
_CHAR_TO_ID = {char: 4 + index for index, char in enumerate(_ALPHABET)}
_BLANK = 0


def toy_vocab_size() -> int:
    """Taille du vocabulaire jouet (marge incluse pour des ids jamais émis)."""
    return 4 + len(_ALPHABET) + 3


def toy_encode(text: str) -> list[int]:
    """Encode un texte en ids jouet (un id par caractère)."""
    return [_CHAR_TO_ID[char] for char in text]


@dataclass(frozen=True)
class LogitsFixture:
    """Un tenseur de logits et sa vérité terrain."""

    name: str
    logits: np.ndarray
    #: ``None`` pour une entrée volontairement non numérique.
    expected_number: int | None
    expected_prompt: str
    provenance: str


def clean_logits(
    text: str,
    *,
    frames_per_token: int = 2,
    strength: float = 8.0,
    noise: float = 0.0,
    seed: int = 0,
) -> np.ndarray:
    """Logits ``(T, V)`` favorisant l'alignement CTC de ``text``.

    Un blank est inséré entre les tokens — la structure qu'un modèle CTC produit
    réellement (et qui est nécessaire entre caractères répétés).
    """
    frame_ids: list[int] = []
    for token_id in toy_encode(text):
        frame_ids.extend([token_id] * frames_per_token)
        frame_ids.append(_BLANK)
    rng = np.random.default_rng(seed)
    logits = rng.normal(0.0, noise, size=(len(frame_ids), toy_vocab_size()))
    for frame, token_id in enumerate(frame_ids):
        logits[frame, token_id] += strength
    return logits


def _synthetic_fixtures() -> dict[str, LogitsFixture]:
    """Jeu déterministe couvrant net / bruité / non numérique."""
    specs: dict[str, tuple[np.ndarray, int | None]] = {
        # Énoncé court et net — le cas d'usage central du produit.
        "clean-short-42": (clean_logits(generate(42)), 42),
        # Énoncé long et net — exerce la composition zambar/nda.
        "clean-long-1234": (clean_logits(generate(1234)), 1234),
        # Énoncé bruité mais encore lisible.
        "noisy-372": (clean_logits(generate(372), noise=1.5, seed=4), 372),
        # Entrée non numérique : aucun nombre ne doit s'imposer (FR21).
        "non-numeric-speech": (clean_logits("kala suba borey ga koy"), None),
    }
    return {
        name: LogitsFixture(
            name=name,
            logits=logits,
            expected_number=number,
            expected_prompt="" if number is None else generate(number),
            provenance="synthetic",
        )
        for name, (logits, number) in specs.items()
    }


def expression_fixtures() -> dict[str, LogitsFixture]:
    """Logits synthétiques d'**expressions** complètes (story 6.1, task 4).

    Volontairement séparées du jeu ci-dessus : elles ne relèvent pas de la même
    langue contrainte, et le décodeur des nombres seuls doit continuer d'être
    testé exactement comme avant (non-régression des epics 1–5).

    ``expected_number`` porte ici le **résultat** attendu de l'opération, et
    ``expected_prompt`` la forme canonique de l'énoncé.
    """
    from zarma_numbers.expressions import Expression, evaluate, render_expression

    specs = [
        ("clean-23-plus-15", Expression(23, "+", 15)),
        ("clean-40-minus-8", Expression(40, "-", 8)),
        ("noisy-105-plus-7", Expression(105, "+", 7)),
    ]
    fixtures: dict[str, LogitsFixture] = {}
    for name, expression in specs:
        prompt = render_expression(expression)
        noise = 1.5 if name.startswith("noisy") else 0.0
        fixtures[name] = LogitsFixture(
            name=name,
            logits=clean_logits(prompt, noise=noise, seed=7),
            expected_number=evaluate(expression).value,
            expected_prompt=prompt,
            provenance="synthetic",
        )
    return fixtures


def _model_fixtures() -> dict[str, LogitsFixture]:
    """Fixtures réelles présentes sur disque (aucune si le dump n'a pas eu lieu)."""
    if not FIXTURES_DIR.is_dir():
        return {}
    fixtures: dict[str, LogitsFixture] = {}
    for path in sorted(FIXTURES_DIR.glob("*.npz")):
        with np.load(path, allow_pickle=False) as data:
            number = int(data["expected_number"]) if "expected_number" in data else -1
            fixtures[path.stem] = LogitsFixture(
                name=path.stem,
                logits=np.asarray(data["logits"], dtype=np.float64),
                expected_number=None if number < 0 else number,
                expected_prompt=str(data["expected_prompt"]) if "expected_prompt" in data else "",
                provenance="model",
            )
    return fixtures


def _all_fixtures() -> dict[str, LogitsFixture]:
    fixtures = _synthetic_fixtures()
    fixtures.update(_model_fixtures())  # les fixtures réelles priment
    return fixtures


#: Noms disponibles (synthétiques + réelles éventuelles).
LOGITS_FIXTURES: tuple[str, ...] = tuple(sorted(_all_fixtures()))


def load_fixture(name: str) -> LogitsFixture:
    """Charge une fixture par son nom."""
    fixtures = _all_fixtures()
    try:
        return fixtures[name]
    except KeyError as exc:  # pragma: no cover - garde-fou
        raise KeyError(f"Fixture de logits inconnue : {name!r}") from exc


def real_token_lexicon(decoding_module):
    """Lexique de tokens **réel** (BPE Omnilingual), chargé depuis le JSON livré.

    Les ids ne sont pas recalculés ici — ils ont été sondés une fois sur le vrai
    tokenizer et versionnés avec les fixtures, pour que la CI reste sans modèle.
    """
    raw = json.loads(REAL_LEXICON_PATH.read_text(encoding="utf-8"))
    return decoding_module.TokenLexicon(
        entries={word: tuple(tuple(ids) for ids in encodings) for word, encodings in raw.items()},
        separator=REAL_SEPARATOR_IDS,
    )


def toy_token_lexicon(decoding_module, grammar):
    """Lexique de tokens **jouet** (un id par caractère)."""
    return decoding_module.build_token_lexicon(
        grammar, toy_encode, separator=toy_encode(" "), blank_id=_BLANK
    )


def lexicon_for(fixture: LogitsFixture, decoding_module, grammar):
    """Le lexique correspondant à la provenance de ``fixture``."""
    if fixture.provenance == "model":
        return real_token_lexicon(decoding_module)
    return toy_token_lexicon(decoding_module, grammar)


__all__ = [
    "FIXTURES_DIR",
    "LOGITS_FIXTURES",
    "REAL_LEXICON_PATH",
    "REAL_SEPARATOR_IDS",
    "LogitsFixture",
    "clean_logits",
    "expression_fixtures",
    "lexicon_for",
    "load_fixture",
    "real_token_lexicon",
    "toy_encode",
    "toy_token_lexicon",
    "toy_vocab_size",
]
