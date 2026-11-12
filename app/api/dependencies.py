from typing import Annotated

from fastapi import Depends, Request

from app.knowledge.facts import KnowledgeProvider
from app.llm.base import LLMClient
from app.services.qa import QAService


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client


def get_knowledge_provider(request: Request) -> KnowledgeProvider:
    return request.app.state.knowledge_provider


def get_qa_service(
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    knowledge: Annotated[KnowledgeProvider, Depends(get_knowledge_provider)],
) -> QAService:
    return QAService(llm=llm, knowledge=knowledge)
