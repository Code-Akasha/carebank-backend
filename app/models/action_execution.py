from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text

from app.core.database import Base


class ActionExecution(Base):
    __tablename__ = "action_executions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    approval_request_id = Column(Integer, nullable=True, index=True)
    action_type = Column(String, index=True, nullable=False)
    status = Column(String, index=True, nullable=False, default="queued")
    idempotency_key = Column(String, index=True, nullable=True)
    request_hash = Column(String, index=True, nullable=True)
    request_payload_json = Column(JSON, nullable=False, default=dict)
    result_payload_json = Column(JSON, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=2)
    last_error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
