"""Normaliseur de texte zarma (story 1.5).

Ramène un texte brut (ASR ou saisi) vers une forme canonique normalisée que le
parseur (story 1.6) pourra analyser de façon déterministe : casse, espaces,
apostrophes/Unicode, puis remplacement des **variantes linguistiques** connues
par leur forme canonique.

Principes stricts :

- **Source unique** : le mapping provient de ``Lexicon.linguistic_variant_map()``
  (story 1.3) ; aucune forme codée en dur.
- **Jamais de fuzzy matching décisionnel** : seuls des remplacements **exacts**
  token-à-token sont appliqués. ``hinka`` (2) et ``hinza`` (3) restent distincts.
- **Variantes ≠ corrections ASR** : les ``asr_confusions`` ne sont **pas**
  appliquées ici (séparation stricte, FR8).
- **Formes canoniques protégées** : une forme canonique produite par le
  générateur (unité isolée *ou* combinée, dizaine, connecteur, échelle) n'est
  **jamais** réécrite. Cela évite de corrompre le sens (ex. ``fo`` ≠ ``afo``
  sont deux formes canoniques contextuelles) et garantit l'idempotence.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from .loader import Lexicon, load_lexicon

#: Apostrophes/quotes typographiques ramenées vers l'apostrophe simple.
_APOSTROPHES = {"’": "'", "‘": "'", "ʼ": "'", "`": "'"}

#: Tout caractère qui n'est ni lettre/chiffre (\w), ni espace, ni apostrophe.
_PUNCT_RE = re.compile(r"[^\w\s']", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+", flags=re.UNICODE)


@dataclass(frozen=True)
class Transformation:
    """Une transformation appliquée à un token lors de la normalisation."""

    source: str
    target: str
    kind: str = "linguistic_variant"

    def as_dict(self) -> dict[str, str]:
        """Représentation JSON conforme à la spec (``from``/``to``/``type``)."""
        return {"from": self.source, "to": self.target, "type": self.kind}


@dataclass(frozen=True)
class NormalizationResult:
    """Trace typée d'une normalisation (interface secondaire, optionnelle)."""

    raw: str
    normalized: str
    transformations: list[Transformation] = field(default_factory=list)


def _canonical_forms(lex: Lexicon) -> frozenset[str]:
    """Toutes les formes canoniques émises par le générateur — jamais réécrites."""
    forms: set[str] = {lex.zero.canonical}
    for unit in lex.units.values():
        forms.add(unit.isolated)
        forms.add(unit.combined)
    for term in lex.tens.values():
        if term.canonical:
            forms.add(term.canonical)
    for term in lex.connectors.values():
        if term.canonical:
            forms.add(term.canonical)
    for scale in lex.scales.values():
        if scale.canonical:
            forms.add(scale.canonical)
    return frozenset(forms)


@lru_cache(maxsize=1)
def _replacement_map() -> dict[str, str]:
    """Map de remplacement : variante non-canonique → forme canonique.

    Dérivée de ``linguistic_variant_map()`` en **excluant** toute forme
    canonique (protégée) et les identités. Dans le lexique v1, cela se réduit
    essentiellement à ``da → nda``.
    """
    lex = load_lexicon()
    variant_map = lex.linguistic_variant_map()
    protected = _canonical_forms(lex)
    return {
        variant: canonical
        for variant, canonical in variant_map.items()
        if variant not in protected and variant != canonical
    }


def _clean(text: str) -> str:
    """Étapes 1–3 : Unicode, apostrophes, minuscules, ponctuation, espaces."""
    text = unicodedata.normalize("NFC", text)
    for typographic, simple in _APOSTROPHES.items():
        text = text.replace(typographic, simple)
    text = text.lower()
    text = _PUNCT_RE.sub(" ", text)
    text = text.replace("_", " ")  # '_' est un caractère \w à éliminer
    text = _WS_RE.sub(" ", text).strip()
    return text


def _normalize_tokens(cleaned: str) -> tuple[str, list[Transformation]]:
    if not cleaned:
        return "", []
    mapping = _replacement_map()
    out_tokens: list[str] = []
    transformations: list[Transformation] = []
    for token in cleaned.split(" "):
        replacement = mapping.get(token)
        if replacement is not None and replacement != token:
            out_tokens.append(replacement)
            transformations.append(Transformation(source=token, target=replacement))
        else:
            out_tokens.append(token)
    return " ".join(out_tokens), transformations


def normalize(text: str) -> str:
    """Interface **primaire** : normalise ``text`` vers sa forme canonique.

    Idempotente : ``normalize(normalize(x)) == normalize(x)``.

    :raises TypeError: si ``text`` n'est pas une chaîne.
    """
    if not isinstance(text, str):
        raise TypeError(f"normalize() attend une chaîne, reçu {type(text).__name__}.")
    normalized, _ = _normalize_tokens(_clean(text))
    return normalized


def normalize_with_trace(text: str) -> NormalizationResult:
    """Interface **secondaire** : normalise et retourne la trace typée.

    N'applique **que** des variantes linguistiques (jamais d'``asr_confusions``).
    """
    if not isinstance(text, str):
        raise TypeError(f"normalize_with_trace() attend une chaîne, reçu {type(text).__name__}.")
    normalized, transformations = _normalize_tokens(_clean(text))
    return NormalizationResult(raw=text, normalized=normalized, transformations=transformations)


__all__ = ["normalize", "normalize_with_trace", "NormalizationResult", "Transformation"]
