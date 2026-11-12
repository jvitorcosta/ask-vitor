import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeLLMClient


def test_ask_returns_answer(client: TestClient, fake_llm: FakeLLMClient) -> None:
    response = client.post("/ask", json={"question": "  What does Vitor do?  "})

    assert response.status_code == 200
    assert response.json() == {
        "question": "What does Vitor do?",
        "answer": "A canned answer.",
        "kind": "answer",
        "sources": [],
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


def test_ask_returns_kind_and_sources(client: TestClient, fake_llm: FakeLLMClient) -> None:
    fake_llm.answer = "He worked at Nubank.\n<<sources: base.2>>"

    body = client.post("/ask", json={"question": "Where?"}).json()

    assert body["answer"] == "He worked at Nubank."
    assert body["kind"] == "answer"
    assert body["sources"][0]["id"] == "base.2"
    assert body["sources"][0]["label"] == "Knowledge base"


def test_unknown_source_ids_are_dropped(client: TestClient, fake_llm: FakeLLMClient) -> None:
    fake_llm.answer = "He worked at Nubank.\n<<sources: base.2, nope>>"

    body = client.post("/ask", json={"question": "Where?"}).json()

    assert [source["id"] for source in body["sources"]] == ["base.2"]


def test_fallback_has_no_sources(client: TestClient, fake_llm: FakeLLMClient) -> None:
    fake_llm.answer = "I don't have information about that."

    body = client.post("/ask", json={"question": "Shoe size?"}).json()

    assert body["kind"] == "fallback"
    assert body["sources"] == []
