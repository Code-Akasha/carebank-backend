from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.bill_snooze import BillSnooze
from app.models.checklist_item import ChecklistItem
from app.models.recurring_rule import RecurringRule

_ACTION_MATCHERS: dict[str, dict[str, Any]] = {
    "pay_rent": {
        "categories": {"rent"},
        "title_tokens": ("rent",),
    },
    "pay_gas": {
        "categories": {"gas", "lpg"},
        "title_tokens": ("gas", "lpg"),
    },
    "pay_utility": {
        "categories": {"utility", "utilities", "bill", "bills"},
        "title_tokens": (
            "utility",
            "electric",
            "electricity",
            "water",
            "internet",
            "bill",
        ),
    },
    "pay_bill": {
        "categories": {"bill", "bills", "utility", "utilities"},
        "title_tokens": (
            "bill",
            "utility",
            "electric",
            "electricity",
            "water",
            "internet",
        ),
    },
}


def _matches_action_type(
    action_type: str,
    *,
    category: str | None,
    title: str | None,
) -> bool:
    normalized_type = (action_type or "").strip().lower()
    matcher = _ACTION_MATCHERS.get(normalized_type)
    if not matcher:
        return False

    category_normalized = (category or "").strip().lower()
    title_normalized = (title or "").strip().lower()

    if category_normalized and category_normalized in matcher["categories"]:
        return True

    return any(token in title_normalized for token in matcher["title_tokens"])


def discover_bill_candidates(
    db: Session,
    *,
    user_id: str,
    action_type: str,
    checklist_horizon_days: int = 7,
    rule_horizon_days: int = 35,
    limit: int = 5,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return bill candidates for a given payment action type.

    Candidates are sourced from:
    - pending ChecklistItems due/overdue/soon
    - active RecurringRules upcoming soon

    Snoozed candidates (BillSnooze.snoozed_until > now) are excluded.

    Output is intentionally JSON-serializable so it can be stored in conversation_state.
    """
    normalized_type = (action_type or "").strip().lower()
    if normalized_type not in _ACTION_MATCHERS:
        return []

    now_value = now or datetime.now(timezone.utc)
    today = date.today()

    snoozes = (
        db.query(BillSnooze)
        .filter(
            BillSnooze.user_id == user_id,
            BillSnooze.snoozed_until > now_value,
        )
        .all()
    )
    snoozed_set = {(s.source_type, int(s.source_id)) for s in snoozes}

    candidates: list[dict[str, Any]] = []

    checklist_to = today + timedelta(days=max(0, int(checklist_horizon_days)))
    checklist_from = today - timedelta(days=60)

    items = (
        db.query(ChecklistItem)
        .filter(
            ChecklistItem.user_id == user_id,
            ChecklistItem.status == "pending",
            ChecklistItem.due_date >= checklist_from,
            ChecklistItem.due_date <= checklist_to,
        )
        .order_by(ChecklistItem.due_date.asc(), ChecklistItem.id.asc())
        .all()
    )

    rule_map: dict[int, RecurringRule] = {}
    rule_ids = {
        item.recurring_rule_id for item in items if item.recurring_rule_id is not None
    }
    if rule_ids:
        rules = (
            db.query(RecurringRule).filter(RecurringRule.id.in_(sorted(rule_ids))).all()
        )
        rule_map = {rule.id: rule for rule in rules}

    checklist_rule_ids_included: set[int] = set()
    for item in items:
        if ("checklist_item", int(item.id)) in snoozed_set:
            continue

        rule = rule_map.get(item.recurring_rule_id) if item.recurring_rule_id else None
        category = rule.category if rule else None
        title = item.title or (rule.title if rule else "")
        if not _matches_action_type(normalized_type, category=category, title=title):
            continue

        amount = item.amount
        if amount is None and rule is not None:
            amount = rule.amount

        candidates.append(
            {
                "source_type": "checklist_item",
                "source_id": int(item.id),
                "recurring_rule_id": int(item.recurring_rule_id)
                if item.recurring_rule_id
                else None,
                "title": str(title or "").strip() or "Payment",
                "category": str(category or "").strip() or None,
                "amount": float(amount) if amount is not None else None,
                "due_date": item.due_date.isoformat(),
                "action_type": normalized_type,
            },
        )
        if item.recurring_rule_id is not None:
            checklist_rule_ids_included.add(int(item.recurring_rule_id))

        if len(candidates) >= limit:
            break

    rule_to = today + timedelta(days=max(0, int(rule_horizon_days)))

    rules = (
        db.query(RecurringRule)
        .filter(
            RecurringRule.user_id == user_id,
            RecurringRule.is_active.is_(True),
            RecurringRule.next_run_date <= rule_to,
        )
        .order_by(RecurringRule.next_run_date.asc(), RecurringRule.id.asc())
        .all()
    )

    for rule in rules:
        if len(candidates) >= limit:
            break
        if ("recurring_rule", int(rule.id)) in snoozed_set:
            continue
        if rule.id in checklist_rule_ids_included:
            continue
        if not _matches_action_type(
            normalized_type,
            category=rule.category,
            title=rule.title,
        ):
            continue

        candidates.append(
            {
                "source_type": "recurring_rule",
                "source_id": int(rule.id),
                "recurring_rule_id": int(rule.id),
                "title": str(rule.title or "").strip() or "Recurring payment",
                "category": str(rule.category or "").strip() or None,
                "amount": float(rule.amount) if rule.amount is not None else None,
                "due_date": rule.next_run_date.isoformat(),
                "action_type": normalized_type,
            },
        )

    return candidates
