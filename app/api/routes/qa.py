import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_qa_service
from app.core.exceptions import LLMError
from app.schemas.qa import AskRequest, AskResponse, SourceOut
from app.services.qa import Answer, QAService

router = APIRouter(tags=["qa"])

LLM_UNAVAILABLE = {"detail": "LLM service unavailable"}


@router.post(
    "/ask",
    response_model=AskResponse,
    responses={503: {"description": "LLM service unavailable"}},
)
async def ask(
    request: AskRequest,
    service: Annotated[QAService, Depends(get_qa_service)],
) -> AskResponse:
    answer = await service.answer(request.question)
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


def sse(data: dict, event: str | None = None) -> str:
    """Format one Server-Sent Event. JSON keeps newlines inside a token from breaking the frame."""
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data)}\n\n"


@router.post(
    "/ask/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": 'Events: `data: {"token": "..."}` per piece of the answer, then '
            "`event: done`. If the LLM fails mid-answer: `event: error`.",
        },
        503: {"description": "LLM service unavailable"},
    },
)
async def ask_stream(
    request: AskRequest,
    service: Annotated[QAService, Depends(get_qa_service)],
) -> StreamingResponse:
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

    async def events() -> AsyncIterator[str]:
        try:
            yield frame(first)
            async for item in items:
                yield frame(item)
        except LLMError:
            yield sse(LLM_UNAVAILABLE, event="error")

    return StreamingResponse(events(), media_type="text/event-stream")
