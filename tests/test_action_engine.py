from __future__ import annotations

import uuid

from app.services import action_policy
from app.services.banking_client import BankingClientError
from app.tools.registry import BankTransactionTool


def _register_and_token(client):
    test_id = uuid.uuid4().hex[:8]
    email = f"action_{test_id}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Action Engine Test User",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["access_token"], payload["user_id"]


def test_create_action_request_pending(client):
    token, _ = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/actions/requests",
        headers=headers,
        json={
            "action_type": "pay_rent",
            "action_payload": {"amount": 25000, "description": "March rent"},
            "idempotency_key": f"req-{uuid.uuid4().hex}",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["request"]["status"] == "pending"
    assert payload["execution"] is None


def test_action_request_idempotency_replay(client):
    token, _ = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    idem_key = f"idem-{uuid.uuid4().hex}"

    req_body = {
        "action_type": "pay_bill",
        "action_payload": {"amount": 3000, "description": "Electricity"},
        "idempotency_key": idem_key,
    }

    first = client.post("/api/actions/requests", headers=headers, json=req_body)
    assert first.status_code == 201
    first_payload = first.json()

    second = client.post("/api/actions/requests", headers=headers, json=req_body)
    assert second.status_code == 201
    second_payload = second.json()

    assert second_payload["request"]["id"] == first_payload["request"]["id"]
    assert second_payload["request"]["replayed"] is True


def test_action_request_idempotency_conflict(client):
    token, _ = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    idem_key = f"idem-{uuid.uuid4().hex}"

    first = client.post(
        "/api/actions/requests",
        headers=headers,
        json={
            "action_type": "pay_bill",
            "action_payload": {"amount": 3000},
            "idempotency_key": idem_key,
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/api/actions/requests",
        headers=headers,
        json={
            "action_type": "pay_bill",
            "action_payload": {"amount": 4500},
            "idempotency_key": idem_key,
        },
    )
    assert second.status_code == 409


def test_action_policy_uses_mockbank_caps(client, monkeypatch):
    token, _ = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    action_policy._policy_cache.clear()

    def fake_get_action_policy_sync(action_type, user_id=None):
        assert action_type == "pay_bill"
        return {
            "country": "IN",
            "policy_version": "test",
            "action_type": "pay_bill",
            "requires_approval": True,
            "max_amount": 1200.0,
            "allow_trusted_recurring_bypass": True,
            "default_payment_rail": "UPI",
            "regulatory_context": ["test"],
        }

    monkeypatch.setattr(
        action_policy,
        "get_action_policy_sync",
        fake_get_action_policy_sync,
    )

    response = client.post(
        "/api/actions/requests",
        headers=headers,
        json={
            "action_type": "pay_bill",
            "action_payload": {"amount": 1500, "description": "Electricity"},
            "idempotency_key": f"policy-{uuid.uuid4().hex}",
        },
    )
    assert response.status_code == 400
    assert "1200.0" in response.json()["detail"]


def test_action_policy_fallback_when_mockbank_unavailable(client, monkeypatch):
    token, _ = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    action_policy._policy_cache.clear()

    def fake_get_action_policy_sync(_action_type, user_id=None):
        raise BankingClientError("mockbank-down", status_code=503)

    monkeypatch.setattr(
        action_policy,
        "get_action_policy_sync",
        fake_get_action_policy_sync,
    )

    response = client.post(
        "/api/actions/requests",
        headers=headers,
        json={
            "action_type": "pay_gas",
            "action_payload": {"amount": 12000, "description": "Gas refill"},
            "idempotency_key": f"fallback-{uuid.uuid4().hex}",
        },
    )
    assert response.status_code == 400
    assert "10000.0" in response.json()["detail"]


def test_approve_action_executes_tool(client, monkeypatch):
    token, _ = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    def fake_execute(self, user_id, action_type, payload):
        return {
            "status": "ok",
            "action_type": action_type,
            "user_id": user_id,
            "payload": payload,
            "mocked": True,
        }

    monkeypatch.setattr(BankTransactionTool, "execute", fake_execute)

    created = client.post(
        "/api/actions/requests",
        headers=headers,
        json={
            "action_type": "pay_rent",
            "action_payload": {"amount": 27000},
            "idempotency_key": f"exec-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201
    request_id = created.json()["request"]["id"]

    approved = client.post(
        f"/api/actions/requests/{request_id}/approve",
        headers=headers,
        json={"reason": "Looks good"},
    )
    assert approved.status_code == 200
    payload = approved.json()
    assert payload["request"]["status"] == "approved"
    assert payload["execution"]["status"] == "success"
    assert payload["execution"]["result_payload"]["mocked"] is True


def test_trusted_recurring_auto_executes_without_manual_approval(client, monkeypatch):
    token, _ = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    def fake_execute(self, user_id, action_type, payload):
        return {"status": "ok", "mocked": True, "action_type": action_type}

    monkeypatch.setattr(BankTransactionTool, "execute", fake_execute)

    plan = client.post(
        "/api/planning/plans",
        headers=headers,
        json={"title": "Rent Plan", "goal_type": "expense_control"},
    )
    assert plan.status_code == 201
    plan_id = plan.json()["id"]

    rule = client.post(
        "/api/planning/recurring-rules",
        headers=headers,
        json={
            "title": "Pay Rent",
            "category": "rent",
            "amount": 25000,
            "day_of_month": 10,
            "plan_id": plan_id,
            "autopay_enabled": True,
            "requires_approval": False,
        },
    )
    assert rule.status_code == 201
    rule_id = rule.json()["id"]

    promoted = client.patch(
        f"/api/planning/recurring-rules/{rule_id}",
        headers=headers,
        json={"trusted_recurring": True, "requires_approval": False},
    )
    assert promoted.status_code == 200

    created = client.post(
        "/api/actions/requests",
        headers=headers,
        json={
            "action_type": "pay_rent",
            "action_payload": {"amount": 25000, "recurring_rule_id": rule_id},
            "idempotency_key": f"auto-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["request"]["status"] == "approved"
    assert payload["execution"] is not None
    assert payload["execution"]["status"] == "success"
