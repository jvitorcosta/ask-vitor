import asyncio
import json
import logging
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx

from app.core.exceptions import LLMError
from app.knowledge.data import KNOWLEDGE_BASE
from app.knowledge.facts import Fact, KnowledgeProvider, parse_knowledge

logger = logging.getLogger(__name__)

__all__ = ["JsonKnowledgeProvider", "KnowledgeProvider", "StaticKnowledgeProvider"]


class StaticKnowledgeProvider:
    """Serves the built-in knowledge base as facts base.1 ... base.N."""

    def __init__(self, snippets: Sequence[str] = KNOWLEDGE_BASE) -> None:
        self._facts = [
            Fact(id=f"base.{number}", source="Knowledge base", updated="", text=text)
            for number, text in enumerate(snippets, start=1)
        ]

    async def get_facts(self) -> list[Fact]:
        return list(self._facts)


class JsonKnowledgeProvider:
    """Loads facts from a knowledge.json (https URL or local path), cached for a TTL.

    If a refresh fails, the last good copy keeps being served; with no copy at all the
    request fails with LLMError, which the API maps to 503.
    """

    def __init__(
        self,
        source: str,
        *,
        http: httpx.AsyncClient,
        ttl_seconds: float = 900,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source = source
        self._http = http
        self._ttl = ttl_seconds
        self._clock = clock
        self._facts: list[Fact] | None = None
        self._expires_at = 0.0

    async def get_facts(self) -> list[Fact]:
        if self._facts is not None and self._clock() < self._expires_at:
            return list(self._facts)
        try:
            self._facts = parse_knowledge(await self._load())
        except (httpx.HTTPError, OSError, ValueError) as exc:
            # ValueError covers bad JSON and KnowledgeError.
            if self._facts is None:
                raise LLMError("knowledge unavailable") from exc
            logger.warning("Knowledge refresh failed, serving last good copy: %s", exc)
        # Also back off after a failed refresh so an outage is not retried on every request.
        self._expires_at = self._clock() + self._ttl
        return list(self._facts)

    async def _load(self) -> dict:
        if self._source.startswith(("http://", "https://")):
            response = await self._http.get(self._source)
            response.raise_for_status()
            return response.json()
        text = await asyncio.to_thread(Path(self._source).read_text, encoding="utf-8")
        return json.loads(text)
