"""Bills issued by businesses to users for services consumed."""

from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Text

from app.core.database import Base


class Bill(Base):
    """A bill issued by a business to a user."""

    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)
    business_user_id = Column(
        String,
        ForeignKey("users.user_id"),
        index=True,
        nullable=False,
    )
    target_user_id = Column(
        String,
        ForeignKey("users.user_id"),
        index=True,
        nullable=False,
    )
    service_plan_id = Column(Integer, ForeignKey("service_plans.id"), nullable=True)

    # Bill details
    plan_name = Column(String, nullable=False)  # Denormalized for display
    quantity = Column(Float, nullable=False, default=1.0)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="INR", nullable=False)
    description = Column(Text, nullable=True)

    # Status tracking
    status = Column(
        String,
        default="pending",
        nullable=False,
    )  # pending, paid, cancelled, overdue
    due_date = Column(Date, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    payment_transaction_id = Column(String, nullable=True)  # Links to proxy transaction

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
