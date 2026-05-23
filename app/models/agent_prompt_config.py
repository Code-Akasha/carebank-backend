"""Agent Prompt Configuration Model.

Stores versioned system prompts for agents, environment-scoped (dev/stage/prod).
Enables prompt customization with version history and rollback capability.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    text,
)

from app.core.database import Base


class AgentPromptConfig(Base):
    __tablename__ = "agent_prompt_configs"

    id = Column(Integer, primary_key=True, index=True)
    agent_name = Column(
        String,
        nullable=False,
        index=True,
    )  # e.g., "coordinator", "payment_agent"
    environment = Column(String, nullable=False, index=True)  # "dev" | "stage" | "prod"
    system_prompt = Column(Text, nullable=False)  # Full prompt template
    version = Column(
        Integer,
        default=1,
        nullable=False,
    )  # Auto-increment version per agent/env
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )  # Only one per (agent, env) can be active

    # Audit fields
    created_by = Column(String, nullable=False, index=True)  # user_id who created
    updated_by = Column(String, nullable=False)  # user_id who last updated
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Admin notes on this version (e.g., reason for update)
    notes = Column(Text, nullable=True)

    # Constraints
    __table_args__ = (
        # Unique constraint: only one active prompt per agent/environment
        # Use Index with unique=True for partial unique constraints (postgresql_where)
        Index(
            "uq_active_prompt_per_agent_env",
            "agent_name",
            "environment",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
        # Index for fast lookups (redundant with the unique index above, but good for clarity)
        Index(
            "ix_agent_prompt_config_agent_env_active",
            "agent_name",
            "environment",
            "is_active",
        ),
    )

    def __repr__(self):
        return f"<AgentPromptConfig id={self.id} agent={self.agent_name} env={self.environment} v{self.version}>"
