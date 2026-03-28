from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from app.core.database import Base


class UserMPIN(Base):
    __tablename__ = "user_mpins"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_mpin_user_id"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    mpin_hash = Column(String, nullable=False)
    failed_attempts = Column(Integer, default=0, nullable=False)
    lockout_until = Column(DateTime, nullable=True)
    last_verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
