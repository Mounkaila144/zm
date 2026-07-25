"""Tests du mécanisme de rejet et du pont ``/transcribe`` (story 5.6, tasks 3-4).

Sans GPU ni modèle : logits synthétiques + fixtures d'entrées non numériques.

Ce qui est prouvé ici :

- le signal de rejet est un **rapport de vraisemblance** borné, calibré par
  trame, élevé sur un nombre net et bas sur du bruit / silence / parole
  quelconque ;
- sous le seuil, le décodeur **s'abstient** — le service renvoie un texte vide,
  jamais un nombre (FR21) ;
- le signal alimente ``AsrResult.acoustic_score`` et les ``candidates`` de la
  confiance composite **existante** : aucun second système de décision.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from zarma_numbers.generator import generate
from zarma_numbers.grammar import load_grammar
from zarma_numbers.parser import parse

_ALPHABET = "abcdefghijklmnopqrstuvwxyz "
_CHAR_TO_ID = {char: 4 + i for i, char in enumerate(_ALPHABET)}
_VOCAB_SIZE = 4 + len(_ALPHABET) + 3
_BLANK = 0
_SPACE_ID = _CHAR_TO_ID[" "]


def _toy_encode(text: str) -> list[int]:
    return [_CHAR_TO_ID[char] for char in text]


def _clean_logits(text: str, *, frames_per_token: int = 2, strength: float = 8.0) -> np.ndarray:
    """Énoncé net : la chaîne ``text`` domine largement à chaque trame."""
    ids = _toy_encode(text)
    frame_ids: list[int] = []
    for token_id in ids:
        frame_ids.extend([token_id] * frames_per_token)
        frame_ids.append(_BLANK)
    logits = np.zeros((len(frame_ids), _VOCAB_SIZE))
    for t, token_id in enumerate(frame_ids):
        logits[t, token_id] += strength
    return logits


# --- Fixtures d'entrées NON numériques (task 3 : « constituer des fixtures ») ---


def _noise_logits(frames: int = 40, seed: int = 11) -> np.ndarray:
    """Bruit : aucune structure, distribution large et aléatoire."""
    return np.random.default_rng(seed).normal(0.0, 4.0, size=(frames, _VOCAB_SIZE))


def _silence_logits(frames: int = 40) -> np.ndarray:
    """Silence : le blank domine partout (le modèle n'émet rien)."""
    logits = np.zeros((frames, _VOCAB_SIZE))
    logits[:, _BLANK] = 10.0
    return logits


def _music_logits(frames: int = 60, seed: int = 12) -> np.ndarray:
    """Musique : structure périodique sur des tokens hors grammaire."""
    rng = np.random.default_rng(seed)
    logits = rng.normal(0.0, 1.0, size=(frames, _VOCAB_SIZE))
    # Tokens jamais utilisés par le lexique de décodage (fin du vocabulaire).
    for t in range(frames):
        logits[t, _VOCAB_SIZE - 1 - (t % 3)] += 9.0
    return logits


def _non_numeric_speech_logits() -> np.ndarray:
    """Parole quelconque : des lettres nettes, mais pas un nombre zarma."""
    return _clean_logits("kala suba borey ga koy")


_NON_NUMERIC = {
    "bruit": _noise_logits,
    "silence": _silence_logits,
    "musique": _music_logits,
    "parole_non_numerique": _non_numeric_speech_logits,
}


@pytest.fixture(scope="module")
def grammar():
    return load_grammar()


@pytest.fixture(scope="module")
def lexicon(decoding, grammar):
    return decoding.build_token_lexicon(
        grammar, _toy_encode, separator=(_SPACE_ID,), blank_id=_BLANK
    )


@pytest.fixture(scope="module")
def decoder(decoding, grammar, lexicon):
    return decoding.ConstrainedCtcDecoder(grammar, lexicon)


# --- AC3 : le signal de rejet ---


def test_free_path_is_a_lower_bound_on_nll(decoding):
    rng = np.random.default_rng(3)
    log_probs = decoding.log_softmax(rng.normal(size=(12, 20)))
    free = decoding.free_path_nll(log_probs)
    # Aucune séquence contrainte ne peut être plus probable que le chemin libre.
    for ids in ([4], [4, 5], [6, 7, 8]):
        assert decoding.ctc_forward_score(log_probs, ids, _BLANK) >= free - 1e-9


def test_confidence_is_bounded_and_monotone(decoding):
    assert decoding.decoding_confidence(10.0, 10.0, 20) == 1.0
    assert decoding.decoding_confidence(9.0, 10.0, 20) == 1.0  # borné à 1
    close = decoding.decoding_confidence(12.0, 10.0, 20)
    far = decoding.decoding_confidence(60.0, 10.0, 20)
    assert 0.0 < far < close < 1.0
    assert decoding.decoding_confidence(math.inf, 10.0, 20) == 0.0
    assert decoding.decoding_confidence(10.0, 10.0, 0) == 0.0


def test_confidence_normalizes_per_token_not_per_frame(decoding):
    """Le coût est amorti par **symbole émis**, pas par la durée de l'audio.

    Sinon une courte insertion dans un long silence paraît anodine : mesuré,
    ``afo`` inséré dans 40 trames de silence obtenait 0,59 par trame contre
    0,001 par token.
    """
    gap_nll, free = 30.0, 0.0
    assert decoding.decoding_confidence(gap_nll, free, 3) < 0.01
    # Un même écart réparti sur beaucoup plus de tokens coûte moins par token.
    assert decoding.decoding_confidence(gap_nll, free, 30) > decoding.decoding_confidence(
        gap_nll, free, 3
    )


def test_confidence_is_high_on_a_clean_number(decoder):
    result = decoder.decode(_clean_logits(generate(42)))
    assert result.best is not None
    assert result.best.text == generate(42)
    assert result.confidence > 0.8


@pytest.mark.parametrize("name", sorted(_NON_NUMERIC))
def test_confidence_is_lower_on_non_numeric_input(decoder, name):
    numeric = decoder.decode(_clean_logits(generate(42))).confidence
    non_numeric = decoder.decode(_NON_NUMERIC[name]()).confidence
    assert non_numeric < numeric, f"{name} : confiance {non_numeric} ≥ nombre net {numeric}"


def test_result_exposes_the_reference_and_threshold(decoder):
    result = decoder.decode(_clean_logits("afo"))
    assert result.free_path_nll >= 0.0
    assert result.reject_threshold == decoder.config.reject_threshold
    assert result.frame_count > 0


# --- AC3/FR21 : sous le seuil, jamais un nombre ---


@pytest.mark.parametrize("name", sorted(_NON_NUMERIC))
def test_non_numeric_input_never_yields_a_number(decoding, grammar, lexicon, name):
    # Seuil volontairement strict : tout ce qui n'est pas franchement un nombre
    # est rejeté. La valeur réelle se calibre hors du split de test (task 3).
    config = decoding.DecoderConfig(reject_threshold=0.5)
    strict = decoding.ConstrainedCtcDecoder(grammar, lexicon, config)
    result = strict.decode(_NON_NUMERIC[name]())
    assert result.rejected, f"{name} : confiance {result.confidence} non rejetée"


def test_clean_number_survives_the_same_threshold(decoding, grammar, lexicon):
    config = decoding.DecoderConfig(reject_threshold=0.5)
    strict = decoding.ConstrainedCtcDecoder(grammar, lexicon, config)
    for n in (0, 7, 42, 372, 1234):
        result = strict.decode(_clean_logits(generate(n)))
        assert not result.rejected, f"n={n} rejeté à tort (confiance {result.confidence})"
        assert parse(result.best.text) == n


def test_no_hypothesis_means_rejected(decoder):
    result = decoder.decode(np.zeros((0, _VOCAB_SIZE)))
    assert result.rejected
    assert result.confidence == 0.0


def test_default_threshold_never_rejects(decoder):
    # Défaut = 0.0 : le décodeur expose le signal sans trancher tant que le
    # seuil n'est pas calibré (un seuil non calibré serait pire que rien).
    assert decoder.config.reject_threshold == 0.0
    assert not decoder.decode(_noise_logits()).rejected


# --- AC5 / task 4 : pont vers le contrat /transcribe ---


def test_payload_carries_canonical_text_and_real_scores(decoder, transcription):
    result = decoder.decode(_clean_logits(generate(372)))
    payload = transcription.build_transcribe_payload(
        result, model_version="omniASR_CTC_300M_v2", latency_ms=123
    )
    assert payload["text"] == generate(372)
    assert 0.0 <= payload["acoustic_score"] <= 1.0
    # Le prototype mettait 1.0 en dur : le score doit désormais être réel.
    assert payload["acoustic_score"] == pytest.approx(result.best.confidence)
    assert payload["latency_ms"] == 123
    assert payload["model_version"] == "omniASR_CTC_300M_v2"
    assert payload["rejected"] is False


def test_payload_candidates_feed_the_margin_signal(decoder, transcription):
    result = decoder.decode(_clean_logits("waranka cindi hinza"))
    payload = transcription.build_transcribe_payload(
        result, model_version="omniASR_CTC_300M_v2", latency_ms=10
    )
    assert len(payload["candidates"]) == len(result.hypotheses) - 1
    for candidate in payload["candidates"]:
        assert set(candidate) == {"text", "score"}
        assert 0.0 <= candidate["score"] <= 1.0


def test_rejected_payload_is_empty_text_never_a_number(decoding, grammar, lexicon, transcription):
    config = decoding.DecoderConfig(reject_threshold=0.99)
    strict = decoding.ConstrainedCtcDecoder(grammar, lexicon, config)
    result = strict.decode(_noise_logits())
    payload = transcription.build_transcribe_payload(
        result, model_version="omniASR_CTC_300M_v2", latency_ms=10
    )
    assert payload["text"] == ""
    assert payload["candidates"] == []
    assert payload["rejected"] is True
    # Le pipeline API en déduit number is None → repeat (politique existante).
    assert parse(payload["text"]) is None


def test_payload_never_exposes_logits(decoder, transcription):
    result = decoder.decode(_clean_logits("afo"))
    payload = transcription.build_transcribe_payload(
        result, model_version="omniASR_CTC_300M_v2", latency_ms=1
    )
    serialized = str(payload)
    assert "logits" not in serialized
    assert set(payload) == {
        "text",
        "acoustic_score",
        "candidates",
        "latency_ms",
        "model_version",
        "decode_frames",
        "decode_latency_ms",
        "rejected",
    }


def test_payload_matches_the_api_asr_result_contract(decoder, transcription):
    """La charge utile doit se mapper telle quelle sur ``AsrResult`` (NFR9)."""
    from app.asr.base import AsrResult, Candidate

    result = decoder.decode(_clean_logits(generate(101)))
    payload = transcription.build_transcribe_payload(
        result, model_version="omniASR_CTC_300M_v2", latency_ms=42
    )
    mapped = AsrResult(
        text=payload["text"],
        acoustic_score=payload["acoustic_score"],
        candidates=[Candidate(text=c["text"], score=c["score"]) for c in payload["candidates"]],
        latency_ms=payload["latency_ms"],
        model_version=payload["model_version"],
    )
    assert mapped.text == generate(101)
    assert 0.0 <= mapped.acoustic_score <= 1.0


def test_constrained_result_flows_through_the_existing_pipeline(decoder, transcription):
    """Le signal alimente la confiance composite et la politique **existantes**."""
    from app.asr.base import AsrResult, Candidate
    from app.config import Settings
    from app.pipeline.recognition import run_recognition_pipeline

    settings = Settings()
    result = decoder.decode(_clean_logits(generate(42)))
    payload = transcription.build_transcribe_payload(
        result, model_version="omniASR_CTC_300M_v2", latency_ms=5
    )
    asr = AsrResult(
        text=payload["text"],
        acoustic_score=payload["acoustic_score"],
        candidates=[Candidate(text=c["text"], score=c["score"]) for c in payload["candidates"]],
        latency_ms=payload["latency_ms"],
        model_version=payload["model_version"],
    )
    outcome = run_recognition_pipeline(asr, settings)
    assert outcome.number == 42
    assert outcome.decision in ("accept", "confirm")


def test_rejected_result_yields_repeat_through_the_existing_policy(
    decoding, grammar, lexicon, transcription
):
    from app.asr.base import AsrResult
    from app.config import Settings
    from app.pipeline.recognition import run_recognition_pipeline

    config = decoding.DecoderConfig(reject_threshold=0.99)
    strict = decoding.ConstrainedCtcDecoder(grammar, lexicon, config)
    payload = transcription.build_transcribe_payload(
        strict.decode(_noise_logits()), model_version="omniASR_CTC_300M_v2", latency_ms=5
    )
    outcome = run_recognition_pipeline(
        AsrResult(
            text=payload["text"],
            acoustic_score=payload["acoustic_score"],
            candidates=[],
            latency_ms=payload["latency_ms"],
            model_version=payload["model_version"],
        ),
        Settings(),
    )
    assert outcome.number is None
    assert outcome.decision == "repeat"
