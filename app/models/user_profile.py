from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text

from app.core.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True, nullable=False)
    monthly_salary = Column(Float, nullable=False, default=0.0)
    currency = Column(String, nullable=False, default="INR")
    min_safe_balance = Column(Float, nullable=False, default=5000.0)
    savings_goal_pct = Column(Float, nullable=False, default=0.2)
    risk_tolerance = Column(String, nullable=False, default="moderate")
    persistent_expenses_json = Column(JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
