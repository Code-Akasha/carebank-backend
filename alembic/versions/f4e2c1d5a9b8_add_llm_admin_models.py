"""Add LLM admin configuration tables

Revision ID: f4e2c1d5a9b8
Revises: 0f191ad76d6f
Create Date: 2026-05-07 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4e2c1d5a9b8"
down_revision: str | Sequence[str] | None = "0f191ad76d6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create LLM tunnel configuration, agent prompt configuration, and admin action log tables."""
    # Create LLM tunnel configuration table
    op.create_table(
        "llm_tunnel_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),
        sa.Column("provider_type", sa.String(), nullable=False),
        sa.Column("tunnel_url", sa.String(), nullable=False),
        sa.Column("tunnel_auth_token_encrypted", sa.String(), nullable=True),
        sa.Column("ollama_model_default", sa.String(), nullable=False),
        sa.Column("request_timeout_sec", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_connectivity_check", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_llm_tunnel_config_environment_active",
        "llm_tunnel_configs",
        ["environment", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_llm_tunnel_configs_environment",
        "llm_tunnel_configs",
        ["environment"],
        unique=False,
    )
    op.create_index(
        "ix_llm_tunnel_configs_is_active",
        "llm_tunnel_configs",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        "ix_llm_tunnel_configs_created_by",
        "llm_tunnel_configs",
        ["created_by"],
        unique=False,
    )

    # Create agent prompt configuration table
    op.create_table(
        "agent_prompt_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_prompt_config_agent_env_active",
        "agent_prompt_configs",
        ["agent_name", "environment", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_agent_prompt_configs_agent_name",
        "agent_prompt_configs",
        ["agent_name"],
        unique=False,
    )
    op.create_index(
        "ix_agent_prompt_configs_environment",
        "agent_prompt_configs",
        ["environment"],
        unique=False,
    )
    op.create_index(
        "ix_agent_prompt_configs_is_active",
        "agent_prompt_configs",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        "ix_agent_prompt_configs_created_by",
        "agent_prompt_configs",
        ["created_by"],
        unique=False,
    )

    # Create admin action log table
    op.create_table(
        "admin_action_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("admin_user_id", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=True),
        sa.Column("environment", sa.String(), nullable=True),
        sa.Column("before_value", sa.Text(), nullable=True),
        sa.Column("after_value", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_action_log_user_time",
        "admin_action_logs",
        ["admin_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_action_logs_admin_user_id",
        "admin_action_logs",
        ["admin_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_admin_action_logs_action_type",
        "admin_action_logs",
        ["action_type"],
        unique=False,
    )
    op.create_index(
        "ix_admin_action_logs_created_at",
        "admin_action_logs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_action_logs_environment",
        "admin_action_logs",
        ["environment"],
        unique=False,
    )


def downgrade() -> None:
    """Drop LLM admin configuration tables."""
    op.drop_table("admin_action_logs")
    op.drop_table("agent_prompt_configs")
    op.drop_table("llm_tunnel_configs")
