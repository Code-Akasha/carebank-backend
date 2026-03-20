from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from app.core.database import Base


class BillSnooze(Base):
    __tablename__ = "bill_snoozes"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source_type",
            "source_id",
            name="uq_bill_snooze_source",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    source_type = Column(String, index=True, nullable=False)
    source_id = Column(Integer, index=True, nullable=False)
    snoozed_until = Column(DateTime, index=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
