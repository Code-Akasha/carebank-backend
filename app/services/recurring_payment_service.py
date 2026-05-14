"""Recurring payment management service."""

from datetime import datetime, timezone, timedelta, date as date_type
from sqlalchemy.orm import Session
from fastapi import HTTPException

from typing import Any

from app.models.recurring_payment_rule import RecurringPaymentRule
from app.models.beneficiary import Beneficiary
from app.models.payment_settings import PaymentSettings
from app.schemas.payments import RecurringPaymentCreate, RecurringPaymentUpdate


def create_recurring_payment_rule(
    db: Session,
    user_id: str,
    payload: RecurringPaymentCreate,
) -> RecurringPaymentRule:
    """Create a new recurring payment rule.

    Validations:
    - Beneficiary exists and belongs to user
    - Amount is within recurring limit (₹100k)
    - Frequency is valid
    - User hasn't exceeded max active rules (10)
    """
    # Validate beneficiary
    beneficiary = (
        db.query(Beneficiary)
        .filter(
            Beneficiary.id == payload.beneficiary_id,
            Beneficiary.user_id == user_id,
        )
        .first()
    )

    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiary not found")

    # Validate amount
    settings = (
        db.query(PaymentSettings).filter(PaymentSettings.user_id == user_id).first()
    )
    if not settings:
        raise HTTPException(status_code=400, detail="Payment settings not configured")

    if payload.amount > settings.recurring_payment_max:
        raise HTTPException(
            status_code=400,
            detail=f"Recurring amount exceeds limit of ₹{settings.recurring_payment_max}",
        )

    # Check max active rules
    active_rules_count = (
        db.query(RecurringPaymentRule)
        .filter(
            RecurringPaymentRule.user_id == user_id,
            RecurringPaymentRule.status.in_(["active", "paused"]),
        )
        .count()
    )

    if active_rules_count >= settings.max_active_recurring_rules:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {settings.max_active_recurring_rules} active recurring rules reached",
        )

    # Extract day_config
    day_of_month = (
        payload.day_config.get("day_of_month") if payload.day_config else None
    )
    day_of_week = payload.day_config.get("day_of_week") if payload.day_config else None
    description = payload.description or (beneficiary.nickname or beneficiary.identifier_value)

    # Calculate next run date
    start_date_dt = (
        datetime.combine(payload.start_date, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
        if payload.start_date
        else datetime.now(timezone.utc)
    )

    next_run_date = calculate_next_run_date(
        payload.frequency,
        day_of_month,
        day_of_week,
        start_date_dt,
    )

    # Create rule
    rule = RecurringPaymentRule(
        user_id=user_id,
        beneficiary_id=payload.beneficiary_id,
        amount=payload.amount,
        description=description,
        frequency=payload.frequency,
        day_of_month=day_of_month,
        day_of_week=day_of_week,
        day_config=payload.day_config,
        start_date=payload.start_date or datetime.now(timezone.utc).date(),
        end_date=payload.end_date,
        next_run_date=next_run_date,
        status="active",
        requires_approval=payload.requires_approval,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def get_recurring_payment_rule(
    db: Session,
    rule_id: int,
    user_id: str | None = None,
) -> RecurringPaymentRule:
    """Get recurring payment rule by ID."""
    query = (
        db.query(RecurringPaymentRule)
        .filter(RecurringPaymentRule.id == rule_id)
    )
    if user_id is not None:
        query = query.filter(RecurringPaymentRule.user_id == user_id)
    rule = query.first()

    if not rule:
        if user_id is None:
            return None
        raise HTTPException(status_code=404, detail="Recurring payment rule not found")

    if rule.status == "expired":
        return None

    return rule


def list_recurring_payment_rules(
    db: Session,
    user_id: str,
    status: str | None = None,
) -> list[RecurringPaymentRule]:
    """List all recurring payment rules for user.

    Optional filter by status: active, paused, expired.
    """
    query = db.query(RecurringPaymentRule).filter(
        RecurringPaymentRule.user_id == user_id
    )

    if status:
        if status not in ["active", "paused", "expired"]:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        query = query.filter(RecurringPaymentRule.status == status)

    # Order by next_run_date, then by creation date
    query = query.order_by(
        RecurringPaymentRule.next_run_date, RecurringPaymentRule.created_at
    )

    return query.all()


def update_recurring_payment_rule(
    db: Session,
    rule_id: int,
    user_id: str | None = None,
    payload: RecurringPaymentUpdate | None = None,
    update_data: dict[str, Any] | None = None,
) -> RecurringPaymentRule:
    """Update recurring payment rule.

    Can update:
    - amount
    - frequency & day config
    - end_date
    - requires_approval flag
    """
    rule = get_recurring_payment_rule(db, rule_id, user_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Recurring payment rule not found")

    effective_user_id = user_id or rule.user_id

    if payload is None:
        payload = RecurringPaymentUpdate(**(update_data or {}))

    # Validate new amount if provided
    if payload.amount is not None:
        settings = (
            db.query(PaymentSettings)
            .filter(PaymentSettings.user_id == effective_user_id)
            .first()
        )
        if payload.amount > settings.recurring_payment_max:
            raise HTTPException(
                status_code=400,
                detail=f"Amount exceeds recurring limit of ₹{settings.recurring_payment_max}",
            )
        rule.amount = payload.amount

    # Update frequency config
    if payload.frequency is not None:
        rule.frequency = payload.frequency

        # Extract day_config if provided
        if payload.day_config is not None:
            day_of_month = payload.day_config.get("day_of_month")
            day_of_week = payload.day_config.get("day_of_week")
            if day_of_month is not None:
                rule.day_of_month = day_of_month
            if day_of_week is not None:
                rule.day_of_week = day_of_week

        # Recalculate next run date
        rule.next_run_date = calculate_next_run_date(
            rule.frequency,
            day_of_month=rule.day_of_month,
            day_of_week=rule.day_of_week,
            base_date=datetime.now(timezone.utc),
        )

    # Update dates
    if payload.end_date is not None:
        rule.end_date = payload.end_date

    # Update approval config
    if payload.requires_approval is not None:
        rule.requires_approval = payload.requires_approval

    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rule)
    return rule


def pause_recurring_payment_rule(
    db: Session,
    rule_id: int,
    user_id: str | None = None,
) -> RecurringPaymentRule:
    """Pause a recurring payment rule (can be resumed)."""
    rule = get_recurring_payment_rule(db, rule_id, user_id)

    if rule is None:
        raise HTTPException(status_code=404, detail="Recurring payment rule not found")

    if rule.status != "active":
        raise HTTPException(status_code=400, detail="Only active rules can be paused")

    rule.status = "paused"
    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rule)
    return rule


def resume_recurring_payment_rule(
    db: Session,
    rule_id: int,
    user_id: str | None = None,
) -> RecurringPaymentRule:
    """Resume a paused recurring payment rule."""
    rule = get_recurring_payment_rule(db, rule_id, user_id)

    if rule is None:
        raise HTTPException(status_code=404, detail="Recurring payment rule not found")

    if rule.status != "paused":
        raise HTTPException(status_code=400, detail="Only paused rules can be resumed")

    rule.status = "active"
    rule.next_run_date = calculate_next_run_date(
        rule.frequency,
        rule.day_of_month,
        rule.day_of_week,
        datetime.now(timezone.utc),
    )
    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rule)
    return rule


