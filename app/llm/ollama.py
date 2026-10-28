import httpx

from app.core.exceptions import LLMError
from app.llm.base import Message


class OllamaClient:
    """LLM client backed by a local Ollama server (https://ollama.com)."""

    def __init__(self, http_client: httpx.AsyncClient, model: str) -> None:
        self._http = http_client
        self._model = model

    async def chat(self, messages: list[Message]) -> str:
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            response = await self._http.post("/api/chat", json=payload)
            response.raise_for_status()
            content = response.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc

        if not isinstance(content, str):
            raise LLMError("Ollama returned a non-text response")
        return content
