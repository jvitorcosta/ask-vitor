import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_qa_service
from app.core.exceptions import LLMError
from app.schemas.qa import AskRequest, AskResponse
from app.services.qa import QAService

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
    return AskResponse(question=request.question, answer=answer)


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
    tokens = service.answer_stream(request.question)

    # Wait for the first token before answering. Once a stream starts, the 200 status is
    # already sent, so this is the last moment a failure (e.g. Ollama down) can become a
    # proper 503 instead of an error event. LLMError propagates to the app's 503 handler.
    first = await anext(tokens, None)

    async def events() -> AsyncIterator[str]:
        try:
            if first is not None:
                yield sse({"token": first})
            async for token in tokens:
                yield sse({"token": token})
        except LLMError:
            yield sse(LLM_UNAVAILABLE, event="error")
            return
        yield sse({}, event="done")

    return StreamingResponse(events(), media_type="text/event-stream")
