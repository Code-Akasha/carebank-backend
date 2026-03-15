from __future__ import annotations

import uuid

from app.services.banking_client import BankingClient


def _register_and_token(client):
    test_id = uuid.uuid4().hex[:8]
    email = f"beneficiary_{test_id}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Beneficiary Test User",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["access_token"], payload["user_id"]


def test_beneficiary_proxy_crud(client, monkeypatch):
    token, user_id = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    state = {
        "beneficiary": {
            "id": "ben_demo_001",
            "user_id": user_id,
            "name": "Landlord",
            "payment_rail": "NEFT",
            "account_number": "555001234567",
            "ifsc": "CARE0000456",
            "upi_handle": None,
            "nickname": "Rent",
            "status": "pending",
            "created_at": "2026-03-14T00:00:00Z",
            "verified_at": None,
            "cooldown_expires_at": None,
        }
    }

    async def fake_get_beneficiaries(self, uid):
        assert uid == user_id
        return [state["beneficiary"]]

    async def fake_create_beneficiary(self, uid, payload):
        assert uid == user_id
        state["beneficiary"] = {
            **state["beneficiary"],
            "name": payload["name"],
            "payment_rail": payload["payment_rail"],
            "nickname": payload.get("nickname"),
        }
        return {
            "status": "created",
            "beneficiary": state["beneficiary"],
        }

    async def fake_verify_beneficiary(self, uid, beneficiary_id):
        assert uid == user_id
        assert beneficiary_id == state["beneficiary"]["id"]
        state["beneficiary"]["status"] = "verified"
        state["beneficiary"]["verified_at"] = "2026-03-14T00:10:00Z"
        state["beneficiary"]["cooldown_expires_at"] = "2026-03-15T00:10:00Z"
        return {
            "status": "verified",
            "beneficiary": state["beneficiary"],
        }

    monkeypatch.setattr(BankingClient, "get_beneficiaries", fake_get_beneficiaries)
    monkeypatch.setattr(BankingClient, "create_beneficiary", fake_create_beneficiary)
    monkeypatch.setattr(BankingClient, "verify_beneficiary", fake_verify_beneficiary)

    create_response = client.post(
        "/api/beneficiaries/",
        headers=headers,
        json={
            "name": "Landlord",
            "payment_rail": "NEFT",
            "account_number": "555001234567",
            "ifsc": "CARE0000456",
            "nickname": "Rent",
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "created"

    list_response = client.get("/api/beneficiaries/", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["status"] == "pending"

    verify_response = client.put(
        f"/api/beneficiaries/{state['beneficiary']['id']}/verify",
        headers=headers,
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["status"] == "verified"
    assert verify_response.json()["beneficiary"]["status"] == "verified"
