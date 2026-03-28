"""add user_mpins

Revision ID: e13a9df4d8b2
Revises: c7a0c6b1d3e4
Create Date: 2026-03-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e13a9df4d8b2"
down_revision: Union[str, Sequence[str], None] = "c7a0c6b1d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_mpins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("mpin_hash", sa.String(), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("lockout_until", sa.DateTime(), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_mpin_user_id"),
    )
    op.create_index(op.f("ix_user_mpins_id"), "user_mpins", ["id"], unique=False)
    op.create_index(
        op.f("ix_user_mpins_user_id"), "user_mpins", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_user_mpins_user_id"), table_name="user_mpins")
    op.drop_index(op.f("ix_user_mpins_id"), table_name="user_mpins")
    op.drop_table("user_mpins")
