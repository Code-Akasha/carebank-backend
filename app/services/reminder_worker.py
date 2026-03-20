from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.checklist_item import ChecklistItem
from app.models.notification import Notification
from app.models.recurring_rule import RecurringRule
from app.models.user import User
from app.routes.actions import create_action_request as create_action_request_api
from app.schemas.action_engine import ActionRequestCreate

logger = logging.getLogger(__name__)


_REMINDER_OFFSETS = (3, 1, 0)

_ACTION_TYPE_BY_CATEGORY: dict[str, str] = {
    "rent": "pay_rent",
    "gas": "pay_gas",
    "bill": "pay_utility",
    "bills": "pay_bill",
    "utility": "pay_utility",
    "utilities": "pay_utility",
    "saving": "transfer_savings",
    "savings": "transfer_savings",
}


def _safe_due_date(year: int, month: int, day_of_month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day_of_month, last_day))


def _advance_month(day_of_month: int, current_due: date) -> date:
    if current_due.month == 12:
        return _safe_due_date(current_due.year + 1, 1, day_of_month)
    return _safe_due_date(current_due.year, current_due.month + 1, day_of_month)


def _ensure_checklist_item(
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


def _create_notification_if_missing(
    db: Session,
    *,
    user_id: str,
    dedupe_key: str,
    kind: str,
    title: str,
    body: str,
    payload: dict[str, Any] | None = None,
) -> bool:
    existing = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.dedupe_key == dedupe_key)
        .first()
    )
    if existing:
        return False

    db.add(
        Notification(
            user_id=user_id,
            dedupe_key=dedupe_key,
            kind=kind,
            title=title,
            body=body,
            payload_json=payload,
        )
    )
    return True


def _rule_to_action_type(rule: RecurringRule) -> str | None:
    category = (rule.category or "").strip().lower()
    if category in _ACTION_TYPE_BY_CATEGORY:
        return _ACTION_TYPE_BY_CATEGORY[category]

    title = (rule.title or "").strip().lower()
    if "rent" in title:
        return "pay_rent"
    if "gas" in title:
        return "pay_gas"
    if "utility" in title or "electric" in title or "bill" in title:
        return "pay_utility"
    if "save" in title or "savings" in title or "transfer" in title:
        return "transfer_savings"
    return None


