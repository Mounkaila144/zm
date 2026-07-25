"""Pont décodage contraint → contrat ``POST /transcribe`` (story 5.6, task 4).

Ce module transforme un ``DecodeResult`` en la charge utile JSON déjà attendue
par ``RemoteCtcRecognizer`` côté API — **contrat inchangé** (NFR9) :

    { text, acoustic_score, candidates[], latency_ms, model_version }

Deux règles structurantes :

- **Aucun logit ne sort du recognizer.** Le décodage a lieu là où les logits
  existent (service ASR) ; seule la forme canonique et des scores bornés
  traversent le réseau (Annexe D §4 : ``T × 10 288`` flottants seraient une
  charge utile absurde et un couplage contraire à NFR9).
- **Jamais de nombre inventé (FR21).** Sous le seuil de rejet, le service
  renvoie un **texte vide** — exactement comme un ASR en échec. Le pipeline API
  en déduit ``number is None`` → ``repeat``, via la politique **existante** :
  aucun second système de décision n'est introduit.

Le score exposé (``acoustic_score``) est la **confiance de décodage** de la
task 3 (rapport de vraisemblance par trame entre chemin contraint et chemin
libre). C'est l'amélioration substantielle apportée par cette story : l'API
haut-niveau d'Omnilingual ne fournit aucun score et le prototype mettait
``1.0`` en dur, rendant les signaux de marge et de confusion inopérants.

Module **sans torch ni modal** : testable en CI sans GPU.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - annotations seulement
    from .decoding import DecodeResult


def _clamp_unit(value: float) -> float:
    """Borne dans ``[0, 1]`` — le contrat ``AsrResult`` l'exige."""
    return max(0.0, min(1.0, float(value)))


def build_transcribe_payload(
    result: DecodeResult,
    *,
    model_version: str,
    latency_ms: int,
) -> dict[str, object]:
    """Assemble la réponse ``/transcribe`` à partir du décodage contraint.

    :param result: sortie du décodeur contraint (hypothèses + signal de rejet).
    :param model_version: identifiant du modèle acoustique (traçabilité, NFR12).
    :param latency_ms: latence **totale** du service (inférence + décodage).
    """
    if result.rejected:
        # Abstention explicite : le pipeline API décidera ``repeat`` (FR21).
        return {
            "text": "",
            "acoustic_score": _clamp_unit(result.confidence),
            "candidates": [],
            "latency_ms": latency_ms,
            "model_version": model_version,
            "decode_frames": result.frame_count,
            "decode_latency_ms": result.latency_ms,
            "rejected": True,
        }

    best = result.best
    assert best is not None  # garanti par `rejected` ci-dessus
    return {
        "text": best.text,
        "acoustic_score": _clamp_unit(best.confidence),
        # Les alternatives alimentent le signal de **marge** de la confiance
        # composite : sans elles, la marge vaut 1.0 par défaut (inopérante).
        "candidates": [
            {"text": hypothesis.text, "score": _clamp_unit(hypothesis.confidence)}
            for hypothesis in result.hypotheses[1:]
        ],
        "latency_ms": latency_ms,
        "model_version": model_version,
        "decode_frames": result.frame_count,
        "decode_latency_ms": result.latency_ms,
        "rejected": False,
    }


__all__ = ["build_transcribe_payload"]
