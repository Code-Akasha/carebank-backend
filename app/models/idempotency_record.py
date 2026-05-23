from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Integer, String, UniqueConstraint

from app.core.database import Base


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "scope", "idempotency_key", name="uq_idempotency_scope_key",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    scope = Column(String, index=True, nullable=False)
    idempotency_key = Column(String, index=True, nullable=False)
    request_hash = Column(String, nullable=False)
    status = Column(String, index=True, nullable=False, default="reserved")
    response_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