def run_reminder_worker(
    db: Session,
    *,
    as_of: date | None = None,
    horizon_days: int = 3,
) -> dict[str, Any]:
    """Materialize checklists + emit reminders + create due-day action requests.

    Intended to be run as a periodic job (e.g., daily). It is idempotent via:
    - checklist uniqueness (rule_id + due_date)
    - notification dedupe keys
    - action request idempotency keys
    """

    today = as_of or date.today()
    horizon = today + timedelta(days=max(0, int(horizon_days)))

    materialized = 0
    notifications_created = 0
    action_requests_created = 0

    rules = (
        db.query(RecurringRule)
        .join(User, RecurringRule.user_id == User.user_id)
        .filter(
            User.is_active.is_(True),
            RecurringRule.is_active.is_(True),
            RecurringRule.next_run_date <= horizon,
        )
        .order_by(RecurringRule.next_run_date.asc())
        .all()
    )

    for rule in rules:
        while rule.next_run_date <= horizon:
            before = (
                db.query(ChecklistItem)
                .filter(
                    ChecklistItem.user_id == rule.user_id,
                    ChecklistItem.recurring_rule_id == rule.id,
                    ChecklistItem.due_date == rule.next_run_date,
                )
                .first()
            )
            if before is None:
                _ensure_checklist_item(db, rule, rule.next_run_date)
                materialized += 1
            rule.next_run_date = _advance_month(rule.day_of_month, rule.next_run_date)

    db.commit()

    items = (
        db.query(ChecklistItem)
        .join(User, ChecklistItem.user_id == User.user_id)
        .filter(
            User.is_active.is_(True),
            ChecklistItem.status == "pending",
            ChecklistItem.due_date <= horizon,
        )
        .order_by(ChecklistItem.due_date.asc(), ChecklistItem.id.asc())
        .all()
    )

    recurring_rule_ids = {
        item.recurring_rule_id for item in items if item.recurring_rule_id is not None
    }
    rule_map: dict[int, RecurringRule] = {}
    if recurring_rule_ids:
        rule_map = {
            rule.id: rule
            for rule in (
                db.query(RecurringRule)
                .filter(RecurringRule.id.in_(sorted(recurring_rule_ids)))
                .all()
            )
        }

    user_ids = {item.user_id for item in items}
    users = {
        user.user_id: user
        for user in db.query(User).filter(User.user_id.in_(sorted(user_ids))).all()
    }

    for item in items:
        delta_days = (item.due_date - today).days

        if delta_days in _REMINDER_OFFSETS:
            if delta_days == 0:
                kind = "checklist_due"
                title = "Due today"
                body = f"{item.title} is due today."
                suffix = "due"
            else:
                kind = "checklist_reminder"
                title = "Upcoming due item"
                body = f"Reminder: {item.title} is due in {delta_days} day(s)."
                suffix = f"d-{delta_days}"

            if _create_notification_if_missing(
                db,
                user_id=item.user_id,
                dedupe_key=f"checklist:{item.id}:{suffix}",
                kind=kind,
                title=title,
                body=body,
                payload={
                    "checklist_item_id": item.id,
                    "recurring_rule_id": item.recurring_rule_id,
                    "due_date": item.due_date.isoformat(),
                    "days_until_due": delta_days,
                },
            ):
                notifications_created += 1

        if delta_days < 0:
            if _create_notification_if_missing(
                db,
                user_id=item.user_id,
                dedupe_key=f"checklist:{item.id}:overdue",
                kind="checklist_overdue",
                title="Overdue item",
                body=f"Overdue: {item.title} was due on {item.due_date.isoformat()}.",
                payload={
                    "checklist_item_id": item.id,
                    "recurring_rule_id": item.recurring_rule_id,
                    "due_date": item.due_date.isoformat(),
                    "days_overdue": abs(delta_days),
                },
            ):
                notifications_created += 1

        rule = rule_map.get(item.recurring_rule_id) if item.recurring_rule_id else None
        if not rule or not rule.autopay_enabled:
            continue

        # Create an action request on due-day; for overdue items, also ensure an action request exists
        if delta_days > 0:
            continue

        action_type = _rule_to_action_type(rule)
        if not action_type:
            continue

        amount = item.amount if item.amount is not None else rule.amount
        try:
            amount_value = float(amount or 0)
        except (TypeError, ValueError):
            amount_value = 0.0
        if amount_value <= 0:
            continue

        current_user = users.get(item.user_id)
        if current_user is None:
            continue

        idempotency_key = (
            f"recurring:{rule.id}:{item.due_date.isoformat()}:{action_type}"
        )

        try:
            created = create_action_request_api(
                ActionRequestCreate(
                    action_type=action_type,
                    action_payload={
                        "amount": amount_value,
                        "category": rule.category,
                        "description": f"Autopay from recurring rule {rule.id} due {item.due_date.isoformat()}",
                        "recurring_rule_id": rule.id,
                        "due_date": item.due_date.isoformat(),
                    },
                    idempotency_key=idempotency_key,
                    expires_in_hours=72,
                ),
                current_user=current_user,
                db=db,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Reminder worker action request failed for user=%s rule=%s: %s",
                item.user_id,
                rule.id,
                exc,
            )
            continue

        if not created.request.replayed:
            action_requests_created += 1

        if _create_notification_if_missing(
            db,
            user_id=item.user_id,
            dedupe_key=f"checklist:{item.id}:action_request",
            kind="action_request",
            title="Action request created",
            body=(
                f"Created action request (ID {created.request.id}) for {rule.title}. "
                f"Status: {created.request.status}."
            ),
            payload={
                "checklist_item_id": item.id,
                "recurring_rule_id": rule.id,
                "action_request_id": created.request.id,
                "action_request_status": created.request.status,
                "execution_id": created.execution.id if created.execution else None,
                "execution_status": created.execution.status
                if created.execution
                else None,
            },
        ):
            notifications_created += 1

    db.commit()

    return {
        "as_of": today.isoformat(),
        "horizon": horizon.isoformat(),
        "materialized_checklists": materialized,
        "notifications_created": notifications_created,
        "action_requests_created": action_requests_created,
    }


def mark_notification_read(db: Session, *, notification_id: int, user_id: str) -> bool:
    item = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if not item:
        return False
    item.read_at = datetime.now(timezone.utc)
    db.commit()
    return True
