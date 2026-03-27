from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    openai_api_key: str
    groq_api_key: str = ""  
    postgres_url: str
    youtube_api_key: str = ''
    slack_webhook_url: str = ''
    env: str = 'development'
    log_level: str = 'INFO'
    max_tokens_per_call: int = 4000  # safety limit per LLM call
    similarity_threshold: float = 0.92  # RAG dedup threshold

    class Config:
        env_file = '.env'

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()