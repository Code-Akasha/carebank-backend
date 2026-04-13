"""Recurring payment management API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.payments import (
    RecurringPaymentCreate,
    RecurringPaymentResponse,
    RecurringPaymentUpdate,
)
from app.services.recurring_payment_service import (
    create_recurring_payment_rule,
    get_recurring_payment_rule,
    list_recurring_payment_rules,
    update_recurring_payment_rule,
    pause_recurring_payment_rule,
    resume_recurring_payment_rule,
    delete_recurring_payment_rule,
    get_upcoming_payments,
)

router = APIRouter(prefix="/api/recurring-payments", tags=["recurring-payments"])


@router.post("/", response_model=RecurringPaymentResponse)
async def create_recurring_payment(
    payload: RecurringPaymentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new recurring payment rule.

    Validates:
    - Beneficiary exists and belongs to user
    - Amount is within recurring limit (₹100k per cycle)
    - User hasn't exceeded max active rules (10)
    - Frequency and day config are valid

    Returns:
    - Full recurring payment rule with calculated next_run_date
    """
    rule = create_recurring_payment_rule(db, current_user.user_id, payload)
    return RecurringPaymentResponse.model_validate(rule)


@router.get("/", response_model=list[RecurringPaymentResponse])
async def list_recurring_payments(
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all recurring payment rules for current user.

    Optional filter by status: 'active', 'paused', 'expired'.
    Returns rules ordered by next run date.
    """
    rules = list_recurring_payment_rules(db, current_user.user_id, status)
    return [RecurringPaymentResponse.model_validate(rule) for rule in rules]


@router.get("/upcoming", response_model=list[dict])
async def get_upcoming(
    days_ahead: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get upcoming recurring payments for next N days.

    Returns list of payments scheduled for the next period,
    sorted by execution date.
    """
    return get_upcoming_payments(db, current_user.user_id, days_ahead)


@router.get("/{rule_id}", response_model=RecurringPaymentResponse)
async def get_recurring_payment(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get specific recurring payment rule details."""
    rule = get_recurring_payment_rule(db, current_user.user_id, rule_id)
    return RecurringPaymentResponse.model_validate(rule)


@router.put("/{rule_id}", response_model=RecurringPaymentResponse)
async def update_recurring_payment(
    rule_id: int,
    payload: RecurringPaymentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update recurring payment rule.

    Can update:
    - amount: Payment per cycle (max ₹100k)
    - frequency: "daily", "weekly", "monthly", "quarterly"
    - day_of_month: 1-31 for monthly/quarterly
    - day_of_week: "monday"-"sunday" for weekly
    - end_date: When to stop recurring
    - requires_approval: Whether to require MPIN for each execution
    """
    rule = update_recurring_payment_rule(db, current_user.user_id, rule_id, payload)
    return RecurringPaymentResponse.model_validate(rule)


@router.post("/{rule_id}/pause", response_model=RecurringPaymentResponse)
async def pause_recurring_payment(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pause a recurring payment rule.

    Paused rules can be resumed later. The rule won't execute until resumed.
    Useful for temporary suspension without permanent deletion.
    """
    rule = pause_recurring_payment_rule(db, current_user.user_id, rule_id)
    return RecurringPaymentResponse.model_validate(rule)


@router.post("/{rule_id}/resume", response_model=RecurringPaymentResponse)
async def resume_recurring_payment(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resume a paused recurring payment rule.

    Recalculates next_run_date from current date.
    """
    rule = resume_recurring_payment_rule(db, current_user.user_id, rule_id)
    return RecurringPaymentResponse.model_validate(rule)


@router.delete("/{rule_id}")
async def delete_recurring_payment(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete (cancel) a recurring payment rule.

    Note: Soft deleted via status="expired". Historical payment records remain.
    """
    delete_recurring_payment_rule(db, current_user.user_id, rule_id)
    return {"message": "Recurring payment rule deleted successfully"}
