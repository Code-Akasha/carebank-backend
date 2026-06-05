"""Pydantic schemas for Admin LLM Configuration API contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ============================================================================
# Tunnel Configuration Schemas
# ============================================================================


class LLMTunnelConfigCreate(BaseModel):
    """Request schema for creating/updating LLM provider configuration."""

    provider_type: Literal["ollama", "gemini", "openai"] = Field(
        default="ollama",
        description="Configured provider type",
    )

    tunnel_url: str | None = Field(
        None,
        description="Base URL for Ollama or OpenAI-compatible endpoints",
    )
    tunnel_auth_token: str | None = Field(
        None,
        description="API key or auth token for the selected provider (encrypted at rest)",
    )
    ollama_model_default: str = Field(
        default="qwen3:8b",
        description="Default model to use for the selected provider",
    )
    request_timeout_sec: int = Field(
        default=30,
        ge=5,
        le=300,
        description="HTTP request timeout in seconds",
    )

    @model_validator(mode="after")
    def validate_provider_config(self):
        provider = (self.provider_type or "ollama").strip().lower()
        if provider in {"ngrok", "local", "ollama"}:
            provider = "ollama"

        if provider == "ollama":
            if not self.tunnel_url or not self.tunnel_url.strip():
                raise ValueError("tunnel_url is required for local Ollama")
            self.tunnel_url = self.tunnel_url.strip()
        elif self.tunnel_url:
            self.tunnel_url = self.tunnel_url.strip()

        if not self.ollama_model_default or not self.ollama_model_default.strip():
            raise ValueError("ollama_model_default cannot be empty")

        self.provider_type = provider  # type: ignore[assignment]
        self.ollama_model_default = self.ollama_model_default.strip()
        return self

    @field_validator("tunnel_url")
    @classmethod
    def validate_tunnel_url(cls, v: str) -> str:
        """Validate tunnel URL format when provided."""
        if not v:
            return v
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("tunnel_url must start with http:// or https://")
        if len(v) > 1000:
            raise ValueError("tunnel_url too long")
        return v


class LLMTunnelConfigResponse(BaseModel):
    """Response schema for LLM provider configuration."""

    id: int
    environment: str
    provider_type: str
    tunnel_url: str
    tunnel_auth_token_masked: str | None = Field(
        None,
        description="Masked token (e.g., '****...****') for display purposes",
    )
    ollama_model_default: str
    request_timeout_sec: int
    is_active: bool
    last_connectivity_check: datetime | None = None
    last_error: str | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LLMProviderConfigResponse(BaseModel):
    """Convenience response wrapper for provider summaries."""

    provider_type: str
    provider_label: str
    tunnel_url: str | None = None
    ollama_model_default: str

    model_config = {"from_attributes": True}


# ============================================================================
# Model Discovery Schemas
# ============================================================================


class OllamaModelInfo(BaseModel):
    """Information about an available Ollama model."""

    name: str
    size_gb: float = 0.0
    size_bytes: int = 0
    available: bool


class ModelListResponse(BaseModel):
    """Response schema for model discovery."""

    models: list[OllamaModelInfo]
    model_count: int


class ConnectivityTestResult(BaseModel):
    """Result of a connectivity test to Ollama instance."""

    status: str = Field(
        ...,
        description="'ok' if connection successful, 'error' if failed",
    )
    models_count: int | None = Field(None, description="Number of models discovered")
    response_time_ms: float | None = Field(
        None,
        description="Response time in milliseconds",
    )
    error: str | None = Field(None, description="Error message if status is 'error'")


# ============================================================================
# Prompt Configuration Schemas
# ============================================================================


class AgentPromptConfigCreate(BaseModel):
    """Request schema for creating/updating an agent prompt."""

    system_prompt: str = Field(
        ...,
        description="System prompt template for the agent",
        max_length=50000,
    )
    notes: str | None = Field(
        None,
        description="Admin notes about this prompt version",
        max_length=1000,
    )

    @field_validator("system_prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        """Validate prompt is not empty."""
        if not v or not v.strip():
            raise ValueError("system_prompt cannot be empty")
        return v


class AgentPromptConfigResponse(BaseModel):
    """Response schema for agent prompt configuration."""

    id: int
    agent_name: str
    environment: str
    system_prompt: str
    version: int
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
    notes: str | None = None

    class Config:
        from_attributes = True


class AgentPromptHistoryResponse(BaseModel):
    """Response schema for prompt version history."""

    id: int
    agent_name: str
    environment: str
    version: int
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
    notes: str | None = None

    class Config:
        from_attributes = True


class PromptListResponse(BaseModel):
    """Response schema for listing all prompts or prompts by agent."""

    prompts: list[AgentPromptConfigResponse]
    total_count: int


# ============================================================================
# Error Response Schemas
# ============================================================================


class ErrorResponse(BaseModel):
    """Standard error response for LLM routes."""

    status: str = "error"
    code: str = Field(..., description="Error code (e.g., 'llm_tunnel_unavailable')")
    message: str = Field(..., description="User-friendly error message")
    remediation: str | None = Field(
        None,
        description="Admin-actionable remediation steps",
    )


class ValidationErrorResponse(BaseModel):
    """Response for validation errors."""

    status: str = "error"
    code: str = "validation_error"
    message: str
    details: dict | None = Field(None, description="Field-level validation errors")


# ============================================================================
# Admin Action Audit Schemas
# ============================================================================


class AdminActionLogResponse(BaseModel):
    """Response schema for admin action audit log entry."""

    id: int
    admin_user_id: str
    action_type: str
    resource_type: str
    resource_id: str | None = None
    environment: str | None = None
    before_value: str | None = None
    after_value: str | None = None
    status: str
    error_message: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True
