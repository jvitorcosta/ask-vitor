from collections.abc import Sequence
from typing import Protocol

from app.knowledge.data import KNOWLEDGE_BASE


class ContextProvider(Protocol):
    """Supplies the knowledge snippets the LLM may use to answer a question."""

    def get_context(self, question: str) -> list[str]: ...


class StaticContextProvider:
    """Returns the whole knowledge base regardless of the question."""

    def __init__(self, snippets: Sequence[str] = KNOWLEDGE_BASE) -> None:
        self._snippets = list(snippets)

    def get_context(self, question: str) -> list[str]:
        return list(self._snippets)
