from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import health, qa
from app.core.config import get_settings
from app.core.exceptions import LLMError
from app.llm.ollama import OllamaClient


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url=settings.ollama_base_url,
        timeout=settings.ollama_timeout_seconds,
    ) as http_client:
        app.state.llm_client = OllamaClient(http_client, model=settings.ollama_model)
        yield


async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "LLM service unavailable"})


def create_app() -> FastAPI:
    app = FastAPI(title="ask-vitor", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(qa.router)
    app.add_exception_handler(LLMError, llm_error_handler)
    return app


app = create_app()
