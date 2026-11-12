from collections.abc import AsyncIterator

from app.knowledge.facts import KnowledgeProvider
from app.llm.base import LLMClient, Message
from app.prompts.qa import build_messages


class QAService:
    """Answers questions with an LLM, grounded in the provided context."""

    def __init__(self, llm: LLMClient, knowledge: KnowledgeProvider) -> None:
        self._llm = llm
        self._knowledge = knowledge

    async def _messages(self, question: str) -> list[Message]:
        facts = await self._knowledge.get_facts()
        return build_messages(facts, question)

    async def answer(self, question: str) -> str:
        answer = await self._llm.chat(await self._messages(question))
        return answer.strip()

    async def answer_stream(self, question: str) -> AsyncIterator[str]:
        """Same grounded prompt as answer(), but yields the answer as it is generated."""
        async for token in self._llm.stream_chat(await self._messages(question)):
            yield token
