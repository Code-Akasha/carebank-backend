from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String

from app.core.database import Base


class RecurringRule(Base):
    __tablename__ = "recurring_rules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    plan_id = Column(Integer, nullable=True, index=True)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False, default="custom")
    amount = Column(Float, nullable=False)
    day_of_month = Column(Integer, nullable=False, default=1)
    start_date = Column(Date, nullable=False, default=date.today)
    next_run_date = Column(Date, nullable=False, index=True)
    autopay_enabled = Column(Boolean, nullable=False, default=False)
    requires_approval = Column(Boolean, nullable=False, default=True)
    trusted_recurring = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    reminder_days_before = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
