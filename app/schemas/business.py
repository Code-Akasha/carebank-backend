"""Pydantic schemas for business onboarding, service plans, and bills."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

# ============================================================================
# BUSINESS ONBOARDING
# ============================================================================


class BusinessProfileResponse(BaseModel):
    """Business profile details."""

    id: int
    user_id: str
    business_name: str
    category: str
    description: str | None = None
    gst_number: str | None = None
    is_verified_business: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# SERVICE PLANS
# ============================================================================


class ServicePlanCreate(BaseModel):
    """Create a service plan (business only)."""

    plan_name: str = Field(..., min_length=1, max_length=200)
    unit_label: str = Field(..., min_length=1, max_length=50)
    unit_price: float = Field(..., gt=0, le=10000000)
    currency: str = Field(default="INR", max_length=10)


class ServicePlanUpdate(BaseModel):
    """Update an existing service plan."""

    plan_name: str | None = Field(None, min_length=1, max_length=200)
    unit_label: str | None = Field(None, min_length=1, max_length=50)
    unit_price: float | None = Field(None, gt=0, le=10000000)
    is_active: bool | None = None


class ServicePlanResponse(BaseModel):
    """Service plan response."""

    id: int
    business_user_id: str
    plan_name: str
    unit_label: str
    unit_price: float
    currency: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# BILLS
# ============================================================================


class BillCreate(BaseModel):
    """Business issues a bill to a user."""

    target_user_id: str = Field(..., min_length=1)
    service_plan_id: int | None = Field(
        None, description="Link to a service plan for auto-pricing",
    )
    plan_name: str | None = Field(
        None, max_length=200, description="Manual plan name if no plan_id",
    )
    quantity: float = Field(default=1.0, gt=0, le=100000)
    amount: float | None = Field(
        None,
        gt=0,
        le=50000000,
        description="Override amount (auto-calculated from plan if omitted)",
    )
    description: str | None = Field(None, max_length=500)
    due_date: date | None = None


class BillPayRequest(BaseModel):
    """User pays a bill."""

    mpin: str = Field(..., min_length=4, max_length=6)
    payment_method: str = Field(default="upi", pattern="^(upi|account_transfer)$")


class BillCancelRequest(BaseModel):
    """Business cancels a bill."""

    reason: str | None = Field(None, max_length=200)


class BillResponse(BaseModel):
    """Bill response model."""

    id: int
    business_user_id: str
    business_name: str | None = None
    target_user_id: str
    service_plan_id: int | None = None
    plan_name: str
    quantity: float
    amount: float
    currency: str
    description: str | None = None
    status: str
    due_date: date | None = None
    paid_at: datetime | None = None
    payment_transaction_id: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True
