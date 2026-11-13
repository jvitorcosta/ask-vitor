import json

import httpx
import pytest

from app.core.exceptions import LLMError
from app.knowledge.context import JsonKnowledgeProvider, StaticKnowledgeProvider
from app.knowledge.facts import Fact, KnowledgeError, parse_knowledge


def _fact(id_: str = "cv.nubank", **overrides: str) -> dict[str, str]:
    fact = {"id": id_, "source": "CV · Experience", "updated": "2026-11-12", "text": "Text."}
    return {**fact, **overrides}


def _doc(*facts: dict[str, str], version: int = 1) -> dict:
    return {"version": version, "generated": "2026-11-12", "facts": list(facts), "extra": 1}


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_parse_knowledge_reads_facts() -> None:
    facts = parse_knowledge(_doc(_fact(), _fact("cv.eloGroup".lower())))

    assert facts[0] == Fact(
        id="cv.nubank", source="CV · Experience", updated="2026-11-12", text="Text."
    )
    assert [f.id for f in facts] == ["cv.nubank", "cv.elogroup"]


def test_parse_rejects_wrong_version() -> None:
    with pytest.raises(KnowledgeError):
        parse_knowledge(_doc(_fact(), version=2))


def test_parse_rejects_duplicate_ids() -> None:
    with pytest.raises(KnowledgeError):
        parse_knowledge(_doc(_fact(), _fact()))


def test_parse_rejects_bad_id() -> None:
    with pytest.raises(KnowledgeError):
        parse_knowledge(_doc(_fact("Has Space")))


def test_parse_rejects_missing_field() -> None:
    with pytest.raises(KnowledgeError):
        parse_knowledge(_doc({"id": "a", "source": "s", "updated": "2026-11-12"}))


@pytest.mark.anyio
async def test_static_provider_numbers_ids() -> None:
    facts = await StaticKnowledgeProvider(["One.", "Two."]).get_facts()

    assert facts[0] == Fact(id="base.1", source="Knowledge base", updated="", text="One.")
    assert facts[1].id == "base.2"


def _provider(
    handler: httpx.MockTransport | None, clock: FakeClock
) -> tuple[JsonKnowledgeProvider, httpx.AsyncClient]:
    http = httpx.AsyncClient(transport=handler)
    provider = JsonKnowledgeProvider(
        "https://example.test/knowledge.json", http=http, ttl_seconds=100, clock=clock
    )
    return provider, http


@pytest.mark.anyio
async def test_json_provider_caches_until_ttl() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_doc(_fact()))

    clock = FakeClock()
    provider, http = _provider(httpx.MockTransport(handler), clock)
    async with http:
        first = await provider.get_facts()
        clock.now = 99
        second = await provider.get_facts()
        assert len(calls) == 1
        clock.now = 101
        await provider.get_facts()

    assert first == second
    assert len(calls) == 2


@pytest.mark.anyio
async def test_json_provider_keeps_last_good_on_failure() -> None:
    responses = [httpx.Response(200, json=_doc(_fact())), httpx.Response(500)]

    clock = FakeClock()
    provider, http = _provider(httpx.MockTransport(lambda request: responses.pop(0)), clock)
    async with http:
        first = await provider.get_facts()
        clock.now = 101
        second = await provider.get_facts()

    assert second == first


@pytest.mark.anyio
async def test_json_provider_without_any_copy_raises_llm_error() -> None:
    provider, http = _provider(
        httpx.MockTransport(lambda request: httpx.Response(500)), FakeClock()
    )
    async with http:
        with pytest.raises(LLMError, match="knowledge unavailable"):
            await provider.get_facts()


@pytest.mark.anyio
async def test_json_provider_reads_local_path(tmp_path) -> None:
    path = tmp_path / "knowledge.json"
    path.write_text(json.dumps(_doc(_fact())), encoding="utf-8")
    async with httpx.AsyncClient() as http:
        facts = await JsonKnowledgeProvider(str(path), http=http).get_facts()

    assert [f.id for f in facts] == ["cv.nubank"]
