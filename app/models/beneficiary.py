"""Saved beneficiaries for payments (contacts)."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class Beneficiary(Base):
    """Saved payment beneficiaries (contacts) per user."""

    __tablename__ = "beneficiaries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"), index=True, nullable=False)

    # Beneficiary Identification
    nickname = Column(
        String,
        nullable=True,
    )  # User-friendly name (e.g., "Mom", "Yoga fees")
    identifier_type = Column(
        String,
        nullable=False,
    )  # "phone", "upi_id", "account_number"
    identifier_value = Column(
        String,
        nullable=False,
    )  # "+919876543210", "user@upi", "1234567890"
    phone_number = Column(String, nullable=True)
    upi_handle = Column(String, nullable=True)
    ifsc = Column(String, nullable=True)

    # Verification Status
    is_verified = Column(
        Boolean,
        default=False,
    )  # Has been verified by OTP/micro-deposit
    is_trusted = Column(Boolean, default=False)  # User marked as trusted (auto-execute)
    verification_method = Column(
        String,
        nullable=True,
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

    @property
    def name(self) -> str | None:
        return self.nickname

    @name.setter
    def name(self, value: str | None) -> None:
        self.nickname = value

    @property
    def phone(self) -> str | None:
        if self.phone_number:
            return self.phone_number
        return self.identifier_value if self.identifier_type == "phone" else None

    @phone.setter
    def phone(self, value: str | None) -> None:
        if value:
            self.identifier_type = "phone"
            self.identifier_value = value

    @property
    def upi(self) -> str | None:
        if self.upi_handle:
            return self.upi_handle
        return (
            self.identifier_value if self.identifier_type in {"upi", "upi_id"} else None
        )

    @upi.setter
    def upi(self, value: str | None) -> None:
        if value:
            self.identifier_type = "upi_id"
            self.identifier_value = value

    @property
    def account_number(self) -> str | None:
        return (
            self.identifier_value if self.identifier_type == "account_number" else None
        )

    @account_number.setter
    def account_number(self, value: str | None) -> None:
        if value:
            self.identifier_type = "account_number"
            self.identifier_value = value
