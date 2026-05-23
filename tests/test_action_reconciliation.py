from __future__ import annotations

import uuid

from app.services.banking_client import BankingClient
from app.tools.registry import BankTransactionTool


def _register_and_token(client):
    test_id = uuid.uuid4().hex[:8]
    email = f"reconcile_{test_id}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Reconcile Test User",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["access_token"], payload["user_id"]


def test_reconcile_updates_execution_to_rollback(client, monkeypatch):
    token, user_id = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    transaction_id = 998001

    def fake_execute(self, user_id, action_type, payload):
        return {
            "status": "ok",
            "action_type": action_type,
            "upstream_response": {
                "transaction": {
                    "id": transaction_id,
                    "status": "success",
                },
            },
        }

    async def fake_get_transaction_lifecycle(self, uid, txn_id):
        assert uid == user_id
        assert txn_id == transaction_id
        return {
            "transaction_id": txn_id,
            "user_id": uid,
            "status": "reversed",
            "lifecycle": [
                {
                    "event_id": "evt_test_1",
                    "status": "success",
                    "timestamp": "2026-03-15T00:00:00Z",
                },
                {
                    "event_id": "evt_test_2",
                    "status": "reversed",
                    "reason": "Dispute rollback",
                    "timestamp": "2026-03-15T00:10:00Z",
                },
            ],
        }

    monkeypatch.setattr(BankTransactionTool, "execute", fake_execute)
    monkeypatch.setattr(
        BankingClient,
        "get_transaction_lifecycle",
        fake_get_transaction_lifecycle,
    )

    created = client.post(
        "/api/actions/requests",
        headers=headers,
        json={
            "action_type": "pay_bill",
            "action_payload": {"amount": 2500, "description": "internet bill"},
            "idempotency_key": f"reconcile-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201

    request_id = created.json()["request"]["id"]
    approved = client.post(
        f"/api/actions/requests/{request_id}/approve",
        headers=headers,
        json={"reason": "approve for reconcile"},
    )
    assert approved.status_code == 200
    execution_id = approved.json()["execution"]["id"]
    assert approved.json()["execution"]["status"] == "success"

    reconcile = client.post(
        "/api/actions/executions/reconcile",
        headers=headers,
        json={"execution_id": execution_id},
    )
    assert reconcile.status_code == 200
    reconcile_payload = reconcile.json()
    assert reconcile_payload["updated_count"] == 1

    refreshed = client.get(f"/api/actions/executions/{execution_id}", headers=headers)
    assert refreshed.status_code == 200
    refreshed_payload = refreshed.json()
    assert refreshed_payload["status"] == "rollback"
    assert (
        refreshed_payload["result_payload"]["mockbank_reconciliation"]["bank_status"]
        == "reversed"
    )


def test_reconcile_skips_missing_transaction_id(client, monkeypatch):
    token, _ = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    def fake_execute(self, user_id, action_type, payload):
        return {
            "status": "ok",
            "action_type": action_type,
            "upstream_response": {
                "transaction": {
                    "status": "success",
                },
            },
        }

    monkeypatch.setattr(BankTransactionTool, "execute", fake_execute)

    created = client.post(
        "/api/actions/requests",
        headers=headers,
        json={
            "action_type": "pay_bill",
            "action_payload": {"amount": 1900, "description": "mobile bill"},
            "idempotency_key": f"reconcile-skip-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201

    request_id = created.json()["request"]["id"]
    approved = client.post(
        f"/api/actions/requests/{request_id}/approve",
        headers=headers,
        json={"reason": "approve for reconcile skip"},
    )
    assert approved.status_code == 200
    execution_id = approved.json()["execution"]["id"]

    reconcile = client.post(
        "/api/actions/executions/reconcile",
        headers=headers,
        json={"execution_id": execution_id},
    )
    assert reconcile.status_code == 200
    payload = reconcile.json()
    assert payload["updated_count"] == 0
    assert payload["results"][0]["status"] == "skipped"
    assert payload["results"][0]["reason"] == "transaction_id_missing"