def delete_recurring_payment_rule(
    db: Session,
    rule_id: int,
    user_id: str | None = None,
) -> None:
    """Delete a recurring payment rule.

    Note: Soft deletes via status, not hard deletes.
    """
    rule = get_recurring_payment_rule(db, rule_id, user_id)
    if rule is None:
        return False
    rule.status = "expired"
    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    return True


def get_upcoming_payments(
    db: Session,
    user_id: str,
    days_ahead: int = 30,
) -> list[dict]:
    """Get upcoming recurring payments for user (next N days).

    Returns list of dict with rule info and next scheduled date.
    """
    now_date = datetime.now(timezone.utc).date()
    future_date = now_date + timedelta(days=days_ahead)

    rules = (
        db.query(RecurringPaymentRule)
        .filter(
            RecurringPaymentRule.user_id == user_id,
            RecurringPaymentRule.status == "active",
            RecurringPaymentRule.next_run_date >= now_date,
            RecurringPaymentRule.next_run_date <= future_date,
        )
        .order_by(RecurringPaymentRule.next_run_date)
        .all()
    )

    result = []
    for rule in rules:
        beneficiary = (
            db.query(Beneficiary)
            .filter(
                Beneficiary.id == rule.beneficiary_id,
                Beneficiary.user_id == user_id,
            )
            .first()
        )
        result.append(
            {
                "id": rule.id,
                "beneficiary": {
                    "id": rule.beneficiary_id,
                    "display_name": (
                        beneficiary.nickname if beneficiary else "Unknown Beneficiary"
                    ),
                    "identifier_value": (
                        beneficiary.identifier_value if beneficiary else None
                    ),
                },
                "amount": rule.amount,
                "frequency": rule.frequency,
                "next_run_date": rule.next_run_date.isoformat(),
                "description": rule.description,
            }
        )

    return result


