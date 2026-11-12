import json
import sys
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import enforce_limits, get_log_store, get_qa_service
from app.core.exceptions import LLMError
from app.core.logstore import LogRecord, LogStore, redact
from app.schemas.qa import AskRequest, AskResponse, SourceOut
from app.services.qa import Answer, QAService

router = APIRouter(tags=["qa"])

LLM_UNAVAILABLE = {"detail": "LLM service unavailable"}


@router.post(
    "/ask",
    response_model=AskResponse,
    dependencies=[Depends(enforce_limits)],
    responses={
        429: {"description": "Rate limited"},
        503: {"description": "LLM service unavailable"},
    },
)
async def ask(
    request: AskRequest,
    service: Annotated[QAService, Depends(get_qa_service)],
    log_store: Annotated[LogStore, Depends(get_log_store)],
) -> AskResponse:
    started = time.perf_counter()
    answer = await service.answer(request.question)
    await _log(log_store, request.question, answer, started)
    return AskResponse(
        question=request.question,
        answer=answer.text,
        kind=answer.kind,
        sources=_sources_out(answer),
    )


def _sources_out(answer: Answer) -> list[SourceOut]:
    return [
        SourceOut(id=fact.id, label=fact.source, updated=fact.updated) for fact in answer.sources
    ]


async def _log(store: LogStore, question: str, answer: Answer, started: float) -> None:
    """Save an anonymous, redacted record. A failing store must never break the answer."""
    record = LogRecord(
        question=redact(question),
        answer=redact(answer.text),
        kind=answer.kind,
        sources=[fact.id for fact in answer.sources],
        latency_ms=round((time.perf_counter() - started) * 1000),
        date=datetime.now(UTC).date().isoformat(),
    )
    try:
        await store.save(record)
    except Exception as error:  # best-effort: a failing log must not break the answer
        print(f"question log failed: {error!r}", file=sys.stderr)


def sse(data: dict, event: str | None = None) -> str:
    """Format one Server-Sent Event. JSON keeps newlines inside a token from breaking the frame."""
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data)}\n\n"


@router.post(
    "/ask/stream",
    response_class=StreamingResponse,
    dependencies=[Depends(enforce_limits)],
    responses={
        429: {
            "description": "Rate limited (hourly per visitor, or the daily cap): "
            '`{"detail": "rate_limited"}`'
        },
        200: {
            "content": {"text/event-stream": {}},
            "description": 'Events: `data: {"token": "..."}` per piece of the answer, then '
            '`event: done` with `data: {"kind": "answer" | "fallback" | "off_topic", '
            '"sources": [{"id", "label", "updated"}]}`. If the LLM fails mid-answer: '
            "`event: error` instead.",
        },
        503: {"description": "LLM service unavailable"},
    },
)
async def ask_stream(
    request: AskRequest,
    service: Annotated[QAService, Depends(get_qa_service)],
    log_store: Annotated[LogStore, Depends(get_log_store)],
) -> StreamingResponse:
    started = time.perf_counter()
    items = service.answer_stream(request.question)

    # Wait for the first item before answering. Once a stream starts, the 200 status is
    # already sent, so this is the last moment a failure (e.g. Ollama down) can become a
    # proper 503 instead of an error event. LLMError propagates to the app's 503 handler.
    first = await anext(items)

    def frame(item: str | Answer) -> str:
        if isinstance(item, Answer):
            done = {
                "kind": item.kind,
                "sources": [source.model_dump() for source in _sources_out(item)],
            }
            return sse(done, event="done")
        return sse({"token": item})

    # The record is saved before `done` goes out: a client that disconnects once it has the
    # answer cancels this generator at its next yield, which would drop a write placed after it.
    # Latency still runs to the end of the answer, since the Answer item comes last.
    async def events() -> AsyncIterator[str]:
        try:
            if isinstance(first, Answer):
                await _log(log_store, request.question, first, started)
            yield frame(first)
            async for item in items:
                if isinstance(item, Answer):
                    await _log(log_store, request.question, item, started)
                yield frame(item)
        except LLMError:
            yield sse(LLM_UNAVAILABLE, event="error")

    return StreamingResponse(events(), media_type="text/event-stream")
