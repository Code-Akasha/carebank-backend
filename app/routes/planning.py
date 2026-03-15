from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.checklist_item import ChecklistItem
from app.models.financial_plan import FinancialPlan
from app.models.recurring_rule import RecurringRule
from app.models.user import User
from app.schemas.planning import (
    ChecklistItemResponse,
    ChecklistStatusUpdateRequest,
    FinancialPlanCreate,
    FinancialPlanResponse,
    RecurringRuleCreate,
    RecurringRuleResponse,
    RecurringRuleUpdate,
    ScheduleFromTextRequest,
    ScheduleFromTextResponse,
    SchedulerMaterializeRequest,
)

router = APIRouter(prefix="/api/planning", tags=["planning"])


_DAY_PATTERN = re.compile(
    r"\b(?:on|every)\s*(?:the\s*)?(\d{1,2})(?:st|nd|rd|th)?(?:\s*day)?\b",
    flags=re.IGNORECASE,
)
_ORDINAL_PATTERN = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\b", flags=re.IGNORECASE)
_AMOUNT_PATTERN = re.compile(
    r"(?:₹|inr|rs\.?\s*)?\s*(\d+(?:\.\d+)?)\s*(k|thousand|lakh|lakhs|lac|lacs|crore|crores|cr)?\b",
    flags=re.IGNORECASE,
)

_UNIT_MULTIPLIERS = {
    "k": 1_000,
    "thousand": 1_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "cr": 10_000_000,
}


def _extract_day_of_month(text: str) -> int | None:
    match = _DAY_PATTERN.search(text)
    if not match:
        match = _ORDINAL_PATTERN.search(text)
    if not match:
        return None

    day = int(match.group(1))
    if 1 <= day <= 31:
        return day
    return None


def _extract_amount(text: str) -> float | None:
    for match in _AMOUNT_PATTERN.finditer(text):
        amount = float(match.group(1))
        unit = (match.group(2) or "").lower()
        if unit:
            multiplier = _UNIT_MULTIPLIERS.get(unit)
            if multiplier:
                amount *= multiplier
        if amount > 0:
            return round(amount, 2)
    return None


def _infer_rule_meta(text: str) -> tuple[str, str]:
    lower = text.lower()
    if "rent" in lower:
        return "rent", "Pay Rent"
    if "gas" in lower:
        return "gas", "Pay Gas Bill"
    if any(word in lower for word in ["bill", "electricity", "internet", "water"]):
        return "bill", "Pay Utility Bill"
    if any(word in lower for word in ["invest", "sip", "mutual fund"]):
        return "investment", "Monthly Investment"
    if any(word in lower for word in ["save", "savings", "transfer"]):
        return "saving", "Monthly Savings"
    return "custom", "Recurring Payment"


def _safe_due_date(year: int, month: int, day_of_month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day_of_month, last_day))


def _next_due(day_of_month: int, reference: date | None = None) -> date:
    ref = reference or date.today()
    current_month_due = _safe_due_date(ref.year, ref.month, day_of_month)
    if current_month_due >= ref:
        return current_month_due

    if ref.month == 12:
        return _safe_due_date(ref.year + 1, 1, day_of_month)
    return _safe_due_date(ref.year, ref.month + 1, day_of_month)


def _advance_month(day_of_month: int, current_due: date) -> date:
    if current_due.month == 12:
        return _safe_due_date(current_due.year + 1, 1, day_of_month)
    return _safe_due_date(current_due.year, current_due.month + 1, day_of_month)


def _create_checklist_item(
    db: Session, rule: RecurringRule, due_date: date
) -> ChecklistItem:
    existing = (
        db.query(ChecklistItem)
        .filter(
            ChecklistItem.user_id == rule.user_id,
            ChecklistItem.recurring_rule_id == rule.id,
            ChecklistItem.due_date == due_date,
        )
        .first()
    )
    if existing:
        return existing

    item = ChecklistItem(
        user_id=rule.user_id,
        recurring_rule_id=rule.id,
        title=f"{rule.title} ({due_date.isoformat()})",
        due_date=due_date,
        amount=rule.amount,
        status="pending",
    )
    db.add(item)
    return item


