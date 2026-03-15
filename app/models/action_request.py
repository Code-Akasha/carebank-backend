from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text

from app.core.database import Base


class ActionRequest(Base):
    __tablename__ = "action_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    action_type = Column(String, index=True, nullable=False)
    action_payload_json = Column(JSON, nullable=False, default=dict)
    policy_snapshot_json = Column(JSON, nullable=True)
    status = Column(String, index=True, nullable=False, default="pending")
    idempotency_key = Column(String, index=True, nullable=True)
    request_hash = Column(String, index=True, nullable=True)
    expires_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc) + timedelta(hours=24),
    )
    decided_at = Column(DateTime, nullable=True)
    decision_reason = Column(Text, nullable=True)
    linked_execution_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
