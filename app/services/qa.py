from app.knowledge.context import ContextProvider
from app.llm.base import LLMClient
from app.prompts.qa import build_messages


class QAService:
    """Answers questions with an LLM, grounded in the provided context."""

    def __init__(self, llm: LLMClient, context_provider: ContextProvider) -> None:
        self._llm = llm
        self._context_provider = context_provider

    async def answer(self, question: str) -> str:
        context = self._context_provider.get_context(question)
        messages = build_messages(context, question)
        answer = await self._llm.chat(messages)
        return answer.strip()
