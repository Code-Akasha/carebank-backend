import json
import hashlib
from urllib.parse import urlparse
from pydantic_settings import BaseSettings
from pydantic import model_validator
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
    banking_api_url: str
    banking_api_secret: str
    backend_public_url: str = "http://localhost:8000"
    mockbank_webhook_secret: str = ""
    mockbank_webhook_signature_tolerance_seconds: int = 300
    openai_api_key: str = ""
    ollama_base_url: str | None = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    cors_origins: str = ""
    environment: str = "development"

    # Financial thresholds (configurable, previously hardcoded)
    whatif_low_threshold: float = 70.0
    whatif_medium_threshold: float = 30.0
    affordability_safe_buffer: float = 10000.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="after")
    def ensure_runtime_secrets(self):
        if not self.mockbank_webhook_secret:
            self.mockbank_webhook_secret = self.banking_api_secret

        if not self.jwt_secret:
            if self.banking_api_secret:
                self.jwt_secret = hashlib.sha256(
                    self.banking_api_secret.encode("utf-8")
                ).hexdigest()
            else:
                raise ValueError(
                    "JWT_SECRET is required (or provide BANKING_API_SECRET to derive one)"
                )
        return self

    def get_cors_origins(self) -> list[str]:
        def expand_dev_aliases(origins: list[str]) -> list[str]:
            expanded: list[str] = []
            seen: set[str] = set()

            for origin in origins:
                if origin not in seen:
                    seen.add(origin)
                    expanded.append(origin)

                parsed = urlparse(origin)
                scheme = parsed.scheme
                host = parsed.hostname
                port = parsed.port

                if not scheme or not host:
                    continue

                if host not in {"localhost", "127.0.0.1", "0.0.0.0"}:
                    continue

                for alias in ("localhost", "127.0.0.1", "0.0.0.0"):
                    alias_origin = f"{scheme}://{alias}"
                    if port:
                        alias_origin = f"{alias_origin}:{port}"
                    if alias_origin not in seen:
                        seen.add(alias_origin)
                        expanded.append(alias_origin)

            return expanded

        value = self.cors_origins
        if value is None or value == "":
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        origins = [
                            str(item).strip() for item in parsed if str(item).strip()
                        ]
                        return expand_dev_aliases(origins)
                except json.JSONDecodeError:
                    pass
            origins = [item.strip() for item in stripped.split(",") if item.strip()]
            return expand_dev_aliases(origins)
        return []

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
