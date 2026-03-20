"""add bill_snoozes

Revision ID: c7a0c6b1d3e4
Revises: ba1fd9312fe9
Create Date: 2026-03-20 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7a0c6b1d3e4"
down_revision: Union[str, Sequence[str], None] = "ba1fd9312fe9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "bill_snoozes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("snoozed_until", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "source_type",
            "source_id",
            name="uq_bill_snooze_source",
        ),
    )
    op.create_index(op.f("ix_bill_snoozes_id"), "bill_snoozes", ["id"], unique=False)
    op.create_index(
        op.f("ix_bill_snoozes_source_id"),
        "bill_snoozes",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bill_snoozes_source_type"),
        "bill_snoozes",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bill_snoozes_snoozed_until"),
        "bill_snoozes",
        ["snoozed_until"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bill_snoozes_user_id"),
        "bill_snoozes",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_bill_snoozes_user_id"), table_name="bill_snoozes")
    op.drop_index(op.f("ix_bill_snoozes_snoozed_until"), table_name="bill_snoozes")
    op.drop_index(op.f("ix_bill_snoozes_source_type"), table_name="bill_snoozes")
    op.drop_index(op.f("ix_bill_snoozes_source_id"), table_name="bill_snoozes")
    op.drop_index(op.f("ix_bill_snoozes_id"), table_name="bill_snoozes")
    op.drop_table("bill_snoozes")
