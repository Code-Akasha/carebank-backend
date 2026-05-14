"""Payment execution history (audit trail)."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from datetime import datetime, timezone
from sqlalchemy.orm import synonym

from app.core.database import Base


class PaymentHistory(Base):
    """Complete audit trail of all payment executions (one-time and recurring)."""

    __tablename__ = "payment_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"), index=True, nullable=False)
    beneficiary_id = Column(Integer, ForeignKey("beneficiaries.id"), nullable=False)

    # Payment Details
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=True, default="")
    payment_type = Column(String, nullable=True, default="once")  # "once", "recurring"
    payment_method = Column(String, nullable=False)  # "upi", "account_transfer"

    # Recurring Link
    recurring_rule_id = Column(
        Integer, ForeignKey("recurring_payment_rules.id"), nullable=True
    )

    # Execution Details
    status = Column(
        String, nullable=False, index=True
    )  # "pending", "success", "failed"
    execution_date = Column(DateTime, nullable=True, index=True)
    mockbank_transaction_id = Column(
        String, nullable=True
    )  # Transaction ID from MockBank
    transaction_id = synonym("mockbank_transaction_id")

    # Error Tracking
    error_reason = Column(String, nullable=True)  # Failure reason if status="failed"

    # Idempotency
    idempotency_key = Column(String, unique=True, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
