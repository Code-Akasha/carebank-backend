from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.services.banking_client as bc
from app.main import app


class DummyBankingClient:
    def __init__(self) -> None:
        self.accounts: dict[str, list[dict]] = {}
        self.transactions: dict[str, list[dict]] = {}

    async def create_profile(self, user_id: str, balance: float = 25000.0) -> dict:
        self.accounts.setdefault(
            user_id,
            [
                {
                    "account_id": f"acct_{user_id[-6:]}",
                    "user_id": user_id,
                    "provider_id": "carebank_retail",
                    "name": "Primary Account",
                    "account_type": "savings",
                    "mask": "1234",
                    "currency": "INR",
                    "institution": "CareBank",
                    "current_balance": balance,
                    "available_balance": balance,
                    "status": "active",
                    "last_statement_date": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )
        self.transactions.setdefault(user_id, [])
        return {"status": "created"}

    async def get_accounts(self, user_id: str) -> list[dict]:
        return self.accounts.setdefault(user_id, [])

    async def create_account(self, user_id: str, payload: dict) -> dict:
        account_id = f"acct_{uuid.uuid4().hex[:10]}"
        account = {
            "account_id": account_id,
            "user_id": user_id,
            "provider_id": payload.get("provider_id", "carebank_retail"),
            "name": payload.get("name", "New Account"),
            "account_type": payload.get("account_type", "savings"),
            "mask": account_id[-4:],
            "currency": payload.get("currency", "INR"),
            "institution": "CareBank",
            "current_balance": float(payload.get("initial_deposit", 0.0)),
            "available_balance": float(payload.get("initial_deposit", 0.0)),
            "status": "active",
            "last_statement_date": datetime.now(timezone.utc).isoformat(),
        }
        self.accounts.setdefault(user_id, []).append(account)
        return {"status": "created", "account": account}

    async def trigger_transaction(self, payload: dict) -> dict:
        user_id = payload["user_id"]
        tx = {
            "id": len(self.transactions.setdefault(user_id, [])) + 1,
            "user_id": user_id,
            "amount": float(payload.get("amount", 0.0)),
            "merchant": payload.get("merchant", "Manual Transaction"),
            "category": payload.get("category", "Manual"),
            "description": payload.get("description", ""),
            "date": datetime.now(timezone.utc).isoformat(),
        }
        self.transactions[user_id].insert(0, tx)
        return {"status": "success", "transaction": tx}

    async def get_transactions(self, user_id: str, **kwargs) -> list[dict]:
        return self.transactions.setdefault(user_id, [])

    async def get_balance(self, user_id: str) -> dict:
        total = sum(
            float(account.get("available_balance", 0.0))
            for account in self.accounts.setdefault(user_id, [])
        )
        return {
            "current_balance": total,
            "available_balance": total,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    async def get_beneficiaries(self, user_id: str) -> list[dict]:
        return []

    async def get_products(self, user_id: str | None = None) -> list[dict]:
        return []


bc._client = DummyBankingClient()

client = TestClient(app)

email = f"smoke_{uuid.uuid4().hex[:8]}@example.com"
password = "P@ssw0rd123"

register_resp = client.post(
    "/api/auth/register",
    json={"email": email, "password": password, "full_name": "Smoke User"},
)
print("register", register_resp.status_code)
assert register_resp.status_code in (200, 201)

login_resp = client.post(
    "/api/auth/login",
    json={"email": email, "password": password},
)
print("login", login_resp.status_code)
assert login_resp.status_code == 200

token = login_resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

me_resp = client.get("/api/auth/me", headers=headers)
print("auth_me", me_resp.status_code)
assert me_resp.status_code == 200

create_account_resp = client.post(
    "/api/accounts/",
    json={
        "name": "Savings Vault",
        "account_type": "savings",
        "initial_deposit": 1500,
    },
    headers=headers,
)
print("create_account", create_account_resp.status_code)
assert create_account_resp.status_code == 200

list_accounts_resp = client.get("/api/accounts/", headers=headers)
print(
    "list_accounts",
    list_accounts_resp.status_code,
    "count",
    len(list_accounts_resp.json()),
)
assert list_accounts_resp.status_code == 200
assert len(list_accounts_resp.json()) >= 1

transaction_resp = client.post(
    "/api/transactions/trigger",
    json={"amount": -250, "merchant": "Smoke Test", "category": "manual"},
    headers=headers,
)
print("trigger_tx", transaction_resp.status_code)
assert transaction_resp.status_code == 200

chat_resp = client.post(
    "/api/chat", json={"message": "show my balance"}, headers=headers
)
print("chat", chat_resp.status_code)
assert chat_resp.status_code in (200, 201)

print("smoke_status PASS")
