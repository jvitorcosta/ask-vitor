from collections.abc import AsyncIterator

from app.knowledge.context import ContextProvider
from app.llm.base import LLMClient, Message
from app.prompts.qa import build_messages


class QAService:
    """Answers questions with an LLM, grounded in the provided context."""

    def __init__(self, llm: LLMClient, context_provider: ContextProvider) -> None:
        self._llm = llm
        self._context_provider = context_provider

    def _messages(self, question: str) -> list[Message]:
        context = self._context_provider.get_context(question)
        return build_messages(context, question)

    async def answer(self, question: str) -> str:
        answer = await self._llm.chat(self._messages(question))
        return answer.strip()

    def answer_stream(self, question: str) -> AsyncIterator[str]:
        """Same grounded prompt as answer(), but yields the answer as it is generated."""
        return self._llm.stream_chat(self._messages(question))
