import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from app.core.logstore import LogRecord, MemoryStore, UpstashStore, redact
from tests.conftest import FakeLLMClient
from tests.test_ask_stream import parse_sse


def test_redact_email_and_phone() -> None:
    text = "mail me at a.b@x.com or +55 (92) 99999-0000"
    assert redact(text) == "mail me at [email] or [phone]"


def test_redact_keeps_years() -> None:
    assert redact("in 2024") == "in 2024"


def test_upstash_save_sends_set_with_90_day_expiry() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"result": "OK"}])

    record = LogRecord("q?", "a.", "answer", ["cv.nubank"], 120, "2026-11-12")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await UpstashStore("https://redis.example", "tok", http=http).save(record)

    asyncio.run(run())

    (request,) = seen
    assert str(request.url) == "https://redis.example/pipeline"
    assert request.headers["authorization"] == "Bearer tok"
    (command,) = json.loads(request.content)
    assert command[0] == "SET"
    assert command[1].startswith("log:")
    assert command[3:] == ["EX", "7776000"]
    stored = json.loads(command[2])
    assert stored == {
        "question": "q?",
        "answer": "a.",
        "kind": "answer",
        "sources": ["cv.nubank"],
        "latency_ms": 120,
        "date": "2026-11-12",
    }
    assert "ip" not in stored
    assert "user_agent" not in stored


def test_upstash_incr_daily_increments_and_expires() -> None:
    seen: list[list] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=[{"result": 3}, {"result": 1}])

    async def run() -> int:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            store = UpstashStore("https://redis.example", "tok", http=http)
            return await store.incr_daily("2026-11-12")

    assert asyncio.run(run()) == 3
    assert seen == [[["INCR", "daily:2026-11-12"], ["EXPIRE", "daily:2026-11-12", "172800"]]]


def test_memory_store_counts_per_day() -> None:
    store = MemoryStore()
    counts = [
        asyncio.run(store.incr_daily(day)) for day in ["2026-11-12", "2026-11-12", "2026-11-13"]
    ]
    assert counts == [1, 2, 1]


def test_stream_logs_after_done(client: TestClient, store: MemoryStore) -> None:
    client.post("/ask/stream", json={"question": "Mail a.b@x.com about Nubank?"})

    (record,) = store.records
    assert record.kind == "answer"
    assert record.question == "Mail [email] about Nubank?"
    assert record.answer == "A canned answer."
    assert record.sources == []
    assert record.latency_ms >= 0
    assert len(record.date) == 10


def test_ask_logs_cited_source_ids(
    client: TestClient, fake_llm: FakeLLMClient, store: MemoryStore
) -> None:
    fake_llm.answer = "He worked at Nubank.\n<<sources: base.2>>"

    client.post("/ask", json={"question": "Where?"})

    assert store.records[0].sources == ["base.2"]


def test_log_failure_does_not_break_answer(client: TestClient, store: MemoryStore) -> None:
    async def boom(record: LogRecord) -> None:
        raise RuntimeError("redis down")

    store.save = boom  # type: ignore[method-assign]  # test double

    response = client.post("/ask/stream", json={"question": "What does Vitor do?"})

    assert response.status_code == 200
    assert parse_sse(response.text)[-1][0] == "done"
    assert client.post("/ask", json={"question": "Again?"}).status_code == 200


def test_mid_stream_error_is_not_logged(
    client: TestClient, fake_llm: FakeLLMClient, store: MemoryStore
) -> None:
    fake_llm.fail_after = 1

    client.post("/ask/stream", json={"question": "What does Vitor do?"})

    assert store.records == []
