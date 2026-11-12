from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_llm_client, get_log_store
from app.core.exceptions import LLMError
from app.core.logstore import MemoryStore
from app.llm.base import Message
from app.main import create_app


class FakeLLMClient:
    def __init__(self, answer: str = "  A canned answer.  ", fail: bool = False) -> None:
        self.answer = answer
        self.fail = fail
        self.tokens: list[str] = ["A canned ", "answer."]
        self.fail_after: int | None = None  # stream: raise after this many tokens
        self.received: list[list[Message]] = []

    async def chat(self, messages: list[Message]) -> str:
        self.received.append(messages)
        if self.fail:
            raise LLMError("boom")
        return self.answer

    async def stream_chat(self, messages: list[Message]) -> AsyncIterator[str]:
        self.received.append(messages)
        if self.fail:
            raise LLMError("boom")
        for index, token in enumerate(self.tokens):
            if index == self.fail_after:
                raise LLMError("boom mid-stream")
            yield token


@pytest.fixture
def fake_llm() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def client(fake_llm: FakeLLMClient, store: MemoryStore) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    app.dependency_overrides[get_log_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
