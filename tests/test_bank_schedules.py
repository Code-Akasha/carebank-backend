from __future__ import annotations

import uuid

from app.services.banking_client import BankingClient


def _register_and_token(client):
    test_id = uuid.uuid4().hex[:8]
    email = f"bankschedule_{test_id}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Bank Schedule Test User",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["access_token"], payload["user_id"]


def test_bank_schedule_proxy_flow(client, monkeypatch):
    token, user_id = _register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    state: dict = {"schedule": None}

    async def fake_get_settlement_windows(self, uid, for_date=None):
        assert uid == user_id
        return {
            "country": "IN",
            "date": "2026-03-15",
            "rails": {
                "UPI": {"mode": "instant"},
                "NEFT": {"mode": "deferred"},
            },
        }

    async def fake_create_schedule(self, uid, payload):
        assert uid == user_id
        schedule = {
            "id": "sch_demo_001",
            "user_id": uid,
            "status": "active",
            "action_type": payload["action_type"],
            "amount": payload["amount"],
            "merchant": payload["merchant"],
            "category": payload["category"],
            "frequency": payload.get("frequency", "monthly"),
            "day_of_month": payload.get("day_of_month", 1),
            "next_run_date": "2026-03-20",
            "created_at": "2026-03-15T00:00:00Z",
            "last_run_at": None,
            "metadata": payload.get("metadata", {}),
            "payment_rail": payload.get("payment_rail"),
            "beneficiary_id": payload.get("beneficiary_id"),
            "beneficiary_verified": payload.get("beneficiary_verified", True),
            "description": payload.get("description"),
        }
        state["schedule"] = schedule
        return {"status": "created", "schedule": schedule}

    async def fake_get_schedules(self, uid, include_inactive=False):
        assert uid == user_id
        schedule = state.get("schedule")
        if not schedule:
            return []
        if include_inactive:
            return [schedule]
        if schedule.get("status") == "active":
            return [schedule]
        return []

    async def fake_run_schedule(self, uid, schedule_id, force=False):
        assert uid == user_id
        assert schedule_id == "sch_demo_001"
        assert force is True
        schedule = state["schedule"]
        schedule["last_run_at"] = "2026-03-15T00:10:00Z"
        schedule["next_run_date"] = "2026-04-20"
        return {
            "status": "executed",
            "schedule": schedule,
            "execution": {
                "transaction": {
                    "id": 999001,
                    "settlement_status": "cleared",
                }
            },
        }

    async def fake_cancel_schedule(self, uid, schedule_id):
        assert uid == user_id
        assert schedule_id == "sch_demo_001"
        schedule = state["schedule"]
        schedule["status"] = "cancelled"
        return {"status": "cancelled", "schedule": schedule}

    monkeypatch.setattr(
        BankingClient, "get_settlement_windows", fake_get_settlement_windows
    )
    monkeypatch.setattr(BankingClient, "create_schedule", fake_create_schedule)
    monkeypatch.setattr(BankingClient, "get_schedules", fake_get_schedules)
    monkeypatch.setattr(BankingClient, "run_schedule", fake_run_schedule)
    monkeypatch.setattr(BankingClient, "cancel_schedule", fake_cancel_schedule)

    windows = client.get("/api/bank-schedules/settlement-windows", headers=headers)
    assert windows.status_code == 200
    assert windows.json()["rails"]["UPI"]["mode"] == "instant"

    created = client.post(
        "/api/bank-schedules/",
        headers=headers,
        json={
            "action_type": "pay_bill",
            "amount": 1200,
            "merchant": "Internet Provider",
            "category": "utilities",
            "frequency": "monthly",
            "day_of_month": 20,
            "payment_rail": "UPI",
        },
    )
    assert created.status_code == 200
    assert created.json()["status"] == "created"

    listed = client.get("/api/bank-schedules/", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    ran = client.post(
        "/api/bank-schedules/sch_demo_001/run?force=true",
        headers=headers,
    )
    assert ran.status_code == 200
    assert ran.json()["status"] == "executed"
    assert ran.json()["execution"]["transaction"]["settlement_status"] == "cleared"

    cancelled = client.delete("/api/bank-schedules/sch_demo_001", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