def calculate_next_run_date(
    frequency: str,
    day_of_month: int | None = None,
    day_of_week: str | None = None,
    base_date: datetime | None = None,
    last_run_date: date_type | datetime | None = None,
    day_config: dict[str, Any] | None = None,
) -> datetime:
    """Calculate next run date based on frequency.

    Args:
        frequency: "daily", "weekly", "monthly", "quarterly"
        day_of_month: 1-31 for monthly (e.g., 3 = 3rd of month)
        day_of_week: "monday", "tuesday", etc. for weekly
        base_date: Reference date (defaults to now)

    Returns:
        Next run datetime in UTC
    """
    if day_config:
        day_of_month = day_config.get("day_of_month", day_of_month)
        day_of_week = day_config.get("day_of_week", day_of_week)

    if last_run_date is not None and base_date is None:
        if isinstance(last_run_date, datetime):
            base_date = last_run_date
        else:
            base_date = datetime.combine(last_run_date, datetime.min.time()).replace(
                tzinfo=timezone.utc
            )

    if base_date is None:
        base_date = datetime.now(timezone.utc)

    # Ensure base_date is at start of day
    base_date = base_date.replace(hour=0, minute=0, second=0, microsecond=0)

    if frequency == "daily":
        return (base_date + timedelta(days=1)).date()

    elif frequency == "weekly":
        # Find next occurrence of day_of_week
        if not day_of_week:
            raise ValueError("day_of_week required for weekly frequency")

        day_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }

        target_day = day_map.get(day_of_week.lower())
        if target_day is None:
            raise ValueError(f"Invalid day_of_week: {day_of_week}")

        current_day = base_date.weekday()
        days_ahead = (target_day - current_day) % 7
        if days_ahead == 0:
            days_ahead = 7  # Next week if today is the target day

        return (base_date + timedelta(days=days_ahead)).date()

    elif frequency == "monthly":
        # Run on specified day of month
        if not day_of_month or day_of_month < 1 or day_of_month > 31:
            raise ValueError("day_of_month must be 1-31 for monthly frequency")

        # Try next month
        year = base_date.year
        month = base_date.month + 1
        if month > 12:
            month = 1
            year += 1

        try:
            next_date = datetime(year, month, day_of_month, tzinfo=timezone.utc)
            if next_date <= base_date:
                # If already passed in current month, go to month after next
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                next_date = datetime(year, month, day_of_month, tzinfo=timezone.utc)
        except ValueError:
            # Day doesn't exist in month (e.g., Feb 31), use last day of month
            last_day_next_month = (
                datetime(year, month + 1 if month < 12 else 1, 1, tzinfo=timezone.utc)
                - timedelta(days=1)
            ).day
            next_date = datetime(
                year, month, min(day_of_month, last_day_next_month), tzinfo=timezone.utc
            )

        return next_date.date()

    elif frequency == "quarterly":
        # Run every 3 months on specified day
        if not day_of_month or day_of_month < 1 or day_of_month > 31:
            raise ValueError("day_of_month must be 1-31 for quarterly frequency")

        year = base_date.year
        month = base_date.month + 3
        if month > 12:
            month = month % 12
            year += 1

        try:
            next_date = datetime(year, month, day_of_month, tzinfo=timezone.utc)
        except ValueError:
            # Day doesn't exist, use last day of month
            last_day = (
                datetime(year, month + 1 if month < 12 else 1, 1, tzinfo=timezone.utc)
                - timedelta(days=1)
            ).day
            next_date = datetime(
                year, month, min(day_of_month, last_day), tzinfo=timezone.utc
            )

        return next_date.date()

    else:
        raise ValueError(f"Invalid frequency: {frequency}")
