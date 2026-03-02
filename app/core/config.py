from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Preferred: set the full URL via env var DATABASE_URL
    # Falls back to building from individual parts if not set
    database_url: str = ""
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "carebank"
    db_password: str = ""
    db_name: str = "carebank_db"

    redis_url: str = "redis://localhost:6379"
    banking_api_url: str = "http://localhost:8001"
    banking_api_secret: str = "mockbank-dev-secret"
    openai_api_key: str = ""
    ollama_base_url: str | None = "http://localhost:11434"
    gemini_api_key: str = ""
    jwt_secret: str = "carebank-backend-secret-2026-hackathon"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def get_database_url(self) -> str:
        """Return a properly-encoded PostgreSQL URL, using individual parts when DATABASE_URL is not set."""
        if self.database_url:
            return self.database_url
        from sqlalchemy.engine import URL

        return URL.create(
            drivername="postgresql",
            username=self.db_user.strip(),
            password=self.db_password.strip(),
            host=self.db_host.strip(),
            port=self.db_port,
            database=self.db_name.strip(),
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
