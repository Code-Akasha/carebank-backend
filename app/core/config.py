from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql://carebank:password@localhost:5432/carebank_db"
    redis_url: str = "redis://localhost:6379"
    mock_bank_url: str = "http://localhost:3001"
    openai_api_key: str = ""
    ollama_base_url: str | None = None
    gemini_api_key: str = ""
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
