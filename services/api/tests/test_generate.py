"""Tests de ``GET /api/v1/grammar/generate/{number}`` (story 3.5).

Sans GPU ni modèle : on valide que la forme zarma provient du moteur
``zarma_numbers`` (source unique), que ``grammar_version`` vient du lexique, et
que les entrées hors plage / invalides sont refusées avec l'enveloppe d'erreur
normalisée (story 2.7).
"""

from __future__ import annotations

from app.main import app
from fastapi.testclient import TestClient
from zarma_numbers import MAX_VALUE, generate, load_lexicon

client = TestClient(app)


def test_generate_returns_canonical_form_from_engine() -> None:
    resp = client.get("/api/v1/grammar/generate/235")
    assert resp.status_code == 200
    body = resp.json()

    assert body["number"] == 235
    # Forme issue exclusivement du moteur, jamais recalculée dans la route.
    assert body["zarma_text"] == generate(235)
    # Version issue du lexique (source unique de vérité).
    assert body["grammar_version"] == load_lexicon().grammar_version


def test_generate_accepts_lower_and_upper_bounds() -> None:
    lower = client.get("/api/v1/grammar/generate/0")
    assert lower.status_code == 200
    assert lower.json()["zarma_text"] == generate(0)

    upper = client.get(f"/api/v1/grammar/generate/{MAX_VALUE}")
    assert upper.status_code == 200
    assert upper.json()["zarma_text"] == generate(MAX_VALUE)


def test_generate_rejects_negative_number() -> None:
    resp = client.get("/api/v1/grammar/generate/-1")
    assert resp.status_code == 400
    error = resp.json()["error"]
    assert error["code"] == "OUT_OF_RANGE"
    # La borne annoncée provient du moteur (source unique), pas d'une copie.
    assert "99 999 999 999" in error["message"]


def test_generate_rejects_above_maximum() -> None:
    resp = client.get(f"/api/v1/grammar/generate/{MAX_VALUE + 1}")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OUT_OF_RANGE"


def test_generate_rejects_non_integer_input() -> None:
    resp = client.get("/api/v1/grammar/generate/abc")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
