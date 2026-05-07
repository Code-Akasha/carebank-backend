"""add banking connector configs

Revision ID: 8b7d4f2c1a90
Revises: f4e2c1d5a9b8
Create Date: 2026-05-07 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8b7d4f2c1a90"
down_revision: Union[str, Sequence[str], None] = "f4e2c1d5a9b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "banking_connector_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),
        sa.Column("provider_type", sa.String(), nullable=False),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column("request_timeout_sec", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_connectivity_check", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_banking_connector_env_active",
        "banking_connector_configs",
        ["environment", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_banking_connector_env_active", table_name="banking_connector_configs")
    op.drop_table("banking_connector_configs")