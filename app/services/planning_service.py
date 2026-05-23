from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.checklist_item import ChecklistItem
from app.models.financial_plan import FinancialPlan
from app.models.recurring_rule import RecurringRule
from app.models.user import User
from app.schemas.planning import (
    ChecklistStatusUpdateRequest,
    FinancialPlanCreate,
    RecurringRuleCreate,
    RecurringRuleUpdate,
    ScheduleFromTextRequest,
)

DAY_PATTERN = re.compile(
    r"\b(?:on|every)\s*(?:the\s*)?(\d{1,2})(?:st|nd|rd|th)?(?:\s*day)?\b",
    flags=re.IGNORECASE,
)
ORDINAL_PATTERN = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\b", flags=re.IGNORECASE)
AMOUNT_PATTERN = re.compile(
    r"(?:₹|inr|rs\.?\s*)?\s*(\d+(?:\.\d+)?)\s*(k|thousand|lakh|lakhs|lac|lacs|crore|crores|cr)?\b",
    flags=re.IGNORECASE,
)

UNIT_MULTIPLIERS = {
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


def extract_day_of_month(text: str) -> int | None:
    match = DAY_PATTERN.search(text)
    if not match:
        match = ORDINAL_PATTERN.search(text)
    if not match:
        return None

    day = int(match.group(1))
    if 1 <= day <= 31:
        return day
    return None


def extract_amount(text: str) -> float | None:
    for match in AMOUNT_PATTERN.finditer(text):
        amount = float(match.group(1))
        unit = (match.group(2) or "").lower()
        if unit:
            multiplier = UNIT_MULTIPLIERS.get(unit)
            if multiplier:
                amount *= multiplier
        if amount > 0:
            return round(amount, 2)
    return None


def infer_rule_meta(text: str) -> tuple[str, str]:
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


def safe_due_date(year: int, month: int, day_of_month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day_of_month, last_day))


def next_due(day_of_month: int, reference: date | None = None) -> date:
    ref = reference or date.today()
    current_month_due = safe_due_date(ref.year, ref.month, day_of_month)
    if current_month_due >= ref:
        return current_month_due

    if ref.month == 12:
        return safe_due_date(ref.year + 1, 1, day_of_month)
    return safe_due_date(ref.year, ref.month + 1, day_of_month)


def advance_month(day_of_month: int, current_due: date) -> date:
    if current_due.month == 12:
        return safe_due_date(current_due.year + 1, 1, day_of_month)
    return safe_due_date(current_due.year, current_due.month + 1, day_of_month)


def create_checklist_item(
    db: Session,
    rule: RecurringRule,
    due_date: date,
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


def ensure_plan_for_user(db: Session, *, plan_id: int | None, user_id: str) -> None:
    if plan_id is None:
        return

    plan_exists = (
        db.query(FinancialPlan)
        .filter(FinancialPlan.id == plan_id, FinancialPlan.user_id == user_id)
        .first()
    )
    if not plan_exists:
        raise HTTPException(status_code=404, detail="Plan not found for this user")


def create_plan_for_user(
    db: Session,
    *,
    current_user: User,
    body: FinancialPlanCreate,
) -> FinancialPlan:
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


def create_recurring_rule_for_user(
    db: Session,
    *,
    current_user: User,
    body: RecurringRuleCreate,
) -> RecurringRule:
    ensure_plan_for_user(db, plan_id=body.plan_id, user_id=current_user.user_id)

    start_ref = body.start_date or date.today()
    rule = RecurringRule(
        user_id=current_user.user_id,
        plan_id=body.plan_id,
        title=body.title,
        category=body.category,
        amount=body.amount,
        day_of_month=body.day_of_month,
        start_date=start_ref,
        next_run_date=next_due(body.day_of_month, start_ref),
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


def create_schedule_from_text_for_user(
    db: Session,
    *,
    current_user: User,
    body: ScheduleFromTextRequest,
) -> dict:
    ensure_plan_for_user(db, plan_id=body.plan_id, user_id=current_user.user_id)

    day_of_month = extract_day_of_month(body.text)
    if day_of_month is None:
        raise HTTPException(
            status_code=422,
            detail="Could not parse schedule day. Include a day like '10th'.",
        )

    amount = extract_amount(body.text)
    if amount is None:
        amount = round(body.default_amount, 2)
    if amount <= 0:
        raise HTTPException(
            status_code=422,
            detail="Could not parse amount. Include amount in text or default_amount.",
        )

    category, title = infer_rule_meta(body.text)
    reminder_days_before = 3 if "remind" in body.text.lower() else 1

    rule = RecurringRule(
        user_id=current_user.user_id,
        plan_id=body.plan_id,
        title=title,
        category=category,
        amount=amount,
        day_of_month=day_of_month,
        start_date=date.today(),
        next_run_date=next_due(day_of_month),
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


def update_recurring_rule_for_user(
    db: Session,
    *,
    rule_id: int,
    current_user: User,
    body: RecurringRuleUpdate,
) -> RecurringRule:
    rule = (
        db.query(RecurringRule)
        .filter(
            RecurringRule.id == rule_id,
            RecurringRule.user_id == current_user.user_id,
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
        rule.next_run_date = next_due(rule.day_of_month, date.today())

    db.commit()
    db.refresh(rule)
    return rule


def materialize_rule_once_for_user(
    db: Session,
    *,
    rule_id: int,
    current_user: User,
) -> ChecklistItem:
    rule = (
        db.query(RecurringRule)
        .filter(
            RecurringRule.id == rule_id,
            RecurringRule.user_id == current_user.user_id,
        )
        .first()
    )
    if not rule or not rule.is_active:
        raise HTTPException(status_code=404, detail="Active recurring rule not found")

    item = create_checklist_item(db, rule, rule.next_run_date)
    rule.next_run_date = advance_month(rule.day_of_month, rule.next_run_date)
    db.commit()
    db.refresh(item)
    return item


def materialize_due_checklists_for_user(
    db: Session,
    *,
    current_user: User,
    until_days: int,
) -> dict[str, str | int]:
    today = date.today()
    horizon = today + timedelta(days=until_days)

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
                create_checklist_item(db, rule, rule.next_run_date)
                created += 1
            rule.next_run_date = advance_month(rule.day_of_month, rule.next_run_date)

    db.commit()
    return {"materialized_count": created, "horizon_date": horizon.isoformat()}


def update_checklist_status_for_user(
    db: Session,
    *,
    item_id: int,
    current_user: User,
    body: ChecklistStatusUpdateRequest,
) -> ChecklistItem:
    item = (
        db.query(ChecklistItem)
        .filter(
            ChecklistItem.id == item_id,
            ChecklistItem.user_id == current_user.user_id,
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
