"""
Admin Action Log Model.

Audit trail for all admin actions: LLM config updates, secret rotations,
prompt publishes, rollbacks, etc.
"""

from sqlalchemy import Column, DateTime, Integer, String, Text, Index
from datetime import datetime, timezone
from app.core.database import Base


class AdminActionLog(Base):
    __tablename__ = "admin_action_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_user_id = Column(String, nullable=False, index=True)  # user_id of admin performing action
    action_type = Column(String, nullable=False, index=True)  # e.g., "llm_config_update", "prompt_publish", "prompt_rollback"
    resource_type = Column(String, nullable=False)  # e.g., "tunnel", "prompt", "model"
    resource_id = Column(String, nullable=True)  # e.g., "coordinator" for agent name, or tunnel id
    environment = Column(String, nullable=True, index=True)  # "dev" | "stage" | "prod"
    
    # Before/after values for audit trail (JSON-serialized or masked)
    before_value = Column(Text, nullable=True)  # Previous value (masked for secrets)
    after_value = Column(Text, nullable=True)  # New value (masked for secrets)
    
    # Status tracking
    status = Column(String, default="success", nullable=False)  # "success" | "failed"
    error_message = Column(Text, nullable=True)  # If status is "failed", why?
    
    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Index for fast audit trail queries by admin user and time
    __table_args__ = (
        Index("ix_admin_action_log_user_time", "admin_user_id", "created_at"),
    )

    def __repr__(self):
        return f"<AdminActionLog id={self.id} user={self.admin_user_id} action={self.action_type}>"
