from typing import Literal, Protocol, TypedDict


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMClient(Protocol):
    """Chat-style LLM backend. Implementations raise LLMError on failure."""

    async def chat(self, messages: list[Message]) -> str: ...
