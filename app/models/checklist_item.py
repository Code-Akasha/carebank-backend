from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, Float, Integer, String, Text

from app.core.database import Base


class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    recurring_rule_id = Column(Integer, index=True, nullable=True)
    title = Column(String, nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="pending")
    notes = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
