"""Service plans created by business accounts for pricing their services."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String

from app.core.database import Base


class ServicePlan(Base):
    """A pricing plan offered by a business account."""

    __tablename__ = "service_plans"

    id = Column(Integer, primary_key=True, index=True)
    business_user_id = Column(
        String,
        ForeignKey("users.user_id"),
        index=True,
        nullable=False,
    )

    plan_name = Column(String, nullable=False)
    unit_label = Column(String, nullable=False)  # "cylinder", "unit", "GB", "month"
    unit_price = Column(Float, nullable=False)
    currency = Column(String, default="INR", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
