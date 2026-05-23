from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

from app.core.database import SessionLocal
from app.services.reminder_worker import run_reminder_worker


def _register_and_token(client):
    test_id = uuid.uuid4().hex[:8]
    email = f"reminder_{test_id}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Reminder Test User",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["access_token"], payload["user_id"]


def test_reminder_worker_creates_d3_notification(client):
    token, _ = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    today = datetime.now(timezone.utc).date()
    due_date = today + timedelta(days=3)

    create_rule = client.post(
        "/api/planning/recurring-rules",
        headers=headers,
        json={
            "title": "Pay Rent",
            "category": "rent",
            "amount": 25000,
            "day_of_month": due_date.day,
            "autopay_enabled": False,
            "requires_approval": True,
            "reminder_days_before": 3,
        },
    )
    assert create_rule.status_code == 201

    with SessionLocal() as db:
        result = run_reminder_worker(db, as_of=today, horizon_days=3)

    assert result["notifications_created"] >= 1

    notifications = client.get("/api/notifications", headers=headers)
    assert notifications.status_code == 200
    payload = notifications.json()
    assert any(
        item.get("kind") == "checklist_reminder"
        and (item.get("payload") or {}).get("days_until_due") == 3
        for item in payload
    )


def test_reminder_worker_due_day_creates_action_request(client):
    token, _ = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    today = datetime.now(timezone.utc).date()

    create_rule = client.post(
        "/api/planning/recurring-rules",
        headers=headers,
        json={
            "title": "Pay Rent",
            "category": "rent",
            "amount": 25000,
            "day_of_month": today.day,
            "autopay_enabled": True,
            "requires_approval": True,
            "reminder_days_before": 0,
        },
    )
    assert create_rule.status_code == 201

    with SessionLocal() as db:
        result = run_reminder_worker(db, as_of=today, horizon_days=0)

    assert result["action_requests_created"] >= 1

    action_requests = client.get("/api/actions/requests", headers=headers)
    assert action_requests.status_code == 200
    requests_payload = action_requests.json()
    assert any(
        item.get("action_type") == "pay_rent" and item.get("status") == "pending"
        for item in requests_payload
    )

    notifications = client.get("/api/notifications", headers=headers)
    assert notifications.status_code == 200
    notif_payload = notifications.json()
    assert any(item.get("kind") == "action_request" for item in notif_payload)
