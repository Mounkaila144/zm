"""Endpoint ``GET /api/v1/grammar/version`` — traçabilité de la grammaire.

``grammar_version`` **provient du lexique** (``zarma_numbers.load_lexicon()``),
jamais d'une constante en dur ni de ``settings.GRAMMAR_VERSION`` : le paquet
linguistique est l'unique source de vérité (NFR12 — versions systématiques).

``validated_count`` et ``unresolved_items`` sont dérivés des statuts des entrées
du ``Lexicon`` (tant que la validation locuteurs natifs n'a pas eu lieu, toutes
les entrées sont ``unresolved``).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from zarma_numbers import (
    MAX_VALUE,
    Lexicon,
    OutOfRangeError,
    UnresolvedFormError,
    generate,
    load_lexicon,
)

from app.core.errors import ApiError, api_error_response, request_id_from

#: Statut marquant une entrée validée par des locuteurs natifs.
VALIDATED_STATUS = "validé"

router = APIRouter(tags=["grammar"])


class GrammarVersionInfo(BaseModel):
    grammar_version: str
    validated_count: int
    unresolved_items: list[str]


class GrammarGenerateResponse(BaseModel):
    """Forme zarma canonique d'un nombre, versionnée par le lexique."""

    number: int
    zarma_text: str
    grammar_version: str


def _iter_entry_statuses(lexicon: Lexicon) -> list[tuple[str, str]]:
    """Énumère ``(label, status)`` pour toutes les entrées du lexique.

    Ordre stable : zero, unités (1–9), dizaines (10–90), connecteurs (ordre du
    lexique), échelles (par valeur croissante). Le ``label`` identifie l'entrée
    (valeur numérique pour zero/unités/dizaines/échelles ; clé pour connecteurs).
    """
    entries: list[tuple[str, str]] = [(str(lexicon.zero.value), lexicon.zero.status)]
    entries += [(str(v), lexicon.units[v].status) for v in sorted(lexicon.units)]
    entries += [(str(v), lexicon.tens[v].status) for v in sorted(lexicon.tens)]
    entries += [(key, term.status) for key, term in lexicon.connectors.items()]
    entries += [
        (str(scale.value), scale.status)
        for scale in sorted(lexicon.scales.values(), key=lambda s: s.value)
    ]
    return entries


def build_grammar_info() -> GrammarVersionInfo:
    lexicon = load_lexicon()
    statuses = _iter_entry_statuses(lexicon)
    validated_count = sum(1 for _, status in statuses if status == VALIDATED_STATUS)
    unresolved_items = [label for label, status in statuses if status != VALIDATED_STATUS]
    return GrammarVersionInfo(
        grammar_version=lexicon.grammar_version,
        validated_count=validated_count,
        unresolved_items=unresolved_items,
    )


@router.get(
    "/grammar/version",
    response_model=GrammarVersionInfo,
    summary="Version de grammaire et statut de validation",
)
def grammar_version() -> GrammarVersionInfo:
    return build_grammar_info()


@router.get(
    "/grammar/generate/{number}",
    response_model=GrammarGenerateResponse,
    summary="Forme zarma canonique d'un nombre",
    responses={
        400: {"model": ApiError, "description": "Nombre hors plage"},
        422: {"model": ApiError, "description": "Forme indisponible"},
    },
)
def grammar_generate(
    request: Request,
    number: int,
) -> GrammarGenerateResponse | JSONResponse:
    """Génère la forme zarma via ``zarma_numbers`` (source unique de vérité).

    Aucune règle numérique n'est recalculée ici : bornes et forme proviennent
    exclusivement du moteur linguistique.
    """

    request_id = request_id_from(request)
    try:
        zarma_text = generate(number)
    except OutOfRangeError:
        return api_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="OUT_OF_RANGE",
            # Borne issue du moteur (source unique), jamais recopiée en dur.
            message=f"Nombre hors plage. Utilisez un nombre entre 0 et {MAX_VALUE:,}.".replace(
                ",", " "
            ),
            request_id=request_id,
        )
    except UnresolvedFormError:
        return api_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="UNRESOLVED_FORM",
            message="Ce nombre n'a pas encore de forme zarma disponible.",
            request_id=request_id,
        )
    return GrammarGenerateResponse(
        number=number,
        zarma_text=zarma_text,
        grammar_version=load_lexicon().grammar_version,
    )
