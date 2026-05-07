"""Runtime configuration for the banking/mock provider connector."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, Index

from app.core.database import Base


class BankingConnectorConfig(Base):
    __tablename__ = "banking_connector_configs"

    id = Column(Integer, primary_key=True, index=True)
    environment = Column(String, nullable=False, index=True)
    provider_type = Column(String, default="mockbank", nullable=False)
    base_url = Column(String, nullable=False)
    secret_encrypted = Column(Text, nullable=True)
    request_timeout_sec = Column(Integer, default=10, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_by = Column(String, nullable=False, index=True)
    updated_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_connectivity_check = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_banking_connector_env_active", "environment", "is_active"),
    )