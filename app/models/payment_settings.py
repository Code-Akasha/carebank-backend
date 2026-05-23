"""Payment settings and security configuration per user."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String

from app.core.database import Base


class PaymentSettings(Base):
    """User-specific payment security and limit settings."""

    __tablename__ = "payment_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        String,
        ForeignKey("users.user_id"),
        unique=True,
        index=True,
        nullable=False,
    )

    # MPIN & Security
    mpin_hash = Column(String, nullable=True)  # Bcrypt hashed MPIN

    # Approval Thresholds
    mpin_threshold = Column(Float, default=50000.0)  # Amount above which MPIN required
    auto_approve_trusted = Column(
        Boolean,
        default=True,
    )  # Auto-approve trusted beneficiaries within threshold

    # Daily Limits
    daily_limit = Column(
        Float,
        default=1000000.0,
    )  # Max total per day across all payments
    daily_limit_used_date = Column(DateTime)  # When daily limit was last reset
    daily_limit_used = Column(Float, default=0.0)  # Amount used today

    # Recurring Payment Limits
    recurring_payment_max = Column(
        Float,
        default=100000.0,
    )  # Max amount per recurring cycle
    max_active_recurring_rules = Column(
        Integer,
        default=10,
    )  # Max number of active recurring rules

    # Transaction Limits (by verification status)
    # Verified: ₹200k UPI, ₹500k Account Transfer
    # Unverified: ₹50k UPI, ₹100k Account Transfer
    # These are hardcoded in policy, but stored here for reference

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
