import sys
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import get_settings
from app.core.logstore import LogStore
from app.core.ratelimit import RateLimited, RateLimiter, client_key
from app.knowledge.facts import KnowledgeProvider
from app.llm.base import LLMClient
from app.schemas.qa import AskRequest
from app.services.qa import QAService


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client


def get_knowledge_provider(request: Request) -> KnowledgeProvider:
    return request.app.state.knowledge_provider


def get_log_store(request: Request) -> LogStore:
    return request.app.state.log_store


def get_qa_service(
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    knowledge: Annotated[KnowledgeProvider, Depends(get_knowledge_provider)],
) -> QAService:
    return QAService(llm=llm, knowledge=knowledge)


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


async def enforce_limits(
    http_request: Request,
    # Taking the body makes FastAPI skip this check when validation fails, so a 422
    # never uses up the visitor's quota or the daily counter.
    request: AskRequest,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    log_store: Annotated[LogStore, Depends(get_log_store)],
) -> None:
    if not limiter.allow(client_key(http_request)):
        raise RateLimited
    day = datetime.now(UTC).date().isoformat()
    try:
        count = await log_store.incr_daily(day)
    except Exception as error:  # fail open: a broken counter must never block visitors
        print(
            f"daily cap check failed, allowing the question: {type(error).__name__}",
            file=sys.stderr,
        )
        return
    if count > get_settings().daily_question_cap:
        raise RateLimited
