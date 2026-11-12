import json

import httpx
import pytest

from app.core.exceptions import LLMError
from app.llm.ollama import OllamaClient


def ollama_client(handler) -> OllamaClient:
    http = httpx.AsyncClient(base_url="http://ollama", transport=httpx.MockTransport(handler))
    return OllamaClient(http, model="test-model")


async def collect(client: OllamaClient) -> list[str]:
    return [token async for token in client.stream_chat([{"role": "user", "content": "hi"}])]


@pytest.mark.anyio
async def test_stream_chat_yields_content_of_each_line() -> None:
    # Ollama streams one JSON object per line (NDJSON); the last one has "done": true.
    lines = [
        {"message": {"content": "Hel"}, "done": False},
        {"message": {"content": "lo"}, "done": False},
        {"message": {"content": ""}, "done": True},
    ]
    body = "\n".join(json.dumps(line) for line in lines)

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, text=body)

    assert await collect(ollama_client(handler)) == ["Hel", "lo"]


@pytest.mark.anyio
async def test_stream_chat_raises_llm_error_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(LLMError):
        await collect(ollama_client(handler))


@pytest.mark.anyio
async def test_stream_chat_raises_llm_error_on_malformed_line() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    with pytest.raises(LLMError):
        await collect(ollama_client(handler))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
