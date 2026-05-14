from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class BankingConnectorConfigCreate(BaseModel):
    base_url: str = Field(..., description="Bank API base URL")
    secret: str | None = Field(None, description="JWT secret for banking mock provider")
    request_timeout_sec: int = Field(default=10, ge=3, le=120)

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value


class BankingConnectorConfigResponse(BaseModel):
    id: int
    environment: str
    provider_type: str
    base_url: str
    secret_masked: str | None = None
    request_timeout_sec: int
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
    last_connectivity_check: datetime | None = None
    last_error: str | None = None

    model_config = {"from_attributes": True}


class BankingConnectorTestResponse(BaseModel):
    status: str
    providers_count: int | None = None
    error: str | None = None
