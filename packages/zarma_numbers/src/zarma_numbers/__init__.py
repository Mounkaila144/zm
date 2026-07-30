"""Paquet ``zarma_numbers`` — cœur déterministe texte↔nombre en zarma.

Ce paquet est **autonome** et **sans GPU** : il ne doit jamais importer
FastAPI, httpx, SQLAlchemy ni aucune dépendance ASR (isolation du moteur
linguistique). Il expose le pipeline complet : ``load_lexicon``, ``generate``
(nombre→zarma), ``normalize`` (texte→canonique), ``parse`` (zarma→nombre) et
``validate_invariant`` (preuve ``parse(generate(n)) == n``).
"""

from .exceptions import (
    DomainError,
    ExpressionParseError,
    GenerationError,
    GrammarDerivationError,
    LexiconError,
    LexiconValidationError,
    OutOfRangeError,
    ParseError,
    UnresolvedFormError,
)
from .expressions import (
    Expression,
    ExpressionParseResult,
    ExpressionResult,
    evaluate,
    evaluate_text,
    parse_expression,
    parse_expression_detailed,
    render_expression,
    render_result,
    supported_operators,
)
from .generator import MAX_VALUE, MIN_VALUE, generate, generate_combined
from .grammar import (
    NumberGrammar,
    build_calculator_grammar,
    build_expression_grammar,
    build_grammar,
    load_calculator_grammar,
    load_expression_grammar,
    load_grammar,
)
from .loader import Lexicon, Operator, load_lexicon
from .normalizer import NormalizationResult, normalize, normalize_with_trace
from .parser import ParseCandidate, ParseResult, parse, parse_detailed
from .validator import InvariantReport, validate_invariant

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "Lexicon",
    "Operator",
    "load_lexicon",
    "generate",
    "generate_combined",
    "MAX_VALUE",
    "MIN_VALUE",
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
    "build_expression_grammar",
    "build_calculator_grammar",
    "load_calculator_grammar",
    "load_grammar",
    "load_expression_grammar",
    "Expression",
    "ExpressionResult",
    "ExpressionParseResult",
    "parse_expression",
    "parse_expression_detailed",
    "evaluate",
    "evaluate_text",
    "render_expression",
    "render_result",
    "supported_operators",
    "LexiconError",
    "LexiconValidationError",
    "GenerationError",
    "OutOfRangeError",
    "UnresolvedFormError",
    "GrammarDerivationError",
    "ParseError",
    "ExpressionParseError",
    "DomainError",
]
