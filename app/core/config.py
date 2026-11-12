from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:1.5b"
    ollama_timeout_seconds: float = 60.0
    # URL or path of the site's knowledge.json; empty means the built-in knowledge base.
    knowledge_source: str = ""
    # Browser origins allowed to call the API (the Next.js app in web/ runs on port 3000).
    cors_origins: list[str] = ["http://localhost:3000"]
    # Both set: the question log goes to Upstash Redis. Otherwise it stays in memory.
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: SecretStr | None = None
    # Questions per visitor per hour, and questions across all visitors per UTC day.
    rate_limit_per_hour: int = 10
    daily_question_cap: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
