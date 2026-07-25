"""Tests d'intégration du squelette API (story 2.1).

Couvre AC5 : ``/health``, ``/api/v1/models`` et ``/api/v1/grammar/version``.
Sans GPU, sans modèle réel — on valide le contrat HTTP et la traçabilité des
versions (``grammar_version`` **issu du lexique**, source unique de vérité).
"""

from __future__ import annotations

from app.api.v1.models import AVAILABLE_RECOGNIZERS
from app.asr.base import SpeechRecognizer
from app.asr.factory import get_recognizer
from app.asr.mock import MockRecognizer
from app.config import get_settings
from app.main import app
from fastapi.testclient import TestClient
from zarma_numbers import load_lexicon

client = TestClient(app)


def test_health_returns_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_models_active_and_available_match_settings() -> None:
    resp = client.get("/api/v1/models")
    assert resp.status_code == 200
    body = resp.json()

    assert body["available"] == list(AVAILABLE_RECOGNIZERS)
    # `active` est piloté par ASR_MODE (défaut `mock` en dev).
    assert body["active"] == get_settings().ASR_MODE
    assert body["active"] in body["available"]


def test_models_resolves_recognizer_through_dependency_injection() -> None:
    calls = 0

    def override_recognizer() -> SpeechRecognizer:
        nonlocal calls
        calls += 1
        return MockRecognizer()

    app.dependency_overrides[get_recognizer] = override_recognizer
    try:
        resp = client.get("/api/v1/models")
    finally:
        app.dependency_overrides.pop(get_recognizer, None)

    assert resp.status_code == 200
    assert calls == 1


def test_grammar_version_comes_from_lexicon() -> None:
    resp = client.get("/api/v1/grammar/version")
    assert resp.status_code == 200
    body = resp.json()

    lexicon = load_lexicon()
    # Source unique de vérité : la version vient du lexique, jamais en dur.
    assert body["grammar_version"] == lexicon.grammar_version

    # Tant que la validation locuteurs natifs n'a pas eu lieu, tout est unresolved.
    assert body["validated_count"] == 0
    assert isinstance(body["unresolved_items"], list)
    assert body["unresolved_items"], "au moins une entrée non résolue attendue"
    # Les trois grandes échelles bloquantes doivent figurer parmi les non résolues.
    for scale_value in ("10000", "100000", "1000000"):
        assert scale_value in body["unresolved_items"]


def test_openapi_docs_available() -> None:
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
