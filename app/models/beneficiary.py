"""Saved beneficiaries for payments (contacts)."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from datetime import datetime, timezone

from app.core.database import Base


class Beneficiary(Base):
    """Saved payment beneficiaries (contacts) per user."""

    __tablename__ = "beneficiaries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"), index=True, nullable=False)

    # Beneficiary Identification
    nickname = Column(
        String, nullable=True
    )  # User-friendly name (e.g., "Mom", "Yoga fees")
    identifier_type = Column(
        String, nullable=False
    )  # "phone", "upi_id", "account_number"
    identifier_value = Column(
        String, nullable=False
    )  # "+919876543210", "user@upi", "1234567890"

    # Verification Status
    is_verified = Column(
        Boolean, default=False
    )  # Has been verified by OTP/micro-deposit
    is_trusted = Column(Boolean, default=False)  # User marked as trusted (auto-execute)
    verification_method = Column(
        String, nullable=True
    )  # "otp", "micro_deposit", "payment"
    verified_at = Column(DateTime, nullable=True)

    # Metadata
    category = Column(String, nullable=True)  # "family", "bills", "services", etc.
    last_used_at = Column(DateTime, nullable=True)  # Last payment to this beneficiary
    payment_count = Column(Integer, default=0)  # Number of times paid

    # Linked CareBank Account (if beneficiary is also a CareBank user)
    linked_carebank_user_id = Column(String, ForeignKey("users.user_id"), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
