import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _production_settings_kwargs() -> dict[str, str]:
    return {
        "banking_api_url": "https://banking.example.com",
        "banking_api_secret": "test-banking-secret-0123456789abcdef-long",
        "jwt_secret": "test-jwt-secret-0123456789abcdef-long",
        "environment": "production",
        "backend_public_url": "https://backend.example.com",
        "cors_origins": '["https://carebank-frontend.vercel.app"]',
    }


def test_production_settings_accept_https_configuration():
    settings = Settings(**_production_settings_kwargs())

    assert settings.backend_public_url == "https://backend.example.com"
    assert settings.get_cors_origins() == ["https://carebank-frontend.vercel.app"]


def test_production_settings_reject_http_backend_url():
    kwargs = _production_settings_kwargs()
    kwargs["backend_public_url"] = "http://backend.example.com"

    with pytest.raises(
        ValidationError, match="BACKEND_PUBLIC_URL must use https:// in production",
    ):
        Settings(**kwargs)


def test_production_settings_require_cors_origins():
    kwargs = _production_settings_kwargs()
    kwargs["cors_origins"] = ""

    with pytest.raises(ValidationError, match="CORS_ORIGINS is required in production"):
        Settings(**kwargs)
