"""La dérive de grammaire entre l'API et l'ASR doit être détectée et visible.

Panne de référence (production, 2026-07-30) : le service ASR redémarré après un
déploiement, l'API non. Le décodeur émettait `kalangaybor` / `kanga itonton`, que
l'analyseur figé de l'API ne savait pas lire — donc `repeat` sur chaque énoncé,
avec deux services en `200 OK` et aucune trace d'erreur. Ces tests verrouillent
la détection de ce scénario exact.
"""

from __future__ import annotations

import httpx
import pytest
import zarma_numbers
from app.asr import grammar_guard
from app.asr.base import AudioInput
from app.asr.remote import RemoteCtcRecognizer
from app.config import Settings


@pytest.fixture(autouse=True)
def _clean_guard():
    grammar_guard.reset()
    yield
    grammar_guard.reset()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        ASR_MODE="ctc",
        ASR_ENDPOINT_URL="https://asr.invalid",
        ASR_ENDPOINT_TOKEN="secret",
    )


def _transcribe_transport(grammar_version: str | None) -> httpx.MockTransport:
    payload = {
        "text": "zambar fo kalangaybor ihinza",
        "acoustic_score": 0.9,
        "candidates": [],
        "latency_ms": 12,
        "model_version": "zarma_w2v2_modele",
    }
    if grammar_version is not None:
        payload["grammar_version"] = grammar_version

    return httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))


def test_versions_identiques_aucune_derive(settings: Settings) -> None:
    current = zarma_numbers.load_lexicon().grammar_version
    recognizer = RemoteCtcRecognizer(settings, transport=_transcribe_transport(current))

    result = recognizer.transcribe(AudioInput(data=b"\x00\x00", format="pcm_s16le"))

    assert result.grammar_version == current
    assert grammar_guard.current_mismatch() is None


def test_version_differente_signale_une_derive(settings: Settings) -> None:
    recognizer = RemoteCtcRecognizer(settings, transport=_transcribe_transport("0.0.1-ancienne"))

    recognizer.transcribe(AudioInput(data=b"\x00\x00", format="pcm_s16le"))

    mismatch = grammar_guard.current_mismatch()
    assert mismatch is not None
    assert mismatch.asr_grammar_version == "0.0.1-ancienne"
    assert mismatch.api_grammar_version == zarma_numbers.load_lexicon().grammar_version
    assert mismatch.reason == "version_drift"


def test_asr_muet_sur_sa_version_est_signale(settings: Settings) -> None:
    """Un ASR qui ne rapporte rien est indiscernable d'un ASR périmé : on alerte."""
    recognizer = RemoteCtcRecognizer(settings, transport=_transcribe_transport(None))

    recognizer.transcribe(AudioInput(data=b"\x00\x00", format="pcm_s16le"))

    mismatch = grammar_guard.current_mismatch()
    assert mismatch is not None
    assert mismatch.reason == "asr_version_unreported"


def test_la_derive_ne_casse_jamais_la_transcription(settings: Settings) -> None:
    """La garde alerte mais ne doit rien refuser : sinon dégradation -> panne totale."""
    recognizer = RemoteCtcRecognizer(settings, transport=_transcribe_transport("0.0.1-ancienne"))

    result = recognizer.transcribe(AudioInput(data=b"\x00\x00", format="pcm_s16le"))

    assert result.text == "zambar fo kalangaybor ihinza"
    assert result.acoustic_score == pytest.approx(0.9)


def test_une_derive_resolue_est_oubliee(settings: Settings) -> None:
    current = zarma_numbers.load_lexicon().grammar_version
    RemoteCtcRecognizer(settings, transport=_transcribe_transport("0.0.1-ancienne")).transcribe(
        AudioInput(data=b"\x00\x00", format="pcm_s16le")
    )
    assert grammar_guard.current_mismatch() is not None

    RemoteCtcRecognizer(settings, transport=_transcribe_transport(current)).transcribe(
        AudioInput(data=b"\x00\x00", format="pcm_s16le")
    )
    assert grammar_guard.current_mismatch() is None


@pytest.mark.asyncio
async def test_sonde_au_demarrage_detecte_la_derive(settings: Settings) -> None:
    """Le cas d'usage central : voir la panne au déploiement, pas au premier usager."""
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200, json={"status": "ok", "model": "m", "grammar_version": "0.0.1-ancienne"}
        )
    )

    mismatch = await grammar_guard.probe(settings, transport=transport)

    assert mismatch is not None
    assert mismatch.asr_grammar_version == "0.0.1-ancienne"


@pytest.mark.asyncio
async def test_sonde_au_demarrage_accepte_des_versions_egales(settings: Settings) -> None:
    current = zarma_numbers.load_lexicon().grammar_version
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"status": "ok", "grammar_version": current})
    )

    assert await grammar_guard.probe(settings, transport=transport) is None
    assert grammar_guard.current_mismatch() is None


@pytest.mark.asyncio
async def test_sonde_injoignable_ne_bloque_pas_le_demarrage(settings: Settings) -> None:
    """L'API doit démarrer ASR éteint — le pipeline retombe sur `repeat` (FR21)."""

    def _refuse(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("service éteint")

    transport = httpx.MockTransport(_refuse)

    assert await grammar_guard.probe(settings, transport=transport) is None
    assert grammar_guard.current_mismatch() is None


@pytest.mark.asyncio
async def test_sonde_ignoree_en_mode_mock() -> None:
    mock_settings = Settings(ASR_MODE="mock", ASR_ENDPOINT_URL="")
    assert await grammar_guard.probe(mock_settings) is None
