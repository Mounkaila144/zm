"""Chargeur et modèle validé du lexique numérique zarma.

Ce module lit ``lexicon.yaml`` (source de vérité versionnée) et le transforme
en un modèle ``Lexicon`` validé et pratique à consommer par le générateur
(story 1.4), le normaliseur (1.5) et le parseur (1.6).

Contraintes d'isolation : stdlib + PyYAML uniquement. Aucune dépendance
FastAPI / httpx / SQLAlchemy / ASR n'est importée ici.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .exceptions import LexiconValidationError

#: Emplacement par défaut du lexique embarqué dans le paquet.
DEFAULT_LEXICON_PATH = Path(__file__).with_name("lexicon.yaml")

#: Vocabulaire de statut autorisé (aligné sur docs/numeration-zarma-v1.md).
VALID_STATUSES = frozenset({"validé", "unresolved"})

#: Catégories requises pour un lexique valide.
REQUIRED_UNIT_KEYS = tuple(range(1, 10))  # 1..9
REQUIRED_TENS_KEYS = tuple(range(10, 100, 10))  # 10..90
REQUIRED_CONNECTOR_KEYS = ("tens_unit", "groups")
REQUIRED_SCALE_KEYS = ("hundred", "thousand", "million")

#: Symboles arithmétiques autorisés pour un opérateur (story 6.1).
VALID_OPERATOR_SYMBOLS = frozenset({"+", "-", "*", "/"})


@dataclass(frozen=True)
class Term:
    """Terme lexical générique : forme canonique + variantes linguistiques."""

    canonical: str | None
    variants: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class Zero:
    value: int
    canonical: str
    variants: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class Unit:
    """Unité 1–9 : formes isolée et combinée + variantes linguistiques."""

    value: int
    isolated: str
    combined: str
    variants: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class Scale:
    """Échelle (100, 1000, …) ; ``canonical`` peut être ``None`` si non résolue."""

    value: int
    canonical: str | None
    variants: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class Operator:
    """Opérateur arithmétique : symbole + forme zarma prononcée (story 6.1).

    ``canonical`` peut être ``None`` : l'opérateur est alors **non résolu** —
    aucune forme n'a été validée par un locuteur natif. Il est dans ce cas
    absent de la grammaire des expressions, exactement comme une échelle non
    résolue est absente de la grammaire des nombres. Jamais de forme inventée.
    """

    name: str
    symbol: str
    canonical: str | None
    variants: tuple[str, ...]
    status: str

    @property
    def resolved(self) -> bool:
        return self.canonical is not None


@dataclass(frozen=True)
class Lexicon:
    """Modèle chargé et validé du lexique numérique zarma.

    Expose ``grammar_version`` (source unique) et des accès distincts pour les
    variantes **linguistiques** (``linguistic_variant_map``) et les corrections
    d'erreurs **ASR** (``asr_confusions``) — jamais fusionnés.
    """

    grammar_version: str
    language: str
    status: str
    zero: Zero
    units: dict[int, Unit]
    tens: dict[int, Term]
    connectors: dict[str, Term]
    scales: dict[str, Scale]
    #: Opérateurs arithmétiques (story 6.1) ; vide si le lexique n'en déclare pas.
    operators: dict[str, Operator]
    #: Corrections d'erreurs acoustiques ASR (forme erronée -> forme correcte).
    #: STRUCTURE DISTINCTE des variantes linguistiques.
    asr_confusions: dict[str, str]

    def resolved_operators(self) -> dict[str, Operator]:
        """Opérateurs dont la forme zarma est résolue — les seuls exploitables."""
        return {name: op for name, op in self.operators.items() if op.resolved}

    def linguistic_variant_map(self) -> dict[str, str]:
        """Map chaque variante **linguistique** vers sa forme canonique.

        Couvre zero, units (isolée/combinée), tens, connectors et scales. Ne
        contient **jamais** les ``asr_confusions`` (corrections acoustiques).
        Destiné à la normalisation (story 1.5).
        """
        mapping: dict[str, str] = {}

        def add(canonical: str | None, variants: tuple[str, ...]) -> None:
            if canonical is None:
                return
            for variant in variants:
                mapping[variant] = canonical

        add(self.zero.canonical, self.zero.variants)
        for unit in self.units.values():
            add(unit.isolated, unit.variants)
        for term in self.tens.values():
            add(term.canonical, term.variants)
        for term in self.connectors.values():
            add(term.canonical, term.variants)
        for scale in self.scales.values():
            add(scale.canonical, scale.variants)
        for operator in self.operators.values():
            add(operator.canonical, operator.variants)
        return mapping


def load_lexicon(path: str | Path | None = None) -> Lexicon:
    """Charge, valide et retourne le lexique.

    :param path: chemin du YAML ; par défaut le lexique embarqué dans le paquet.
    :raises LexiconValidationError: si le fichier est absent, illisible, ou si
        une entrée requise manque / est incohérente (échec « propre »).
    """
    lexicon_path = Path(path) if path is not None else DEFAULT_LEXICON_PATH

    try:
        raw_text = lexicon_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LexiconValidationError(
            f"Lexique introuvable ou illisible : {lexicon_path} ({exc})"
        ) from exc

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise LexiconValidationError(f"YAML invalide dans {lexicon_path} : {exc}") from exc

    if not isinstance(data, dict):
        raise LexiconValidationError("Le lexique doit être un mapping YAML au niveau racine.")

    return _build_lexicon(data)


def _require(data: dict, key: str, expected_type: type, context: str):
    if key not in data:
        raise LexiconValidationError(f"Clé requise manquante : '{key}' dans {context}.")
    value = data[key]
    if not isinstance(value, expected_type):
        raise LexiconValidationError(
            f"'{key}' dans {context} doit être de type {expected_type.__name__}, "
            f"reçu {type(value).__name__}."
        )
    return value


def _validate_status(status: object, context: str) -> str:
    if status not in VALID_STATUSES:
        raise LexiconValidationError(
            f"Statut invalide dans {context} : {status!r} "
            f"(attendu l'un de {sorted(VALID_STATUSES)})."
        )
    return status


def _variants_tuple(entry: dict, context: str) -> tuple[str, ...]:
    variants = entry.get("variants", [])
    if not isinstance(variants, list) or not all(isinstance(v, str) for v in variants):
        raise LexiconValidationError(f"'variants' dans {context} doit être une liste de chaînes.")
    return tuple(variants)


def _build_lexicon(data: dict) -> Lexicon:
    version = _require(data, "version", str, "racine")
    language = _require(data, "language", str, "racine")
    status = _require(data, "status", str, "racine")

    # --- zero ---
    zero_raw = _require(data, "zero", dict, "racine")
    zero = Zero(
        value=int(_require(zero_raw, "value", int, "zero")),
        canonical=_require(zero_raw, "canonical", str, "zero"),
        variants=_variants_tuple(zero_raw, "zero"),
        status=_validate_status(zero_raw.get("status"), "zero"),
    )

    # --- units 1..9 ---
    units_raw = _require(data, "units", dict, "racine")
    units: dict[int, Unit] = {}
    for key in REQUIRED_UNIT_KEYS:
        if key not in units_raw:
            raise LexiconValidationError(f"Unité requise manquante : {key} dans 'units'.")
        entry = units_raw[key]
        if not isinstance(entry, dict):
            raise LexiconValidationError(f"L'unité {key} doit être un mapping.")
        ctx = f"units[{key}]"
        units[key] = Unit(
            value=key,
            isolated=_require(entry, "isolated", str, ctx),
            combined=_require(entry, "combined", str, ctx),
            variants=_variants_tuple(entry, ctx),
            status=_validate_status(entry.get("status"), ctx),
        )

    # --- tens 10..90 ---
    tens_raw = _require(data, "tens", dict, "racine")
    tens: dict[int, Term] = {}
    for key in REQUIRED_TENS_KEYS:
        if key not in tens_raw:
            raise LexiconValidationError(f"Dizaine requise manquante : {key} dans 'tens'.")
        entry = tens_raw[key]
        if not isinstance(entry, dict):
            raise LexiconValidationError(f"La dizaine {key} doit être un mapping.")
        ctx = f"tens[{key}]"
        tens[key] = Term(
            canonical=_require(entry, "canonical", str, ctx),
            variants=_variants_tuple(entry, ctx),
            status=_validate_status(entry.get("status"), ctx),
        )

    # --- connectors (chargés génériquement ; clés requises validées ensuite) ---
    connectors_raw = _require(data, "connectors", dict, "racine")
    connectors: dict[str, Term] = {}
    for key, entry in connectors_raw.items():
        if not isinstance(entry, dict):
            raise LexiconValidationError(f"Le connecteur '{key}' doit être un mapping.")
        ctx = f"connectors[{key}]"
        connectors[key] = Term(
            canonical=_require(entry, "canonical", str, ctx),
            variants=_variants_tuple(entry, ctx),
            status=_validate_status(entry.get("status"), ctx),
        )
    for key in REQUIRED_CONNECTOR_KEYS:
        if key not in connectors:
            raise LexiconValidationError(f"Connecteur requis manquant : '{key}' dans 'connectors'.")

    # --- scales ---
    scales_raw = _require(data, "scales", dict, "racine")
    scales: dict[str, Scale] = {}
    for key, entry in scales_raw.items():
        if not isinstance(entry, dict):
            raise LexiconValidationError(f"L'échelle '{key}' doit être un mapping.")
        ctx = f"scales[{key}]"
        canonical = entry.get("canonical")
        if canonical is not None and not isinstance(canonical, str):
            raise LexiconValidationError(f"'canonical' dans {ctx} doit être une chaîne ou null.")
        scales[key] = Scale(
            value=int(_require(entry, "value", int, ctx)),
            canonical=canonical,
            variants=_variants_tuple(entry, ctx),
            status=_validate_status(entry.get("status"), ctx),
        )
    for key in REQUIRED_SCALE_KEYS:
        if key not in scales:
            raise LexiconValidationError(f"Échelle requise manquante : '{key}' dans 'scales'.")

    # --- operators (story 6.1 ; section optionnelle : un lexique 1.2.x reste lisible) ---
    operators_raw = data.get("operators", {})
    if operators_raw is None:
        operators_raw = {}
    if not isinstance(operators_raw, dict):
        raise LexiconValidationError("'operators' doit être un mapping.")
    operators: dict[str, Operator] = {}
    seen_symbols: dict[str, str] = {}
    seen_forms: dict[str, str] = {}
    for key, entry in operators_raw.items():
        if not isinstance(entry, dict):
            raise LexiconValidationError(f"L'opérateur '{key}' doit être un mapping.")
        ctx = f"operators[{key}]"
        symbol = _require(entry, "symbol", str, ctx)
        if symbol not in VALID_OPERATOR_SYMBOLS:
            raise LexiconValidationError(
                f"Symbole invalide dans {ctx} : {symbol!r} "
                f"(attendu l'un de {sorted(VALID_OPERATOR_SYMBOLS)})."
            )
        if symbol in seen_symbols:
            raise LexiconValidationError(
                f"Symbole {symbol!r} déclaré deux fois : '{seen_symbols[symbol]}' et '{key}'."
            )
        seen_symbols[symbol] = key
        canonical = entry.get("canonical")
        if canonical is not None and not isinstance(canonical, str):
            raise LexiconValidationError(f"'canonical' dans {ctx} doit être une chaîne ou null.")
        variants = _variants_tuple(entry, ctx)
        # Deux opérateurs ne peuvent pas partager une forme prononcée : sinon
        # l'expression entendue serait ambiguë et l'évaluation, indécidable.
        for form in ({canonical} if canonical else set()) | set(variants):
            if form in seen_forms and seen_forms[form] != key:
                raise LexiconValidationError(
                    f"Forme d'opérateur ambiguë : {form!r} déclarée pour "
                    f"'{seen_forms[form]}' et '{key}'."
                )
            seen_forms[form] = key
        operators[key] = Operator(
            name=key,
            symbol=symbol,
            canonical=canonical,
            variants=variants,
            status=_validate_status(entry.get("status"), ctx),
        )

    # --- asr_confusions (structure DISTINCTE, optionnelle) ---
    asr_raw = data.get("asr_confusions", {})
    if asr_raw is None:
        asr_raw = {}
    if not isinstance(asr_raw, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in asr_raw.items()
    ):
        raise LexiconValidationError("'asr_confusions' doit être un mapping chaîne -> chaîne.")
    asr_confusions = dict(asr_raw)

    return Lexicon(
        grammar_version=version,
        language=language,
        status=status,
        zero=zero,
        units=units,
        tens=tens,
        connectors=connectors,
        scales=scales,
        operators=operators,
        asr_confusions=asr_confusions,
    )


__all__ = [
    "Lexicon",
    "Operator",
    "Term",
    "Unit",
    "Zero",
    "Scale",
    "load_lexicon",
    "DEFAULT_LEXICON_PATH",
    "VALID_STATUSES",
    "VALID_OPERATOR_SYMBOLS",
]
