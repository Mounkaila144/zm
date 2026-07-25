"""Exceptions du paquet ``zarma_numbers``.

Hiérarchie volontairement minimale et autonome (aucune dépendance externe).
"""


class LexiconError(Exception):
    """Erreur de base liée au lexique (chargement, accès)."""


class LexiconValidationError(LexiconError):
    """Le lexique est structurellement invalide ou incohérent.

    Levée par le chargeur quand une entrée requise manque, qu'un type est
    incohérent, ou qu'un statut n'appartient pas au vocabulaire autorisé.
    Le message doit indiquer précisément la cause pour un échec « propre ».
    """


class GenerationError(Exception):
    """Erreur de base du générateur ``nombre → zarma``.

    Porte un ``code`` machine-lisible (ex. ``OUT_OF_RANGE``) en plus du message.
    """

    default_code = "GENERATION_ERROR"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.default_code


class OutOfRangeError(GenerationError):
    """Le nombre demandé est hors de la plage supportée ``[0, 1 000 000]``."""

    default_code = "OUT_OF_RANGE"


class UnresolvedFormError(GenerationError):
    """La forme requise n'est pas résolue dans le lexique (``canonical: null``).

    Le générateur **refuse** plutôt que d'inventer une forme (ex. le million).
    """

    default_code = "UNRESOLVED_FORM"


class GrammarDerivationError(Exception):
    """La grammaire des formes valides n'a pas pu être dérivée du générateur.

    Levée par ``grammar.py`` quand une observation du générateur contredit la
    structure attendue (préfixe inattendu, langues incohérentes, prononciation
    ambiguë). On **échoue proprement** plutôt que de coder une règle en dur.
    """


class ParseError(Exception):
    """Échec d'analyse d'un texte zarma vers un nombre.

    Utilisée **en interne** par le parseur : ``parse()`` la capture et retourne
    ``None`` (absence explicite) ; ``parse_detailed()`` expose son ``code``.
    Le parseur ne devine **jamais** un nombre — un texte non numérique/ambigu
    produit une ``ParseError``, jamais une valeur arbitraire.
    """

    default_code = "PARSE_ERROR"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.default_code


__all__ = [
    "LexiconError",
    "LexiconValidationError",
    "GenerationError",
    "OutOfRangeError",
    "UnresolvedFormError",
    "GrammarDerivationError",
    "ParseError",
]
