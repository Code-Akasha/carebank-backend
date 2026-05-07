"""
Pydantic schemas for Admin LLM Configuration API contracts.
"""

from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Optional, List
from datetime import datetime


# ============================================================================
# Tunnel Configuration Schemas
# ============================================================================

class LLMTunnelConfigCreate(BaseModel):
    """Request schema for creating/updating tunnel configuration."""

    tunnel_url: str = Field(
        ...,
        description="Base URL of ngrok tunnel or other secure tunnel endpoint"
    )
    tunnel_auth_token: Optional[str] = Field(
        None,
        description="Authentication token for the tunnel (will be encrypted at rest)"
    )
    ollama_model_default: str = Field(
        default="qwen3:8b",
        description="Default Ollama model to use from this tunnel"
    )
    request_timeout_sec: int = Field(
        default=30,
        ge=5,
        le=300,
        description="HTTP request timeout in seconds"
    )

    @field_validator("tunnel_url")
    @classmethod
    def validate_tunnel_url(cls, v: str) -> str:
        """Validate tunnel URL format."""
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("tunnel_url must start with http:// or https://")
        if len(v) > 1000:
            raise ValueError("tunnel_url too long")
        return v


class LLMTunnelConfigResponse(BaseModel):
    """Response schema for tunnel configuration."""

    id: int
    environment: str
    provider_type: str
    tunnel_url: str
    tunnel_auth_token_masked: Optional[str] = Field(
        None,
        description="Masked token (e.g., '****...****') for display purposes"
    )
    ollama_model_default: str
    request_timeout_sec: int
    is_active: bool
    last_connectivity_check: Optional[datetime] = None
    last_error: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Model Discovery Schemas
# ============================================================================

class OllamaModelInfo(BaseModel):
    """Information about an available Ollama model."""

    name: str
    size_gb: float
    size_bytes: int
    available: bool


class ModelListResponse(BaseModel):
    """Response schema for model discovery."""

    models: List[OllamaModelInfo]
    model_count: int


class ConnectivityTestResult(BaseModel):
    """Result of a connectivity test to Ollama instance."""

    status: str = Field(
        ...,
        description="'ok' if connection successful, 'error' if failed"
    )
    models_count: Optional[int] = Field(None, description="Number of models discovered")
    response_time_ms: Optional[float] = Field(None, description="Response time in milliseconds")
    error: Optional[str] = Field(None, description="Error message if status is 'error'")


# ============================================================================
# Prompt Configuration Schemas
# ============================================================================

class AgentPromptConfigCreate(BaseModel):
    """Request schema for creating/updating an agent prompt."""

    system_prompt: str = Field(
        ...,
        description="System prompt template for the agent",
        max_length=50000
    )
    notes: Optional[str] = Field(
        None,
        description="Admin notes about this prompt version",
        max_length=1000
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
    notes: Optional[str] = None

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
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class PromptListResponse(BaseModel):
    """Response schema for listing all prompts or prompts by agent."""

    prompts: List[AgentPromptConfigResponse]
    total_count: int


# ============================================================================
# Error Response Schemas
# ============================================================================

class ErrorResponse(BaseModel):
    """Standard error response for LLM routes."""

    status: str = "error"
    code: str = Field(..., description="Error code (e.g., 'llm_tunnel_unavailable')")
    message: str = Field(..., description="User-friendly error message")
    remediation: Optional[str] = Field(
        None,
        description="Admin-actionable remediation steps"
    )


class ValidationErrorResponse(BaseModel):
    """Response for validation errors."""

    status: str = "error"
    code: str = "validation_error"
    message: str
    details: Optional[dict] = Field(None, description="Field-level validation errors")


# ============================================================================
# Admin Action Audit Schemas
# ============================================================================

class AdminActionLogResponse(BaseModel):
    """Response schema for admin action audit log entry."""

    id: int
    admin_user_id: str
    action_type: str
    resource_type: str
    resource_id: Optional[str] = None
    environment: Optional[str] = None
    before_value: Optional[str] = None
    after_value: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
