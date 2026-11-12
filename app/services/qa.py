from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass, field

from app.knowledge.facts import Fact, KnowledgeProvider
from app.llm.base import LLMClient
from app.prompts.qa import FALLBACK_ANSWER, build_messages
from app.services.replies import ReplyKind, reply_kind
from app.services.sources import SourcesTrailer


@dataclass(frozen=True)
class Answer:
    text: str
    kind: ReplyKind
    sources: list[Fact]
    # Every id the model cited, before unknown ones were dropped from `sources` (for evals).
    cited_ids: list[str] = field(default_factory=list)


def _build_answer(text: str, cited_ids: list[str], facts: list[Fact]) -> Answer:
    """Classify the visible text and map cited ids to facts (unknown ids dropped)."""
    text = text.strip()
    if not text:  # empty or refused reply: show the fixed fallback, never a blank answer
        return Answer(text=FALLBACK_ANSWER, kind="fallback", sources=[], cited_ids=cited_ids)
    kind = reply_kind(text)
    if kind != "answer":
        return Answer(text=text, kind=kind, sources=[], cited_ids=cited_ids)
    by_id = {fact.id: fact for fact in facts}
    return Answer(
        text=text,
        kind=kind,
        sources=[by_id[i] for i in cited_ids if i in by_id],
        cited_ids=cited_ids,
    )


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
        answer = _build_answer("".join(shown), ids, facts)
        if not shown:
            yield answer.text  # nothing visible was streamed: show the fallback text
        yield answer
