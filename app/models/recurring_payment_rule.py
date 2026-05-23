"""Recurring payment rules configured by users."""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)

from app.core.database import Base


class RecurringPaymentRule(Base):
    """User-configured recurring payments (bills, subscriptions, etc.)."""

    __tablename__ = "recurring_payment_rules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"), index=True, nullable=False)
    beneficiary_id = Column(Integer, ForeignKey("beneficiaries.id"), nullable=False)

    # Payment Details
    amount = Column(Float, nullable=False)  # Amount per cycle
    description = Column(
        String, nullable=True, default="",
    )  # "Yoga fees", "Dish TV bill", etc.
    day_config = Column(JSON, nullable=True)

    # Frequency Configuration
    frequency = Column(
        String, nullable=False,
    )  # "daily", "weekly", "monthly", "quarterly"
    day_of_month = Column(Integer, nullable=True)  # 1-31 for monthly frequency
    day_of_week = Column(String, nullable=True)  # "monday", "tuesday", etc. for weekly

    # Timing
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)  # None = indefinite
    next_run_date = Column(
        Date,
        nullable=True,
        index=True,
        default=lambda: datetime.now(timezone.utc).date(),
    )  # Next scheduled execution

    # Execution Control
    status = Column(
        String, default="active", index=True,
    )  # "active", "paused", "expired"
    requires_approval = Column(Boolean, default=True)  # User must approve each payment

    # Execution History
    total_executions = Column(Integer, default=0)
    last_executed_at = Column(DateTime, nullable=True)
    last_execution_status = Column(String, nullable=True)  # "success", "failed"
    last_failure_reason = Column(String, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
