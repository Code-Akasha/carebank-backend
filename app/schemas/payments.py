"""Pydantic schemas for payment operations."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================================
# BENEFICIARY SCHEMAS
# ============================================================================


class BeneficiaryCreate(BaseModel):
    """Create a new beneficiary."""

    nickname: str = Field(
        ..., min_length=1, max_length=50, description="User-friendly name"
    )
    identifier_type: str = Field(
        ...,
        pattern="^(phone|upi_id|account_number)$",
        description="Type of identifier",
    )
    identifier_value: str = Field(
        ...,
        min_length=5,
        max_length=100,
        description="Phone, UPI ID, or account number",
    )
    category: Optional[str] = Field(
        None, max_length=50, description="Category (family, bills, services)"
    )


class BeneficiaryUpdate(BaseModel):
    """Update an existing beneficiary."""

    nickname: Optional[str] = Field(None, min_length=1, max_length=50)
    category: Optional[str] = Field(None, max_length=50)
    is_trusted: Optional[bool] = Field(
        None, description="Mark as trusted for auto-execute"
    )


class BeneficiaryResponse(BaseModel):
    """Beneficiary response model."""

    id: int
    nickname: Optional[str]
    identifier_type: str
    identifier_value: str
    category: Optional[str]
    is_verified: bool
    is_trusted: bool
    last_used_at: Optional[datetime]
    payment_count: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# PAYMENT OPERATION SCHEMAS
# ============================================================================


class ExecutePaymentPayload(BaseModel):
    """Payload for executing a one-time payment."""

    beneficiary_id: int = Field(..., description="Beneficiary ID")
    amount: float = Field(..., gt=0, le=500000, description="Payment amount in rupees")
    description: Optional[str] = Field(
        None, max_length=200, description="Payment description"
    )
    payment_method: str = Field(
        default="upi",
        pattern="^(upi|account_transfer)$",
        description="Payment method",
    )
    mpin: Optional[str] = Field(None, description="User MPIN for verification")


class PaymentHistoryResponse(BaseModel):
    """Payment history entry response."""

    id: int
    beneficiary_id: int
    amount: float
    description: str
    payment_type: str  # "once", "recurring"
    payment_method: str
    status: str
    execution_date: datetime
    mockbank_transaction_id: Optional[str]
    error_reason: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# RECURRING PAYMENT SCHEMAS
# ============================================================================


class RecurringPaymentCreate(BaseModel):
    """Create a new recurring payment rule."""

    beneficiary_id: int = Field(..., description="Beneficiary ID")
    amount: float = Field(
        ..., gt=0, le=100000, description="Amount per cycle (max ₹100k)"
    )
    description: str = Field(
        ..., min_length=1, max_length=100, description="Bill/service name"
    )
    frequency: str = Field(
        ...,
        pattern="^(daily|weekly|monthly|quarterly)$",
        description="Frequency",
    )
    day_config: Optional[dict] = Field(
        None,
        description='{"day_of_week": "monday"} for weekly or {"day_of_month": 5} for monthly',
    )
    start_date: Optional[date] = Field(
        None, description="Start date (defaults to today)"
    )
    end_date: Optional[date] = Field(
        None, description="End date (optional; None = indefinite)"
    )
    requires_approval: bool = Field(
        default=True, description="Require approval for each payment"
    )


class RecurringPaymentUpdate(BaseModel):
    """Update an existing recurring payment rule."""

    amount: Optional[float] = Field(None, gt=0, le=100000)
    description: Optional[str] = Field(None, min_length=1, max_length=100)
    frequency: Optional[str] = Field(None, pattern="^(daily|weekly|monthly|quarterly)$")
    day_config: Optional[dict] = Field(None)
    end_date: Optional[date] = Field(None)
    requires_approval: Optional[bool] = Field(None)


class RecurringPaymentResponse(BaseModel):
    """Recurring payment rule response."""

    id: int
    beneficiary_id: int
    amount: float
    description: str
    frequency: str
    day_of_month: Optional[int]
    day_of_week: Optional[str]
    start_date: date
    end_date: Optional[date]
    next_run_date: date
    status: str  # "active", "paused", "expired"
    requires_approval: bool
    total_executions: int
    last_executed_at: Optional[datetime]
    last_execution_status: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class RecurringPaymentUpcomingResponse(BaseModel):
    """Upcoming payments for a recurring rule."""

    recurring_rule_id: int
    description: str
    beneficiary_nickname: Optional[str]
    amount: float
    upcoming_payments: list[dict] = Field(
        description="List of next 5 scheduled payments with dates"
    )


# ============================================================================
# PAYMENT SETTINGS SCHEMAS
# ============================================================================


class PaymentSettingsResponse(BaseModel):
    """User's payment settings."""

    id: int
    mpin_threshold: float
    auto_approve_trusted: bool
    daily_limit: float
    daily_limit_used: float
    recurring_payment_max: float
    max_active_recurring_rules: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaymentSettingsUpdate(BaseModel):
    """Update payment settings."""

    mpin_threshold: Optional[float] = Field(None, gt=0, le=1000000)
    auto_approve_trusted: Optional[bool] = Field(None)
    daily_limit: Optional[float] = Field(None, gt=0, le=10000000)
    recurring_payment_max: Optional[float] = Field(None, gt=0, le=1000000)


class SetMPINRequest(BaseModel):
    """Set or update user MPIN."""

    mpin: str = Field(..., min_length=4, max_length=6, description="4-6 digit MPIN")


# ============================================================================
# RESPONSE ENVELOPES
# ============================================================================


class PaymentExecutionResult(BaseModel):
    """Result of payment execution."""

    status: str  # "success", "pending", "failed"
    message: str
    execution_id: Optional[int] = None
    transaction_id: Optional[str] = None
    error_reason: Optional[str] = None
