from typing import Annotated

from fastapi import Depends, Request

from app.knowledge.context import ContextProvider, StaticContextProvider
from app.llm.base import LLMClient
from app.services.qa import QAService


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client


def get_context_provider() -> ContextProvider:
    return StaticContextProvider()


def get_qa_service(
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    context_provider: Annotated[ContextProvider, Depends(get_context_provider)],
) -> QAService:
    return QAService(llm=llm, context_provider=context_provider)