@router.post(
    "/plans", response_model=FinancialPlanResponse, status_code=status.HTTP_201_CREATED
)
def create_plan(
    body: FinancialPlanCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    plan = FinancialPlan(
        user_id=current_user.user_id,
        title=body.title,
        goal_type=body.goal_type,
        target_amount=body.target_amount,
        monthly_budget=body.monthly_budget,
        notes=body.notes,
        status="active",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/plans", response_model=list[FinancialPlanResponse])
def list_plans(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return (
        db.query(FinancialPlan)
        .filter(FinancialPlan.user_id == current_user.user_id)
        .order_by(FinancialPlan.created_at.desc())
        .all()
    )


@router.post(
    "/recurring-rules",
    response_model=RecurringRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_recurring_rule(
    body: RecurringRuleCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    if body.plan_id is not None:
        plan_exists = (
            db.query(FinancialPlan)
            .filter(
                FinancialPlan.id == body.plan_id,
                FinancialPlan.user_id == current_user.user_id,
            )
            .first()
        )
        if not plan_exists:
            raise HTTPException(
                status_code=404,
                detail="Plan not found for this user",
            )

    start_ref = body.start_date or date.today()
    rule = RecurringRule(
        user_id=current_user.user_id,
        plan_id=body.plan_id,
        title=body.title,
        category=body.category,
        amount=body.amount,
        day_of_month=body.day_of_month,
        start_date=start_ref,
        next_run_date=_next_due(body.day_of_month, start_ref),
        autopay_enabled=body.autopay_enabled,
        requires_approval=body.requires_approval,
        reminder_days_before=body.reminder_days_before,
        trusted_recurring=False,
        is_active=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.post(
    "/schedule-from-text",
    response_model=ScheduleFromTextResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule_from_text(
    body: ScheduleFromTextRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    if body.plan_id is not None:
        plan_exists = (
            db.query(FinancialPlan)
            .filter(
                FinancialPlan.id == body.plan_id,
                FinancialPlan.user_id == current_user.user_id,
            )
            .first()
        )
        if not plan_exists:
            raise HTTPException(status_code=404, detail="Plan not found for this user")

    day_of_month = _extract_day_of_month(body.text)
    if day_of_month is None:
        raise HTTPException(
            status_code=422,
            detail="Could not parse schedule day. Include a day like '10th'.",
        )

    amount = _extract_amount(body.text)
    if amount is None:
        amount = round(body.default_amount, 2)
    if amount <= 0:
        raise HTTPException(
            status_code=422,
            detail="Could not parse amount. Include amount in text or default_amount.",
        )

    category, title = _infer_rule_meta(body.text)
    reminder_days_before = 3 if "remind" in body.text.lower() else 1

    rule = RecurringRule(
        user_id=current_user.user_id,
        plan_id=body.plan_id,
        title=title,
        category=category,
        amount=amount,
        day_of_month=day_of_month,
        start_date=date.today(),
        next_run_date=_next_due(day_of_month),
        autopay_enabled=body.autopay_enabled,
        requires_approval=body.requires_approval,
        reminder_days_before=reminder_days_before,
        trusted_recurring=False,
        is_active=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    return {
        "rule": rule,
        "extracted": {
            "day_of_month": day_of_month,
            "amount": amount,
            "category": category,
            "title": title,
            "source_text": body.text,
        },
    }


@router.get("/recurring-rules", response_model=list[RecurringRuleResponse])
def list_recurring_rules(
    current_user: Annotated[User, Depends(get_current_user)],
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(RecurringRule).filter(
        RecurringRule.user_id == current_user.user_id
    )
    if not include_inactive:
        query = query.filter(RecurringRule.is_active.is_(True))
    return query.order_by(RecurringRule.next_run_date.asc()).all()


@router.patch("/recurring-rules/{rule_id}", response_model=RecurringRuleResponse)
def update_recurring_rule(
    rule_id: int,
    body: RecurringRuleUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    rule = (
        db.query(RecurringRule)
        .filter(
            RecurringRule.id == rule_id, RecurringRule.user_id == current_user.user_id
        )
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Recurring rule not found")

    payload = body.model_dump(exclude_unset=True)
    day_changed = "day_of_month" in payload

    for key, value in payload.items():
        setattr(rule, key, value)

    if day_changed:
        rule.next_run_date = _next_due(rule.day_of_month, date.today())

    db.commit()
    db.refresh(rule)
    return rule


@router.post(
    "/recurring-rules/{rule_id}/materialize",
    response_model=ChecklistItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def materialize_rule_once(
    rule_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    rule = (
        db.query(RecurringRule)
        .filter(
            RecurringRule.id == rule_id, RecurringRule.user_id == current_user.user_id
        )
        .first()
    )
    if not rule or not rule.is_active:
        raise HTTPException(status_code=404, detail="Active recurring rule not found")

    item = _create_checklist_item(db, rule, rule.next_run_date)
    rule.next_run_date = _advance_month(rule.day_of_month, rule.next_run_date)

    db.commit()
    db.refresh(item)
    return item


@router.post("/scheduler/materialize-due")
def materialize_due_checklists(
    body: SchedulerMaterializeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    today = date.today()
    horizon = today + timedelta(days=body.until_days)

    rules = (
        db.query(RecurringRule)
        .filter(
            RecurringRule.user_id == current_user.user_id,
            RecurringRule.is_active.is_(True),
            RecurringRule.next_run_date <= horizon,
        )
        .order_by(RecurringRule.next_run_date.asc())
        .all()
    )

    created = 0
    for rule in rules:
        while rule.next_run_date <= horizon:
            before = (
                db.query(ChecklistItem)
                .filter(
                    ChecklistItem.user_id == current_user.user_id,
                    ChecklistItem.recurring_rule_id == rule.id,
                    ChecklistItem.due_date == rule.next_run_date,
                )
                .first()
            )
            if before is None:
                _create_checklist_item(db, rule, rule.next_run_date)
                created += 1
            rule.next_run_date = _advance_month(rule.day_of_month, rule.next_run_date)

    db.commit()

    return {
        "materialized_count": created,
        "horizon_date": horizon.isoformat(),
    }


@router.get("/checklist", response_model=list[ChecklistItemResponse])
def list_checklist(
    current_user: Annotated[User, Depends(get_current_user)],
    status_filter: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(ChecklistItem).filter(
        ChecklistItem.user_id == current_user.user_id
    )

    if status_filter:
        query = query.filter(ChecklistItem.status == status_filter)
    if from_date:
        query = query.filter(ChecklistItem.due_date >= from_date)
    if to_date:
        query = query.filter(ChecklistItem.due_date <= to_date)

    return query.order_by(ChecklistItem.due_date.asc(), ChecklistItem.id.asc()).all()


@router.patch("/checklist/{item_id}", response_model=ChecklistItemResponse)
def update_checklist_status(
    item_id: int,
    body: ChecklistStatusUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    item = (
        db.query(ChecklistItem)
        .filter(
            ChecklistItem.id == item_id, ChecklistItem.user_id == current_user.user_id
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")

    item.status = body.status
    item.completed_at = (
        datetime.now(timezone.utc) if body.status == "completed" else None
    )

    if body.status == "completed" and item.recurring_rule_id is not None:
        rule = (
            db.query(RecurringRule)
            .filter(
                RecurringRule.id == item.recurring_rule_id,
                RecurringRule.user_id == current_user.user_id,
            )
            .first()
        )
        # Hybrid autonomy: first successful approval unlocks trusted recurring mode.
        if (
            rule
            and rule.autopay_enabled
            and rule.requires_approval
            and not rule.trusted_recurring
        ):
            rule.trusted_recurring = True
            rule.requires_approval = False

    db.commit()
    db.refresh(item)
    return item
