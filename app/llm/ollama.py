import json
from collections.abc import AsyncIterator

import httpx

from app.core.exceptions import LLMError
from app.llm.base import Message


class OllamaClient:
    """LLM client backed by a local Ollama server (https://ollama.com)."""

    def __init__(self, http_client: httpx.AsyncClient, model: str) -> None:
        self._http = http_client
        self._model = model

    def _payload(self, messages: list[Message], *, stream: bool) -> dict:
        return {
            "model": self._model,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": 0},
        }

    async def chat(self, messages: list[Message]) -> str:
        payload = self._payload(messages, stream=False)
        try:
            response = await self._http.post("/api/chat", json=payload)
            response.raise_for_status()
            content = response.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc

        if not isinstance(content, str):
            raise LLMError("Ollama returned a non-text response")
        return content

    async def stream_chat(self, messages: list[Message]) -> AsyncIterator[str]:
        # With "stream": true, Ollama sends one JSON object per line (NDJSON) as the model
        # generates; each line carries the next piece of text and the last one has "done": true.
        payload = self._payload(messages, stream=True)
        try:
            async with self._http.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    token = chunk["message"]["content"]
                    if token:
                        yield token
                    if chunk.get("done"):
                        return
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise LLMError(f"Ollama stream failed: {exc}") from exc
