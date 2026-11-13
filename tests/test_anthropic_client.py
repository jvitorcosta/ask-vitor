import json

import anthropic
import httpx2
import pytest

from app.core.exceptions import LLMError
from app.llm.anthropic import AnthropicClient
from app.llm.base import Message

SYSTEM = "Facts about Vitor. Rules."
QUESTION = "Where does Vitor work?"
MESSAGES: list[Message] = [
    {"role": "system", "content": SYSTEM},
    {"role": "user", "content": QUESTION},
]


def anthropic_client(handler) -> AnthropicClient:
    sdk = anthropic.AsyncAnthropic(
        api_key="test",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        max_retries=0,
    )
    return AnthropicClient(sdk, model="claude-haiku-5-5", max_tokens=300)


def message_json(content: list[dict], stop_reason: str = "end_turn") -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 0},
    }


def sse(events: list[tuple[str, dict]]) -> str:
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)


@pytest.mark.anyio
async def test_chat_sends_system_with_cache_control_no_sampling_and_no_thinking() -> None:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.update(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": "At Nubank."}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 3},
            },
        )

    answer = await anthropic_client(handler).chat(MESSAGES)

    assert answer == "At Nubank."
    assert seen["system"] == [
        {"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}
    ]
    assert seen["messages"] == [{"role": "user", "content": QUESTION}]
    assert seen["model"] == "claude-haiku-5-5"
    assert seen["max_tokens"] == 300
    assert seen["thinking"] == {"type": "disabled"}
    for param in ("temperature", "top_p", "top_k"):
        assert param not in seen


@pytest.mark.anyio
async def test_stream_chat_yields_text_deltas() -> None:
    def delta(text: str) -> tuple[str, dict]:
        return (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": text},
            },
        )

    body = sse(
        [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_1",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-haiku-5-5",
                        "content": [],
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": 10, "output_tokens": 1},
                    },
                },
            ),
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            delta("Hello"),
            delta(" there"),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 2},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
    )

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent = json.loads(request.content)
        assert sent["stream"] is True
        assert sent["thinking"] == {"type": "disabled"}
        return httpx2.Response(200, text=body, headers={"content-type": "text/event-stream"})

    client = anthropic_client(handler)
    assert [t async for t in client.stream_chat(MESSAGES)] == ["Hello", " there"]


@pytest.mark.anyio
@pytest.mark.parametrize("status", [500, 429])
async def test_api_error_becomes_llm_error(status: int) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status,
            json={"type": "error", "error": {"type": "api_error", "message": "boom"}},
        )

    client = anthropic_client(handler)
    with pytest.raises(LLMError):
        await client.chat(MESSAGES)
    with pytest.raises(LLMError):
        _ = [t async for t in client.stream_chat(MESSAGES)]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize("key", [None, ""])
def test_startup_fails_without_api_key(monkeypatch: pytest.MonkeyPatch, key: str | None) -> None:
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    app = create_app()
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(_env_file=None, llm_backend="anthropic", anthropic_api_key=key),
    )
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is required"):
        with TestClient(app):
            pass


@pytest.mark.anyio
async def test_chat_returns_empty_text_when_the_model_refuses() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=message_json([], stop_reason="refusal"))

    assert await anthropic_client(handler).chat(MESSAGES) == ""


@pytest.mark.anyio
async def test_stream_chat_yields_nothing_when_the_model_refuses() -> None:
    body = sse(
        [
            (
                "message_start",
                {"type": "message_start", "message": message_json([], stop_reason="refusal")},
            ),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "refusal", "stop_sequence": None},
                    "usage": {"output_tokens": 0},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
    )

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, text=body, headers={"content-type": "text/event-stream"})

    assert [t async for t in anthropic_client(handler).stream_chat(MESSAGES)] == []


def test_timeout_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    app = create_app()
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: Settings(
            _env_file=None,
            llm_backend="anthropic",
            anthropic_api_key="test",
            anthropic_timeout_seconds=12.5,
        ),
    )
    with TestClient(app):
        sdk = app.state.llm_client._client
        assert sdk.timeout == 12.5


def test_timeout_defaults_to_30_seconds() -> None:
    from app.core.config import Settings

    assert Settings(_env_file=None).anthropic_timeout_seconds == 30.0
