from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

from app.core.config import get_settings
from app.tools.registry import BankTransactionTool


def _register_and_token(client):
    test_id = uuid.uuid4().hex[:8]
    email = f"webhook_{test_id}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Webhook Test User",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["access_token"], payload["user_id"]


def _signed_payload_headers(payload: dict) -> tuple[str, dict[str, str]]:
    settings = get_settings()
    timestamp = str(int(time.time()))
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    signed_payload = f"{timestamp}.{body}"
    signature = hmac.new(
        settings.mockbank_webhook_secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return body, {
        "Content-Type": "application/json",
        "X-CareBank-Timestamp": timestamp,
        "X-CareBank-Signature": signature,
    }


def test_mockbank_webhook_rejects_invalid_signature(client):
    payload = {
        "event_id": "evt-invalid-signature",
        "event_type": "transaction.lifecycle.updated",
        "transaction_id": 1,
        "status": "success",
    }
    body = json.dumps(payload)
    response = client.post(
        "/api/actions/webhooks/mockbank",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-CareBank-Timestamp": str(int(time.time())),
            "X-CareBank-Signature": "invalid-signature",
        },
    )
    assert response.status_code == 401


def test_mockbank_webhook_moves_execution_to_rollback(client, monkeypatch):
    token, user_id = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    def fake_execute(self, user_id, action_type, payload):
        return {
            "status": "ok",
            "action_type": action_type,
            "user_id": user_id,
            "payload": payload,
        }

    monkeypatch.setattr(BankTransactionTool, "execute", fake_execute)

    idem_key = f"wh-{uuid.uuid4().hex}"
    created = client.post(
        "/api/actions/requests",
        headers=headers,
        json={
            "action_type": "pay_bill",
            "action_payload": {"amount": 2500, "description": "internet bill"},
            "idempotency_key": idem_key,
        },
    )
    assert created.status_code == 201

    request_id = created.json()["request"]["id"]
    approved = client.post(
        f"/api/actions/requests/{request_id}/approve",
        headers=headers,
        json={"reason": "approve for webhook test"},
    )
    assert approved.status_code == 200
    execution_id = approved.json()["execution"]["id"]
    assert approved.json()["execution"]["status"] == "success"

    webhook_payload = {
        "event_id": f"evt-{uuid.uuid4().hex}",
        "event_type": "transaction.lifecycle.updated",
        "transaction_id": 998877,
        "user_id": user_id,
        "status": "reversed",
        "reason": "Bank reversal due to dispute",
        "idempotency_key": idem_key,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metadata": {
            "execution_id": execution_id,
            "approval_request_id": request_id,
            "reversal_transaction_id": 998878,
        },
    }
    body, webhook_headers = _signed_payload_headers(webhook_payload)

    webhook_response = client.post(
        "/api/actions/webhooks/mockbank",
        data=body,
        headers=webhook_headers,
    )
    assert webhook_response.status_code == 202
    assert webhook_response.json()["execution_status"] == "rollback"

    refreshed_execution = client.get(
        f"/api/actions/executions/{execution_id}",
        headers=headers,
    )
    assert refreshed_execution.status_code == 200
    payload = refreshed_execution.json()
    assert payload["status"] == "rollback"
    assert payload["result_payload"]["mockbank_lifecycle"]["status"] == "reversed"
