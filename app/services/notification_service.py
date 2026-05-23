"""Notification delivery service — creates DB records and pushes SSE events."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.notification import Notification

logger = logging.getLogger(__name__)


def create_notification(
    db: Session,
    *,
    user_id: str,
    kind: str,
    title: str,
    body: str,
    payload: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> Notification:
    """Create a notification and push it to SSE stream."""
    dedupe = dedupe_key or f"note:{uuid.uuid4().hex}"
    notification = Notification(
        user_id=user_id,
        dedupe_key=dedupe,
        kind=kind,
        title=title,
        body=body,
        payload_json=payload or {},
        created_at=datetime.now(timezone.utc),
    )
    try:
        db.add(notification)
        db.commit()
        db.refresh(notification)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.dedupe_key == dedupe,
            )
            .first()
        )
        if existing:
            return existing
        raise

    # Push to SSE stream (best-effort, non-blocking)
    try:
        from app.routes.events import push_event

        push_event(
            user_id,
            "notification",
            {
                "id": notification.id,
                "kind": kind,
                "title": title,
                "body": body,
                "payload": payload or {},
            },
        )
    except Exception as exc:
        logger.warning("Failed to push SSE notification: %s", exc)

    return notification


def notify_payment_completed(
    db: Session,
    *,
    user_id: str,
    amount: float,
    merchant: str,
    transaction_id: str | None = None,
) -> Notification:
    """Send a payment completion notification."""
    return create_notification(
        db,
        user_id=user_id,
        kind="payment",
        title="Payment Completed",
        body=f"₹{amount:,.0f} paid to {merchant}",
        payload={
            "amount": amount,
            "merchant": merchant,
            "transaction_id": transaction_id,
        },
    )


def notify_savings_transfer(
    db: Session,
    *,
    user_id: str,
    amount: float,
    transaction_id: str | None = None,
) -> Notification:
    """Send an auto-savings transfer notification."""
    return create_notification(
        db,
        user_id=user_id,
        kind="savings",
        title="Auto-Savings Transfer",
        body=f"₹{amount:,.0f} transferred to your savings goal",
        payload={
            "amount": amount,
            "transaction_id": transaction_id,
        },
    )


def notify_health_score_change(
    db: Session,
    *,
    user_id: str,
    old_score: int,
    new_score: int,
) -> Notification:
    """Send a health score change notification."""
    direction = "improved" if new_score > old_score else "decreased"
    return create_notification(
        db,
        user_id=user_id,
        kind="health_score",
        title="Health Score Update",
        body=f"Your financial health score has {direction} from {old_score} to {new_score}",
        payload={
            "old_score": old_score,
            "new_score": new_score,
        },
    )
