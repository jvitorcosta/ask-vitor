import asyncio

from app.knowledge.context import StaticKnowledgeProvider
from app.services.qa import QAService


class _FixedLLM:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    async def chat(self, messages: list) -> str:
        return self._reply

    async def stream_chat(self, messages: list):  # pragma: no cover - unused here
        yield self._reply


def test_cited_ids_keeps_every_id_the_model_cited_while_sources_drops_unknown_ones() -> None:
    llm = _FixedLLM("He works in Python.\n<<sources: base.6, made.up>>")
    answer = asyncio.run(QAService(llm, StaticKnowledgeProvider()).answer("What stack?"))

    assert answer.cited_ids == ["base.6", "made.up"]
    assert [fact.id for fact in answer.sources] == ["base.6"]


def test_cited_ids_defaults_to_empty_for_fixed_replies() -> None:
    llm = _FixedLLM("I don't have information about that.")
    answer = asyncio.run(QAService(llm, StaticKnowledgeProvider()).answer("Salary?"))

    assert answer.cited_ids == []
