import re
from dataclasses import dataclass
from typing import Protocol

_ID_PATTERN = re.compile(r"^[a-z0-9._-]+$")
_SUPPORTED_VERSION = 1


class KnowledgeError(ValueError):
    """Raised when a knowledge document does not have the expected shape."""


@dataclass(frozen=True)
class Fact:
    """One citable statement about Vitor; `source` is the label visitors see."""

    id: str
    source: str
    updated: str
    text: str


class KnowledgeProvider(Protocol):
    """Supplies the facts the LLM may use to answer a question."""

    async def get_facts(self) -> list[Fact]: ...


def parse_knowledge(data: dict) -> list[Fact]:
    """Validate a knowledge.json document and return its facts. Unknown keys are ignored."""
    if not isinstance(data, dict) or data.get("version") != _SUPPORTED_VERSION:
        raise KnowledgeError(f"unsupported knowledge version (expected {_SUPPORTED_VERSION})")
    raw_facts = data.get("facts")
    if not isinstance(raw_facts, list):
        raise KnowledgeError("'facts' must be a list")

    facts: list[Fact] = []
    seen: set[str] = set()
    for raw in raw_facts:
        if not isinstance(raw, dict):
            raise KnowledgeError("each fact must be an object")
        values = {key: raw.get(key) for key in ("id", "source", "updated", "text")}
        if not all(isinstance(value, str) for value in values.values()):
            raise KnowledgeError(f"fact {raw.get('id')!r} needs string id, source, updated, text")
        fact = Fact(**values)
        if not _ID_PATTERN.match(fact.id):
            raise KnowledgeError(f"invalid fact id {fact.id!r}")
        if fact.id in seen:
            raise KnowledgeError(f"duplicate fact id {fact.id!r}")
        seen.add(fact.id)
        facts.append(fact)
    return facts
