from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import health, qa
from app.core.config import get_settings
from app.core.exceptions import LLMError
from app.knowledge.context import JsonKnowledgeProvider, StaticKnowledgeProvider
from app.knowledge.facts import KnowledgeProvider
from app.llm.ollama import OllamaClient


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url=settings.ollama_base_url,
        timeout=settings.ollama_timeout_seconds,
    ) as http_client:
        app.state.llm_client = OllamaClient(http_client, model=settings.ollama_model)
        # Separate client: the Ollama one has a base_url and a long LLM timeout.
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as knowledge_http:
            knowledge: KnowledgeProvider = (
                JsonKnowledgeProvider(settings.knowledge_source, http=knowledge_http)
                if settings.knowledge_source
                else StaticKnowledgeProvider()
            )
            app.state.knowledge_provider = knowledge
            yield


async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "LLM service unavailable"})


def create_app() -> FastAPI:
    app = FastAPI(title="ask-vitor", lifespan=lifespan)
    # The web app is served from another origin (localhost:3000), so the browser blocks its
    # calls unless the API says that origin is allowed (CORS).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(qa.router)
    app.add_exception_handler(LLMError, llm_error_handler)
    return app


app = create_app()
