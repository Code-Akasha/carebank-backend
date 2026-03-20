from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text, UniqueConstraint

from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notification_dedupe"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    dedupe_key = Column(String, nullable=False)
    kind = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    payload_json = Column(JSON, nullable=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
