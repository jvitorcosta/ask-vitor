from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_llm_client
from app.core.exceptions import LLMError
from app.llm.base import Message
from app.main import create_app


class FakeLLMClient:
    def __init__(self, answer: str = "  A canned answer.  ", fail: bool = False) -> None:
        self.answer = answer
        self.fail = fail
        self.received: list[list[Message]] = []

    async def chat(self, messages: list[Message]) -> str:
        self.received.append(messages)
        if self.fail:
            raise LLMError("boom")
        return self.answer


@pytest.fixture
def fake_llm() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
def client(fake_llm: FakeLLMClient) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    with TestClient(app) as test_client:
        yield test_client
