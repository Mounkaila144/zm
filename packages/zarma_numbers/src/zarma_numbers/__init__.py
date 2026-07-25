"""Paquet ``zarma_numbers`` — cœur déterministe texte↔nombre en zarma.

Ce paquet est **autonome** et **sans GPU** : il ne doit jamais importer
FastAPI, httpx, SQLAlchemy ni aucune dépendance ASR (isolation du moteur
linguistique). Il expose le pipeline complet : ``load_lexicon``, ``generate``
(nombre→zarma), ``normalize`` (texte→canonique), ``parse`` (zarma→nombre) et
``validate_invariant`` (preuve ``parse(generate(n)) == n``).
"""

from .exceptions import (
    GenerationError,
    GrammarDerivationError,
    LexiconError,
    LexiconValidationError,
    OutOfRangeError,
    ParseError,
    UnresolvedFormError,
)
from .generator import generate
from .grammar import NumberGrammar, build_grammar, load_grammar
from .loader import Lexicon, load_lexicon
from .normalizer import NormalizationResult, normalize, normalize_with_trace
from .parser import ParseCandidate, ParseResult, parse, parse_detailed
from .validator import InvariantReport, validate_invariant

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "Lexicon",
    "load_lexicon",
    "generate",
    "normalize",
    "normalize_with_trace",
    "NormalizationResult",
    "parse",
    "parse_detailed",
    "ParseResult",
    "ParseCandidate",
    "validate_invariant",
    "InvariantReport",
    "NumberGrammar",
    "build_grammar",
    "load_grammar",
    "LexiconError",
    "LexiconValidationError",
    "GenerationError",
    "OutOfRangeError",
    "UnresolvedFormError",
    "GrammarDerivationError",
    "ParseError",
]
