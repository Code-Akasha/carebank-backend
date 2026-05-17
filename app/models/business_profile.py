"""Business profile for users with account_type='business'."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class BusinessProfile(Base):
    """Extended profile for business/service-provider accounts."""

    __tablename__ = "business_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        String, ForeignKey("users.user_id"), unique=True, index=True, nullable=False
    )

    business_name = Column(String, nullable=False)
    category = Column(
        String, nullable=False
    )  # gas, electricity, telecom, housing, etc.
    description = Column(Text, nullable=True)
    gst_number = Column(String, nullable=True)
    is_verified_business = Column(Boolean, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
