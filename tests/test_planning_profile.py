from __future__ import annotations

import uuid


def _register_and_token(client):
    test_id = uuid.uuid4().hex[:8]
    email = f"plan_{test_id}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Planning Test User",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["access_token"], payload["user_id"]


def test_chat_requires_auth(client):
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code in (401, 403)


def test_chat_rejects_cross_user_payload(client):
    token, _ = _register_and_token(client)

    response = client.post(
        "/api/chat",
        json={"message": "show my balance", "user_id": "user_999"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_profile_upsert_and_read(client):
    token, user_id = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    initial = client.get("/api/profile", headers=headers)
    assert initial.status_code == 200
    initial_data = initial.json()
    assert initial_data["user_id"] == user_id
    assert initial_data["monthly_salary"] == 0

    update = client.put(
        "/api/profile",
        headers=headers,
        json={
            "monthly_salary": 120000,
            "currency": "INR",
            "min_safe_balance": 15000,
            "savings_goal_pct": 0.3,
            "risk_tolerance": "moderate",
            "persistent_expenses": [
                {
                    "name": "House Rent",
                    "amount": 25000,
                    "day_of_month": 10,
                    "category": "rent",
                },
                {
                    "name": "Gas Bill",
                    "amount": 1800,
                    "day_of_month": 14,
                    "category": "gas",
                },
            ],
        },
    )
    assert update.status_code == 200

    updated = client.get("/api/profile", headers=headers)
    assert updated.status_code == 200
    data = updated.json()
    assert data["monthly_salary"] == 120000
    assert data["min_safe_balance"] == 15000
    assert data["total_persistent_expenses"] == 26800
    assert data["projected_free_cashflow"] == 93200


def test_planning_rule_materialization_and_checklist(client):
    token, _ = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_plan = client.post(
        "/api/planning/plans",
        headers=headers,
        json={
            "title": "Monthly Stability Plan",
            "goal_type": "expense_control",
            "monthly_budget": 70000,
        },
    )
    assert create_plan.status_code == 201
    plan_id = create_plan.json()["id"]

    create_rule = client.post(
        "/api/planning/recurring-rules",
        headers=headers,
        json={
            "title": "Pay Rent",
            "category": "rent",
            "amount": 25000,
            "day_of_month": 10,
            "plan_id": plan_id,
            "autopay_enabled": True,
            "requires_approval": True,
            "reminder_days_before": 3,
        },
    )
    assert create_rule.status_code == 201
    rule_id = create_rule.json()["id"]

    materialize_once = client.post(
        f"/api/planning/recurring-rules/{rule_id}/materialize",
        headers=headers,
    )
    assert materialize_once.status_code == 201
    first_item_id = materialize_once.json()["id"]

    mark_complete = client.patch(
        f"/api/planning/checklist/{first_item_id}",
        headers=headers,
        json={"status": "completed"},
    )
    assert mark_complete.status_code == 200

    rule_after_complete = client.get("/api/planning/recurring-rules", headers=headers)
    assert rule_after_complete.status_code == 200
    updated_rule = next(
        item for item in rule_after_complete.json() if item["id"] == rule_id
    )
    assert updated_rule["trusted_recurring"] is True
    assert updated_rule["requires_approval"] is False

    scheduler_run = client.post(
        "/api/planning/scheduler/materialize-due",
        headers=headers,
        json={"until_days": 90},
    )
    assert scheduler_run.status_code == 200
    assert scheduler_run.json()["materialized_count"] >= 1

    checklist = client.get("/api/planning/checklist", headers=headers)
    assert checklist.status_code == 200
    items = checklist.json()
    assert len(items) >= 1
    assert any(item["status"] == "completed" for item in items)
    assert any(item["status"] == "pending" for item in items)


def test_schedule_from_text_creates_recurring_rule(client):
    token, _ = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/planning/schedule-from-text",
        headers=headers,
        json={
            "text": "Please pay my rent of 25000 every month on 10th and remind me",
            "autopay_enabled": True,
            "requires_approval": True,
        },
    )
    assert response.status_code == 201

    payload = response.json()
    assert payload["rule"]["category"] == "rent"
    assert payload["rule"]["day_of_month"] == 10
    assert payload["rule"]["amount"] == 25000
    assert payload["rule"]["reminder_days_before"] == 3
    assert payload["extracted"]["day_of_month"] == 10
