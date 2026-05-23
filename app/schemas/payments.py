"""Pydantic schemas for payment operations."""

from datetime import date, datetime

from pydantic import BaseModel, Field

# ============================================================================
# BENEFICIARY SCHEMAS
# ============================================================================


class BeneficiaryCreate(BaseModel):
    """Create a new beneficiary."""

    nickname: str = Field(
        ..., min_length=1, max_length=50, description="User-friendly name",
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
    category: str | None = Field(
        None, max_length=50, description="Category (family, bills, services)",
    )


class BeneficiaryUpdate(BaseModel):
    """Update an existing beneficiary."""

    nickname: str | None = Field(None, min_length=1, max_length=50)
    category: str | None = Field(None, max_length=50)
    is_trusted: bool | None = Field(
        None, description="Mark as trusted for auto-execute",
    )


class BeneficiaryResponse(BaseModel):
    """Beneficiary response model."""

    id: int
    nickname: str | None
    identifier_type: str
    identifier_value: str
    category: str | None
    is_verified: bool
    is_trusted: bool
    last_used_at: datetime | None
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
    description: str | None = Field(
        None, max_length=200, description="Payment description",
    )
    payment_method: str = Field(
        default="upi",
        pattern="^(upi|account_transfer)$",
        description="Payment method",
    )
    mpin: str | None = Field(None, description="User MPIN for verification")
    idempotency_key: str | None = Field(None, description="Client idempotency key")


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
    mockbank_transaction_id: str | None
    error_reason: str | None
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
        ..., gt=0, le=100000, description="Amount per cycle (max ₹100k)",
    )
    description: str | None = Field(
        None, min_length=1, max_length=100, description="Bill/service name",
    )
    frequency: str = Field(
        ...,
        pattern="^(daily|weekly|monthly|quarterly)$",
        description="Frequency",
    )
    day_config: dict | None = Field(
        None,
        description='{"day_of_week": "monday"} for weekly or {"day_of_month": 5} for monthly',
    )
    start_date: date | None = Field(
        None, description="Start date (defaults to today)",
    )
    end_date: date | None = Field(
        None, description="End date (optional; None = indefinite)",
    )
    requires_approval: bool = Field(
        default=True, description="Require approval for each payment",
    )


class RecurringPaymentUpdate(BaseModel):
    """Update an existing recurring payment rule."""

    amount: float | None = Field(None, gt=0, le=100000)
    description: str | None = Field(None, min_length=1, max_length=100)
    frequency: str | None = Field(None, pattern="^(daily|weekly|monthly|quarterly)$")
    day_config: dict | None = Field(None)
    end_date: date | None = Field(None)
    requires_approval: bool | None = Field(None)


class RecurringPaymentResponse(BaseModel):
    """Recurring payment rule response."""

    id: int
    beneficiary_id: int
    amount: float
    description: str
    frequency: str
    day_of_month: int | None
    day_of_week: str | None
    start_date: date
    end_date: date | None
    next_run_date: date
    status: str  # "active", "paused", "expired"
    requires_approval: bool
    total_executions: int
    last_executed_at: datetime | None
    last_execution_status: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class RecurringPaymentUpcomingResponse(BaseModel):
    """Upcoming payments for a recurring rule."""

    recurring_rule_id: int
    description: str
    beneficiary_nickname: str | None
    amount: float
    upcoming_payments: list[dict] = Field(
        description="List of next 5 scheduled payments with dates",
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

    mpin_threshold: float | None = Field(None, gt=0, le=1000000)
    auto_approve_trusted: bool | None = Field(None)
    daily_limit: float | None = Field(None, gt=0, le=10000000)
    recurring_payment_max: float | None = Field(None, gt=0, le=1000000)


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
    execution_id: int | None = None
    transaction_id: str | None = None
    error_reason: str | None = None

    def __getitem__(self, key: str):
        return getattr(self, key)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and hasattr(self, key)
