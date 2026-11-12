from collections.abc import AsyncIterator

import anthropic

from app.core.exceptions import LLMError
from app.llm.base import Message


class AnthropicClient:
    """LLM client backed by the Claude API (Claude Haiku 5.5)."""

    def __init__(self, client: anthropic.AsyncAnthropic, *, model: str, max_tokens: int) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def _request(self, messages: list[Message]) -> dict:
        # The system prompt (facts + rules) is identical across questions, so it is marked as
        # cacheable. No temperature/top_p/top_k: Haiku 5.5 rejects non-default values. Thinking is
        # off: its tokens would count toward max_tokens and could cut the answer and its trailer.
        system_text = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        rest = [
            {"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"
        ]
        return {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": [
                {"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": rest,
            "thinking": {"type": "disabled"},
        }

    async def chat(self, messages: list[Message]) -> str:
        try:
            response = await self._client.messages.create(**self._request(messages))
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic request failed: {exc}") from exc
        return "".join(block.text for block in response.content if block.type == "text")

    async def stream_chat(self, messages: list[Message]) -> AsyncIterator[str]:
        try:
            async with self._client.messages.stream(**self._request(messages)) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic stream failed: {exc}") from exc
