from collections.abc import AsyncIterator
from typing import Literal, Protocol, TypedDict


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMClient(Protocol):
    """Chat-style LLM backend. Implementations raise LLMError on failure."""

    async def chat(self, messages: list[Message]) -> str: ...

    def stream_chat(self, messages: list[Message]) -> AsyncIterator[str]:
        """Yield the answer piece by piece (tokens) as the model generates it."""
        ...
