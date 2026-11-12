from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass

from app.knowledge.facts import Fact, KnowledgeProvider
from app.llm.base import LLMClient
from app.prompts.qa import build_messages
from app.services.replies import ReplyKind, reply_kind
from app.services.sources import SourcesTrailer


@dataclass(frozen=True)
class Answer:
    text: str
    kind: ReplyKind
    sources: list[Fact]


def _build_answer(text: str, cited_ids: list[str], facts: list[Fact]) -> Answer:
    """Classify the visible text and map cited ids to facts (unknown ids dropped)."""
    text = text.strip()
    kind = reply_kind(text)
    if kind != "answer":
        return Answer(text=text, kind=kind, sources=[])
    by_id = {fact.id: fact for fact in facts}
    return Answer(text=text, kind=kind, sources=[by_id[i] for i in cited_ids if i in by_id])


class QAService:
    """Answers questions with an LLM, grounded in the provided context."""

    def __init__(self, llm: LLMClient, knowledge: KnowledgeProvider) -> None:
        self._llm = llm
        self._knowledge = knowledge

    async def answer(self, question: str) -> Answer:
        facts = await self._knowledge.get_facts()
        raw = await self._llm.chat(build_messages(facts, question))
        trailer = SourcesTrailer()
        visible = trailer.feed(raw)
        rest, ids = trailer.finish()
        return _build_answer(visible + rest, ids, facts)

    async def answer_stream(self, question: str) -> AsyncIterator[str | Answer]:
        """Same grounded prompt as answer(): yields visible tokens, then one Answer last."""
        facts = await self._knowledge.get_facts()
        trailer = SourcesTrailer()
        shown: list[str] = []
        async with aclosing(self._llm.stream_chat(build_messages(facts, question))) as stream:
            async for token in stream:
                visible = trailer.feed(token)
                if visible:
                    shown.append(visible)
                    yield visible
        rest, ids = trailer.finish()
        if rest:
            shown.append(rest)
            yield rest
        yield _build_answer("".join(shown), ids, facts)
