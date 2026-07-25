"""Reconnaissance d'une **opération** via POST /api/v1/recognize (story 6.1, task 7).

Deux exigences se répondent :

- l'API porte désormais une expression (opérandes + opérateur + résultat) ;
- le mode « nombre seul » des epics 1–5 reste **strictement** identique — c'est
  ce que vérifient les tests de non-régression en fin de fichier.

Tout passe par ``MockRecognizer`` : aucun GPU, aucun réseau.
"""

from __future__ import annotations

import wave
from io import BytesIO
from uuid import UUID

import pytest
import zarma_numbers
from app.asr.factory import get_recognizer
from app.asr.mock import MockRecognizer
from app.main import app
from app.pipeline.recognition import run_recognition_pipeline
from fastapi.testclient import TestClient
from zarma_numbers.expressions import Expression, render_expression

client = TestClient(app)
ANON_ID = "00000000-0000-4000-8000-000000000042"


def make_wav(frame_count: int = 1_600) -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"\x00\x00" * frame_count)
    return output.getvalue()


@pytest.fixture
def mock_recognizer() -> MockRecognizer:
    recognizer = MockRecognizer()
    app.dependency_overrides[get_recognizer] = lambda: recognizer
    try:
        yield recognizer
    finally:
        app.dependency_overrides.pop(get_recognizer, None)


def recognize() -> dict:
    response = client.post(
        "/api/v1/recognize",
        files={"audio": ("test.wav", make_wav(), "audio/wav")},
        data={"anon_id": ANON_ID},
    )
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# AC1/AC5 — l'API porte l'opération et son résultat
# --------------------------------------------------------------------------- #


def test_expression_is_recognized_and_evaluated(mock_recognizer):
    mock_recognizer.set_text(render_expression(Expression(23, "+", 15)), acoustic_score=0.95)
    body = recognize()

    expression = body["expression"]
    assert (expression["left"], expression["operator"], expression["right"]) == (23, "+", 15)
    assert expression["result"] == 38
    assert expression["remainder"] == 0
    assert expression["result_zarma_text"] == zarma_numbers.generate(38)
    assert expression["refusal_code"] is None
    assert body["decision"] in {"accept", "confirm"}


def test_division_with_remainder_is_carried_by_the_contract():
    """Le reste doit **voyager** dans le contrat, jamais être arrondi en route.

    Ce test s'arrête au schéma, et c'est volontaire : la division n'a pas encore
    de mot zarma validé (``divide`` est ``unresolved`` au lexique), donc aucune
    transcription ne peut aujourd'hui produire une division de bout en bout. Le
    jour où un locuteur la fournira, le chemin complet fonctionnera sans
    modification de code — le contrat, lui, est déjà prêt.
    """
    from app.api.v1.recognize import RecognizedExpression

    payload = RecognizedExpression(
        left=103,
        operator="/",
        right=5,
        zarma_text="—",
        result=20,
        remainder=3,
        result_zarma_text="waranka ga cindi hinza",
    ).model_dump(mode="json")

    assert payload["result"] == 20
    assert payload["remainder"] == 3
    assert payload["result_zarma_text"] == "waranka ga cindi hinza"


def test_out_of_domain_expression_is_refused_not_invented(mock_recognizer):
    """3 − 5 : l'énoncé est compris, la réponse n'existe pas. On le dit (FR21)."""
    mock_recognizer.set_text(render_expression(Expression(3, "-", 5)))
    expression = recognize()["expression"]

    assert expression["result"] is None
    assert expression["refusal_code"] == "NEGATIVE_RESULT"
    assert expression["result_zarma_text"] == ""


def test_understood_but_impossible_is_not_a_repeat(mock_recognizer):
    """Demander de répéter serait faux : l'utilisateur a été parfaitement compris."""
    mock_recognizer.set_text(render_expression(Expression(3, "-", 5)), acoustic_score=1.0)
    body = recognize()

    assert body["decision"] != "repeat"
    assert body["expression"]["refusal_code"] == "NEGATIVE_RESULT"


def test_expression_zarma_text_is_replayable(mock_recognizer):
    """La forme portée par l'API doit pouvoir être relue à voix haute telle quelle."""
    text = render_expression(Expression(23, "+", 15))
    mock_recognizer.set_text(text)

    assert recognize()["expression"]["zarma_text"] == text


def test_expression_is_persisted_and_returned_by_history(mock_recognizer):
    mock_recognizer.set_text(render_expression(Expression(23, "+", 15)))
    recognized = recognize()

    history = client.get("/api/v1/history", params={"anon_id": ANON_ID, "limit": 5})
    assert history.status_code == 200
    row = next(item for item in history.json() if item["id"] == recognized["id"])
    assert row["expression"]["result"] == 38
    assert row["zarma_text"] == recognized["expression"]["zarma_text"]


def test_unintelligible_speech_still_asks_to_repeat(mock_recognizer):
    """Ni nombre ni opération : rien n'est inventé, on demande de répéter."""
    mock_recognizer.set_text("kala suba borey ga koy", acoustic_score=0.2)
    body = recognize()

    assert body["expression"] is None
    assert body["recognized_number"] is None
    assert body["decision"] == "repeat"


# --------------------------------------------------------------------------- #
# Non-régression : « nombre seul » se comporte exactement comme avant
# --------------------------------------------------------------------------- #


def test_number_only_response_carries_no_expression(mock_recognizer):
    mock_recognizer.set_text(zarma_numbers.generate(42), acoustic_score=0.95)
    body = recognize()

    assert body["expression"] is None
    assert body["recognized_number"] == 42
    assert body["zarma_text"] == zarma_numbers.generate(42)


@pytest.mark.parametrize("value", [0, 1, 42, 105, 1234, 99_999])
def test_number_only_pipeline_is_byte_for_byte_unchanged(mock_recognizer, value):
    """L'ajout des expressions ne doit toucher aucun champ du chemin numérique."""
    from app.asr.base import AsrResult
    from app.config import get_settings

    asr = AsrResult(
        text=zarma_numbers.generate(value),
        acoustic_score=0.9,
        candidates=[],
        latency_ms=10,
        model_version="mock-1.0.0",
    )
    outcome = run_recognition_pipeline(asr, get_settings())

    assert outcome.number == value
    assert outcome.zarma_text == zarma_numbers.generate(value)
    assert outcome.expression is None
    assert outcome.expression_result is None
    assert outcome.refusal_code is None
    assert outcome.result_zarma_text == ""


def test_anon_id_is_a_valid_uuid_in_tests():
    """Garde-fou : le harnais ne doit pas masquer une validation d'entrée."""
    assert UUID(ANON_ID)
