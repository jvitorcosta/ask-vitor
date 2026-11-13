from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import anthropic
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import health, qa
from app.core.config import Settings, get_settings
from app.core.exceptions import LLMError
from app.core.logstore import LogStore, MemoryStore, UpstashStore
from app.core.ratelimit import RateLimited, RateLimiter
from app.knowledge.context import JsonKnowledgeProvider, StaticKnowledgeProvider
from app.knowledge.facts import KnowledgeProvider
from app.llm.anthropic import AnthropicClient
from app.llm.base import LLMClient
from app.llm.ollama import OllamaClient


def build_log_store(settings: Settings, http: httpx.AsyncClient) -> LogStore:
    if settings.upstash_redis_rest_url and settings.upstash_redis_rest_token:
        return UpstashStore(
            settings.upstash_redis_rest_url,
            settings.upstash_redis_rest_token.get_secret_value(),
            http=http,
        )
    return MemoryStore()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    async with AsyncExitStack() as stack:
        llm: LLMClient
        if settings.llm_backend == "anthropic":
            if (
                settings.anthropic_api_key is None
                or not settings.anthropic_api_key.get_secret_value()
            ):
                raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_BACKEND=anthropic")
            sdk = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key.get_secret_value(),
                timeout=settings.anthropic_timeout_seconds,
                max_retries=0,
            )
            stack.push_async_callback(sdk.close)
            llm = AnthropicClient(
                sdk, model=settings.anthropic_model, max_tokens=settings.max_output_tokens
            )
        else:
            http_client = await stack.enter_async_context(
                httpx.AsyncClient(
                    base_url=settings.ollama_base_url,
                    timeout=settings.ollama_timeout_seconds,
                )
            )
            llm = OllamaClient(http_client, model=settings.ollama_model)
        app.state.llm_client = llm
        # Separate client: the Ollama one has a base_url and a long LLM timeout.
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as knowledge_http:
            knowledge: KnowledgeProvider = (
                JsonKnowledgeProvider(settings.knowledge_source, http=knowledge_http)
                if settings.knowledge_source
                else StaticKnowledgeProvider()
            )
            app.state.knowledge_provider = knowledge
            async with httpx.AsyncClient(timeout=5.0) as log_http:
                app.state.log_store = build_log_store(settings, log_http)
                yield


async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "LLM service unavailable"})


async def rate_limited_handler(request: Request, exc: RateLimited) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "rate_limited"})


def create_app() -> FastAPI:
    app = FastAPI(title="ask-vitor", lifespan=lifespan)
    app.state.rate_limiter = RateLimiter(get_settings().rate_limit_per_hour, 3600)
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
    app.add_exception_handler(RateLimited, rate_limited_handler)
    return app


app = create_app()
