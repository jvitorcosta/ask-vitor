from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_qa_service
from app.schemas.qa import AskRequest, AskResponse
from app.services.qa import QAService

router = APIRouter(tags=["qa"])


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
