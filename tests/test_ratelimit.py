from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.dependencies import get_log_store, get_rate_limiter
from app.core.config import get_settings
from app.core.logstore import MemoryStore
from app.core.ratelimit import RateLimiter, client_key
from tests.conftest import FakeLLMClient


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make_request(headers: dict[str, str], host: str = "10.0.0.1") -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (host, 1234),
    }
    return Request(scope)


def test_allows_up_to_limit_then_blocks() -> None:
    limiter = RateLimiter(10, 3600)
    assert all(limiter.allow("a") for _ in range(10))
    assert limiter.allow("a") is False
    assert limiter.allow("b") is True


def test_window_slides() -> None:
    clock = FakeClock()
    limiter = RateLimiter(10, 3600, clock=clock)
    assert all(limiter.allow("a") for _ in range(10))
    assert limiter.allow("a") is False
    clock.now += 3601
    assert limiter.allow("a") is True


def test_prunes_idle_keys() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 10, clock=clock)
    limiter.allow("a")
    clock.now += 11
    limiter.allow("b")
    assert "a" not in limiter._hits


def test_client_key_prefers_forwarded_for() -> None:
    request = make_request({"X-Forwarded-For": "203.0.113.9, 10.0.0.1"})
    assert client_key(request) == "203.0.113.9"


def test_client_key_falls_back_to_client_host() -> None:
    assert client_key(make_request({}, host="198.51.100.4")) == "198.51.100.4"


@pytest.fixture
def limited(
    fake_llm: FakeLLMClient, store: MemoryStore, client: TestClient
) -> Iterator[TestClient]:
    limiter = RateLimiter(10, 3600)
    client.app.dependency_overrides[get_rate_limiter] = lambda: limiter
    yield client


@pytest.mark.parametrize("path", ["/ask", "/ask/stream"])
def test_ask_returns_429_after_limit(
    limited: TestClient, fake_llm: FakeLLMClient, path: str
) -> None:
    for _ in range(10):
        assert limited.post(path, json={"question": "Who is Vitor?"}).status_code == 200
    calls = len(fake_llm.received)
    response = limited.post(path, json={"question": "Who is Vitor?"})
    assert response.status_code == 429
    assert response.json() == {"detail": "rate_limited"}
    assert len(fake_llm.received) == calls


def test_invalid_question_does_not_consume_quota(limited: TestClient, store: MemoryStore) -> None:
    for _ in range(15):
        assert limited.post("/ask", json={"question": ""}).status_code == 422
    assert limited.post("/ask", json={"question": "Who is Vitor?"}).status_code == 200


def test_daily_cap_returns_429(
    client: TestClient, store: MemoryStore, fake_llm: FakeLLMClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "daily_question_cap", 2)
    client.app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(100, 3600)
    for _ in range(2):
        assert client.post("/ask", json={"question": "Who is Vitor?"}).status_code == 200
    calls = len(fake_llm.received)
    response = client.post("/ask", json={"question": "Who is Vitor?"})
    assert response.status_code == 429
    assert response.json() == {"detail": "rate_limited"}
    assert len(fake_llm.received) == calls


def test_invalid_question_does_not_consume_daily_counter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "daily_question_cap", 1)
    client.app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(100, 3600)
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={"question": "Who is Vitor?"}).status_code == 200


def test_daily_counter_failure_fails_open(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    class BrokenStore(MemoryStore):
        async def incr_daily(self, day: str) -> int:
            raise KeyError("result")

    client.app.dependency_overrides[get_log_store] = lambda: BrokenStore()
    client.app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(100, 3600)
    assert client.post("/ask", json={"question": "Who is Vitor?"}).status_code == 200
    err = capsys.readouterr().err
    assert "daily cap" in err
