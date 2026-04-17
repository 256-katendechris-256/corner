# agent/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # OpenAI — optional, empty if using Groq
    openai_api_key: str = ""

    # Groq — used for scoring
    groq_api_key: str = ""

    # Database
    postgres_url: str

    # Optional integrations
    youtube_api_key: str = ""
    slack_webhook_url: str = ""
    firecrawl_api_key: str = ""

    # Runtime
    env: str = "development"
    log_level: str = "INFO"

    # Pipeline tuning
    max_tokens_per_call: int = 4000
    similarity_threshold: float = 0.92

    # Langfuse observability
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()