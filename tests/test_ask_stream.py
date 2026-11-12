import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeLLMClient


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """Turn a raw Server-Sent Events body into (event, data) pairs."""
    events = []
    for block in body.strip().split("\n\n"):
        event, data = "message", {}
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        events.append((event, data))
    return events


def test_stream_sends_tokens_then_done(client: TestClient, fake_llm: FakeLLMClient) -> None:
    fake_llm.tokens = ["Vitor ", "works ", "with ML."]

    response = client.post("/ask/stream", json={"question": "What does Vitor do?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert parse_sse(response.text) == [
        ("message", {"token": "Vitor "}),
        ("message", {"token": "works "}),
        ("message", {"token": "with ML."}),
        ("done", {}),
    ]


def test_stream_returns_503_when_llm_fails_before_first_token(
    client: TestClient, fake_llm: FakeLLMClient
) -> None:
    fake_llm.fail = True

    response = client.post("/ask/stream", json={"question": "What does Vitor do?"})

    assert response.status_code == 503
    assert response.json() == {"detail": "LLM service unavailable"}


def test_stream_sends_error_event_when_llm_fails_mid_answer(
    client: TestClient, fake_llm: FakeLLMClient
) -> None:
    fake_llm.tokens = ["Vitor ", "works "]
    fake_llm.fail_after = 1

    response = client.post("/ask/stream", json={"question": "What does Vitor do?"})

    assert response.status_code == 200
    assert parse_sse(response.text) == [
        ("message", {"token": "Vitor "}),
        ("error", {"detail": "LLM service unavailable"}),
    ]


@pytest.mark.parametrize("payload", [{}, {"question": "   "}, {"question": "a" * 501}])
def test_stream_validates_question(client: TestClient, payload: dict) -> None:
    response = client.post("/ask/stream", json=payload)
    assert response.status_code == 422


def test_cors_allows_the_web_app(client: TestClient) -> None:
    response = client.options(
        "/ask/stream",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
