from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session as DBSession

from app.models.bill_snooze import BillSnooze
from app.models.user import User
from app.services.action_request_service import (
    approve_action_request_for_user,
    create_action_request_for_user,
    reject_action_request_for_user,
)
from app.services.bill_discovery import discover_bill_candidates
from app.services.planning_service import create_schedule_from_text_for_user
from app.schemas.action_engine import ActionDecisionRequest, ActionRequestCreate
from app.schemas.planning import ScheduleFromTextRequest


def apply_planned_chat_action(
    *,
    agent_response: str,
    response_metadata: dict[str, Any] | None,
    current_user: User,
    db: DBSession,
) -> tuple[str, dict[str, Any]]:
    """Execute a planned chat action (if present) and return updated response + metadata.

    The planner (CommunicationAgent) emits `response_metadata['action']` as an intent to
    execute domain operations. This function performs the side effect and rewrites the
    assistant response to reflect the actual outcome.

    If no executable action is present, returns inputs unchanged.
    """

    metadata: dict[str, Any] = (
        response_metadata if isinstance(response_metadata, dict) else {}
    )

    action = metadata.get("action")
    if not isinstance(action, dict):
        return agent_response, metadata

    action_type = action.get("type")

    if action_type == "discover_bills":
        requested_action_type = str(action.get("action_type") or "").strip().lower()
        if not requested_action_type:
            return agent_response, metadata

        candidates = discover_bill_candidates(
            db,
            user_id=str(current_user.user_id),
            action_type=requested_action_type,
            checklist_horizon_days=int(action.get("checklist_horizon_days", 7) or 7),
            rule_horizon_days=int(action.get("rule_horizon_days", 35) or 35),
            limit=int(action.get("limit", 5) or 5),
        )

        object_map = {
            "pay_rent": "rent",
            "pay_gas": "gas bill",
            "pay_utility": "utility bill",
            "pay_bill": "bill",
        }
        label_map = {
            "pay_rent": "pay rent",
            "pay_bill": "pay a bill",
            "pay_gas": "pay the gas bill",
            "pay_utility": "pay the utility bill",
        }

        object_label = object_map.get(requested_action_type, "bill")
        action_label = label_map.get(
            requested_action_type, requested_action_type.replace("_", " ")
        )

        def _format_amount(value: Any) -> str:
            try:
                amount_value = float(value)
            except (TypeError, ValueError):
                return ""
            return f"INR {amount_value:,.2f}"

        if not candidates:
            return (
                (
                    f"I couldn't find any pending or scheduled {object_label} in your plans. "
                    f"How much should I {action_label}?"
                ),
                {
                    **metadata,
                    "clear_pending": False,
                    "ui_actions": [],
                    "pending_state": {
                        "pending_intent": "actions",
                        "actions": {
                            "flow": "action_request",
                            "action_type": requested_action_type,
                            "action_payload": {
                                "amount": None,
                                "description": "Payment requested via chat",
                            },
                        },
                    },
                    "action_result": {
                        "type": "discover_bills",
                        "matched": 0,
                        "action_type": requested_action_type,
                    },
                },
            )

        if len(candidates) == 1:
            candidate = candidates[0]
            title = str(candidate.get("title") or "Payment")
            due_date = str(candidate.get("due_date") or "")
            amount_str = _format_amount(candidate.get("amount"))
            amount_clause = f" for {amount_str}" if amount_str else ""
            due_clause = f" due {due_date}" if due_date else ""
            return (
                f"I found: {title}{due_clause}{amount_clause}. What do you want to do?",
                {
                    **metadata,
                    "clear_pending": False,
                    "ui_actions": [
                        {"label": "Pay now", "message": "pay now"},
                        {"label": "Later", "message": "later"},
                    ],
                    "pending_state": {
                        "pending_intent": "actions",
                        "actions": {
                            "flow": "bill_suggestion",
                            "candidate": candidate,
                        },
                    },
                    "action_result": {
                        "type": "discover_bills",
                        "matched": 1,
                        "action_type": requested_action_type,
                    },
                },
            )

        lines = [
            "I found multiple matches. Which one do you mean?",
        ]
        for idx, candidate in enumerate(candidates, start=1):
            title = str(candidate.get("title") or "Payment")
            due_date = str(candidate.get("due_date") or "")
            amount_str = _format_amount(candidate.get("amount"))
            bits = [title]
            if due_date:
                bits.append(f"due {due_date}")
            if amount_str:
                bits.append(amount_str)
            lines.append(f"{idx}) " + " — ".join(bits))
        lines.append("Reply with the number (1, 2, ...).")

        return (
            "\n".join(lines),
            {
                **metadata,
                "clear_pending": False,
                "ui_actions": [],
                "pending_state": {
                    "pending_intent": "actions",
                    "actions": {
                        "flow": "bill_picker",
                        "candidates": candidates,
                        "action_type": requested_action_type,
                    },
                },
                "action_result": {
                    "type": "discover_bills",
                    "matched": len(candidates),
                    "action_type": requested_action_type,
                },
            },
        )

    if action_type == "snooze_bill":
        source_type = str(action.get("source_type") or "").strip().lower()
        if source_type not in {"checklist_item", "recurring_rule"}:
            return agent_response, metadata

        source_id_raw = action.get("source_id")
        try:
            source_id = int(source_id_raw)
        except (TypeError, ValueError):
            return agent_response, metadata

        hours_raw = action.get("hours", 24)
        try:
            hours = int(hours_raw)
        except (TypeError, ValueError):
            hours = 24
        hours = max(1, min(hours, 24 * 14))

        snoozed_until = datetime.now(timezone.utc) + timedelta(hours=hours)

        existing = (
            db.query(BillSnooze)
            .filter(
                BillSnooze.user_id == current_user.user_id,
                BillSnooze.source_type == source_type,
                BillSnooze.source_id == source_id,
            )
            .first()
        )
        if existing:
            existing.snoozed_until = snoozed_until
        else:
            db.add(
                BillSnooze(
                    user_id=current_user.user_id,
                    source_type=source_type,
                    source_id=source_id,
                    snoozed_until=snoozed_until,
                )
            )
        db.commit()

        return (
            "Okay. I'll remind you later.",
            {
                **metadata,
                "clear_pending": True,
                "ui_actions": [],
                "action_result": {
                    "type": "snooze_bill",
                    "source_type": source_type,
                    "source_id": source_id,
                    "snoozed_until": snoozed_until.isoformat(),
                },
            },
        )

    if action_type == "create_schedule_from_text":
        text = str(action.get("text") or "").strip()
        if not text:
            return agent_response, metadata

        default_amount_raw = action.get("default_amount", 0)
        try:
            default_amount = float(default_amount_raw or 0)
        except (TypeError, ValueError):
            default_amount = 0.0

        body = ScheduleFromTextRequest(
            text=text,
            default_amount=default_amount,
            autopay_enabled=bool(action.get("autopay_enabled", True)),
            requires_approval=bool(action.get("requires_approval", True)),
        )

        try:
            created = create_schedule_from_text_for_user(
                db,
                current_user=current_user,
                body=body,
            )
        except Exception as exc:  # noqa: BLE001
            return (
                f"I parsed your scheduling request, but execution failed. Reason: {exc}",
                {
                    **metadata,
                    "clear_pending": False,
                },
            )

        rule = created.get("rule")
        extracted = created.get("extracted") or {}

        day_of_month = extracted.get("day_of_month")
        amount = extracted.get("amount")
        title = extracted.get("title")
        category = extracted.get("category")

        if hasattr(rule, "id"):
            rule_id = getattr(rule, "id", None)
        elif isinstance(rule, dict):
            rule_id = rule.get("id")
        else:
            rule_id = None

        response = (
            f"Done. I created your recurring schedule: {title or 'payment'} "
            f"for INR {float(amount or 0):,.2f} on day {day_of_month}. "
            f"Category: {category or 'custom'}."
            + (f" Rule ID: {rule_id}." if rule_id is not None else "")
        )

        return (
            response,
            {
                **metadata,
                "clear_pending": True,
                "action_result": {
                    "type": "create_schedule_from_text",
                    "rule_id": rule_id,
                    "day_of_month": day_of_month,
                    "amount": amount,
                    "category": category,
                },
            },
        )

    if action_type in {
        "create_action_request",
        "approve_action_request",
        "reject_action_request",
    }:
        label_map = {
            "pay_rent": "pay rent",
            "pay_bill": "pay a bill",
            "pay_gas": "pay the gas bill",
            "pay_utility": "pay the utility bill",
            "transfer_savings": "transfer to savings",
            "record_note": "record a note",
        }

        def _format_amount(value: Any) -> str:
            try:
                amount_value = float(value)
            except (TypeError, ValueError):
                return ""
            return f"INR {amount_value:,.2f}"

        if action_type == "create_action_request":
            tool_action_type = str(action.get("action_type") or "").strip()
            action_payload = action.get("action_payload")
            if not tool_action_type or not isinstance(action_payload, dict):
                return agent_response, metadata

            expires_in_hours_raw = action.get("expires_in_hours", 24)
            try:
                expires_in_hours = int(expires_in_hours_raw)
            except (TypeError, ValueError):
                expires_in_hours = 24

            idempotency_key = action.get("idempotency_key")
            if isinstance(idempotency_key, str):
                idempotency_key = idempotency_key.strip() or None
            else:
                idempotency_key = None

            try:
                created = create_action_request_for_user(
                    db,
                    current_user=current_user,
                    body=ActionRequestCreate(
                        action_type=tool_action_type,
                        action_payload=action_payload,
                        idempotency_key=idempotency_key,
                        expires_in_hours=expires_in_hours,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                return (
                    f"I parsed your action request, but execution failed. Reason: {exc}",
                    {
                        **metadata,
                        "clear_pending": False,
                        "pending_state": {
                            "pending_intent": "actions",
                            "actions": {
                                "flow": "action_request",
                                "action_type": tool_action_type,
                                "action_payload": action_payload,
                            },
                        },
                    },
                )

            request = created.request
            execution = created.execution

            action_label = label_map.get(request.action_type) or request.action_type
            amount_str = _format_amount(request.action_payload.get("amount"))
            amount_clause = f" for {amount_str}" if amount_str else ""

            if request.status == "pending":
                return (
                    (
                        f"I created an action request (ID {request.id}) to {action_label}{amount_clause}. "
                        "Reply 'yes' to approve or 'no' to cancel."
                    ),
                    {
                        **metadata,
                        "clear_pending": False,
                        "pending_state": {
                            "pending_intent": "actions",
                            "actions": {
                                "flow": "action_approval",
                                "request_id": request.id,
                                "action_type": request.action_type,
                                "action_payload": request.action_payload,
                            },
                        },
                        "action_result": {
                            "type": "create_action_request",
                            "request_id": request.id,
                            "request_status": request.status,
                        },
                    },
                )

            exec_clause = ""
            if execution is not None:
                exec_clause = (
                    f" Execution ID: {execution.id}. Status: {execution.status}."
                )

            return (
                (
                    f"Done. Approved action request (ID {request.id}) to {action_label}{amount_clause}."
                    + exec_clause
                ),
                {
                    **metadata,
                    "clear_pending": True,
                    "action_result": {
                        "type": "create_action_request",
                        "request_id": request.id,
                        "request_status": request.status,
                        "execution_id": execution.id if execution else None,
                        "execution_status": execution.status if execution else None,
                    },
                },
            )

        request_id_raw = action.get("request_id")
        try:
            request_id = int(request_id_raw)
        except (TypeError, ValueError):
            return agent_response, metadata

        if action_type == "approve_action_request":
            try:
                decided = approve_action_request_for_user(
                    db,
                    request_id=request_id,
                    body=ActionDecisionRequest(reason="Approved via chat"),
                    current_user=current_user,
                )
            except Exception as exc:  # noqa: BLE001
                return (
                    f"I tried to approve that request, but it failed. Reason: {exc}",
                    {
                        **metadata,
                        "clear_pending": False,
                    },
                )

            request = decided.request
            execution = decided.execution
            action_label = label_map.get(request.action_type) or request.action_type
            amount_str = _format_amount(request.action_payload.get("amount"))
            amount_clause = f" for {amount_str}" if amount_str else ""

            exec_clause = ""
            if execution is not None:
                exec_clause = (
                    f" Execution ID: {execution.id}. Status: {execution.status}."
                )

            return (
                (
                    f"Approved action request (ID {request.id}) to {action_label}{amount_clause}."
                    + exec_clause
                ),
                {
                    **metadata,
                    "clear_pending": True,
                    "action_result": {
                        "type": "approve_action_request",
                        "request_id": request.id,
                        "request_status": request.status,
                        "execution_id": execution.id if execution else None,
                        "execution_status": execution.status if execution else None,
                    },
                },
            )

        if action_type == "reject_action_request":
            try:
                decided = reject_action_request_for_user(
                    db,
                    request_id=request_id,
                    body=ActionDecisionRequest(reason="Rejected via chat"),
                    current_user=current_user,
                )
            except Exception as exc:  # noqa: BLE001
                return (
                    f"I tried to reject that request, but it failed. Reason: {exc}",
                    {
                        **metadata,
                        "clear_pending": False,
                    },
                )

            request = decided.request
            action_label = label_map.get(request.action_type) or request.action_type
            amount_str = _format_amount(request.action_payload.get("amount"))
            amount_clause = f" for {amount_str}" if amount_str else ""

            return (
                f"Cancelled action request (ID {request.id}) to {action_label}{amount_clause}.",
                {
                    **metadata,
                    "clear_pending": True,
                    "action_result": {
                        "type": "reject_action_request",
                        "request_id": request.id,
                        "request_status": request.status,
                    },
                },
            )

        return agent_response, metadata

    return agent_response, metadata
