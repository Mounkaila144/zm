"""Détection de la dérive de grammaire entre le service ASR et l'API.

Pourquoi ce module existe
-------------------------

Le décodeur contraint (service ASR) et l'analyseur (``zarma_numbers`` côté API)
sont deux processus séparés, chacun avec **sa propre copie** du paquet
linguistique en mémoire. Ils ne partagent que le texte qui transite par
``/transcribe``.

Quand les deux versions divergent, le décodeur émet des mots que l'analyseur ne
sait pas lire. ``parse``/``parse_expression`` renvoient ``None``, et la politique
sort immédiatement sur ``repeat`` — **avant même de regarder la confiance**.
L'utilisateur voit « je n'ai pas compris » sur *chaque* énoncé.

Ce qui rend la panne coûteuse, c'est qu'elle est silencieuse :

- les deux services répondent ``200`` ;
- les deux sondes de santé sont vertes ;
- aucune exception n'est levée, aucun log d'erreur n'apparaît ;
- le modèle acoustique est innocent et le prouve (confiances à 0,9+).

C'est arrivé en production le 2026-07-30 : le service ASR avait été redémarré
après un déploiement, l'API non. Elle a servi des ``repeat`` pendant des heures
avec, en mémoire, un analyseur vieux d'une journée. Le diagnostic a demandé de
remonter jusqu'aux lignes de la table ``recognitions``.

Politique retenue : **signaler fort, ne pas refuser de servir**
---------------------------------------------------------------

Une divergence ne fait pas échouer les requêtes. Refuser de servir
transformerait une dégradation en panne totale, y compris dans les cas où les
deux versions restent compatibles (un changement de lexique qui ne touche pas
les mots utilisés). On journalise donc au niveau ``error``, une seule fois par
version distincte observée — assez pour alerter, sans inonder le journal — et on
expose l'état sur ``/health``, où un opérateur ou une supervision le voit sans
avoir à interroger la base.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import httpx
import zarma_numbers
from structlog import get_logger

from app.config import Settings

log = get_logger("zarma.asr")


@dataclass(frozen=True, slots=True)
class GrammarMismatch:
    """Divergence constatée entre la grammaire de l'ASR et celle de l'API."""

    api_grammar_version: str
    #: Version annoncée par l'ASR ; ``""`` s'il ne la rapporte pas (service
    #: antérieur à cette vérification — cas indiscernable d'une vraie dérive).
    asr_grammar_version: str

    @property
    def reason(self) -> str:
        return "asr_version_unreported" if not self.asr_grammar_version else "version_drift"


@lru_cache(maxsize=1)
def api_grammar_version() -> str:
    """Version du lexique chargée par **ce** processus API.

    Mémorisée : elle ne peut pas changer sans redémarrage, et c'est précisément
    ce que le module cherche à mettre en évidence.
    """
    return zarma_numbers.load_lexicon().grammar_version


#: Dernière divergence observée, ``None`` tant que tout concorde. État par
#: processus : avec plusieurs workers uvicorn, chacun tient le sien, ce qui est
#: correct — c'est bien par processus que la grammaire est chargée.
_mismatch: GrammarMismatch | None = None
_reported: set[str] = set()


def check(asr_grammar_version: str) -> GrammarMismatch | None:
    """Compare la version annoncée par l'ASR à celle de l'API.

    Journalise au plus une fois par version distincte reçue. Ne lève jamais :
    une garde qui casse le chemin nominal serait pire que la panne qu'elle
    surveille.
    """
    global _mismatch

    expected = api_grammar_version()
    if asr_grammar_version == expected:
        _mismatch = None
        return None

    mismatch = GrammarMismatch(
        api_grammar_version=expected,
        asr_grammar_version=asr_grammar_version,
    )
    _mismatch = mismatch
    if asr_grammar_version not in _reported:
        _reported.add(asr_grammar_version)
        log.error(
            "asr.grammar_version_mismatch",
            api_grammar_version=expected,
            asr_grammar_version=asr_grammar_version or None,
            reason=mismatch.reason,
            remediation=(
                "Les deux services n'ont pas le même paquet linguistique en mémoire. "
                "Redémarrer celui qui n'a pas été relancé après le dernier déploiement "
                "(systemctl restart zarma-api zarma-asr)."
            ),
        )
    return mismatch


async def probe(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> GrammarMismatch | None:
    """Interroge ``/health`` de l'ASR au démarrage et compare les grammaires.

    Sans cette sonde, une divergence n'apparaît qu'à la **première requête
    utilisateur** — c'est-à-dire une fois la panne déjà servie. Ici elle apparaît
    dans ``journalctl -u zarma-api`` dans les secondes qui suivent un déploiement,
    au moment précis où l'on peut encore corriger.

    N'échoue jamais : l'API doit démarrer même ASR éteint (le pipeline retombe
    alors sur ``repeat`` plutôt que d'inventer un nombre, FR21). Une sonde qui
    empêcherait le démarrage serait une régression de disponibilité.

    ``transport`` permet d'injecter un ``httpx.MockTransport`` en test, comme le
    fait déjà ``_RemoteRecognizer`` — aucun réseau dans la CI.
    """
    if settings.ASR_MODE == "mock" or not settings.ASR_ENDPOINT_URL:
        return None

    endpoint = settings.ASR_ENDPOINT_URL.rstrip("/")
    headers = (
        {"Authorization": f"Bearer {settings.ASR_ENDPOINT_TOKEN}"}
        if settings.ASR_ENDPOINT_TOKEN
        else {}
    )
    try:
        async with httpx.AsyncClient(timeout=5.0, transport=transport) as client:
            response = await client.get(f"{endpoint}/health", headers=headers)
            response.raise_for_status()
            reported = str(response.json().get("grammar_version") or "")
    except (httpx.HTTPError, ValueError) as exc:
        # L'ASR peut démarrer plus lentement que l'API (chargement du modèle) :
        # ne rien conclure d'une sonde injoignable.
        log.info("asr.grammar_probe_skipped", error=type(exc).__name__)
        return None

    mismatch = check(reported)
    if mismatch is None:
        log.info("asr.grammar_version_agreed", grammar_version=reported)
    return mismatch


def current_mismatch() -> GrammarMismatch | None:
    """Dernière divergence observée, pour la sonde de santé."""
    return _mismatch


def reset() -> None:
    """Réinitialise l'état — réservé aux tests."""
    global _mismatch
    _mismatch = None
    _reported.clear()
    api_grammar_version.cache_clear()


__all__ = [
    "GrammarMismatch",
    "api_grammar_version",
    "check",
    "current_mismatch",
    "probe",
    "reset",
]
