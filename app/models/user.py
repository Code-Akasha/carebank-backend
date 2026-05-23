from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import synonym

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True, nullable=False)
    telegram_user_id = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True, default="")
    full_name = Column(String, nullable=True, default="")
    role = Column(String, default="user", nullable=False)
    account_type = Column(
        String,
        default="personal",
        nullable=False,
    )  # "personal" or "business"
    is_active = Column(Boolean, default=True, nullable=False)

    # Payment methods (for generic payment system)
    phone_number = Column(String, nullable=True)  # For UPI payments
    phone_verified = Column(Boolean, default=False)
    phone = synonym("phone_number")

    account_number = Column(String, nullable=True)  # For account transfers
    account_ifsc = Column(String, nullable=True)
    account_verified = Column(Boolean, default=False)

    name = synonym("full_name")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
