"""LLM Tunnel Configuration Model.

Stores runtime configuration for secure tunnel to local Ollama instance,
environment-scoped (dev/stage/prod).
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text

from app.core.database import Base


class LLMTunnelConfig(Base):
    __tablename__ = "llm_tunnel_configs"

    id = Column(Integer, primary_key=True, index=True)
    environment = Column(String, nullable=False, index=True)  # "dev" | "stage" | "prod"
    provider_type = Column(
        String, default="ngrok", nullable=False,
    )  # For future multi-provider support
    tunnel_url = Column(String, nullable=False)  # e.g., "https://abc123.ngrok.io"
    tunnel_auth_token_encrypted = Column(
        String, nullable=True,
    )  # Encrypted ngrok auth token or None
    ollama_model_default = Column(
        String, default="qwen3:8b", nullable=False,
    )  # Default model to use
    request_timeout_sec = Column(
        Integer, default=30, nullable=False,
    )  # HTTP request timeout
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Connectivity monitoring
    last_connectivity_check = Column(DateTime, nullable=True)
    last_error = Column(
        Text, nullable=True,
    )  # Last error message if connectivity failed

    # Audit fields
    created_by = Column(String, nullable=False, index=True)  # user_id who created
    updated_by = Column(String, nullable=False)  # user_id who last updated
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Index for fast environment lookups
    __table_args__ = (
        Index("ix_llm_tunnel_config_environment_active", "environment", "is_active"),
    )

    def __repr__(self):
        return f"<LLMTunnelConfig id={self.id} env={self.environment} active={self.is_active}>"
