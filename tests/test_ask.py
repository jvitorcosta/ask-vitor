import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeLLMClient


def test_ask_returns_answer(client: TestClient, fake_llm: FakeLLMClient) -> None:
    response = client.post("/ask", json={"question": "  What does Vitor do?  "})

    assert response.status_code == 200
    assert response.json() == {
        "question": "What does Vitor do?",
        "answer": "A canned answer.",
    }
    assert len(fake_llm.received) == 1


@pytest.mark.parametrize("payload", [{}, {"question": ""}, {"question": "   "}])
def test_ask_rejects_missing_or_blank_question(client: TestClient, payload: dict) -> None:
    response = client.post("/ask", json=payload)
    assert response.status_code == 422


def test_ask_rejects_too_long_question(client: TestClient) -> None:
    response = client.post("/ask", json={"question": "a" * 501})
    assert response.status_code == 422


def test_ask_returns_503_when_llm_fails(client: TestClient, fake_llm: FakeLLMClient) -> None:
    fake_llm.fail = True

    response = client.post("/ask", json={"question": "What does Vitor do?"})

    assert response.status_code == 503
    assert response.json() == {"detail": "LLM service unavailable"}
