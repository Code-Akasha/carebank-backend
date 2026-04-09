from __future__ import annotations

import json
import uuid

import httpx

BACKEND_URL = "http://127.0.0.1:8000"


def excerpt(payload: object, max_len: int = 180) -> str:
    text = json.dumps(payload, default=str)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def print_step(name: str, status: int, body: object) -> None:
    print(f"{name}: {status} | {excerpt(body)}")


def main() -> int:
    email = f"live_{uuid.uuid4().hex[:8]}@example.com"
    password = "P@ssw0rd123"

    with httpx.Client(base_url=BACKEND_URL, timeout=20.0) as client:
        register = client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "full_name": "Live Verify"},
        )
        print_step("register", register.status_code, register.json())

        login = client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        print_step("login", login.status_code, login.json())

        if login.status_code != 200:
            return 1

        token = login.json().get("access_token")
        if not token:
            print("fatal: missing access_token")
            return 1

        headers = {"Authorization": f"Bearer {token}"}

        me = client.get("/api/auth/me", headers=headers)
        print_step("me", me.status_code, me.json())

        create_account = client.post(
            "/api/accounts/",
            json={
                "name": "Live Savings",
                "account_type": "savings",
                "initial_deposit": 1200,
            },
            headers=headers,
        )
        print_step("create_account", create_account.status_code, create_account.json())

        list_accounts = client.get("/api/accounts/", headers=headers)
        list_accounts_body = list_accounts.json()
        list_count = len(list_accounts_body) if isinstance(list_accounts_body, list) else -1
        print(
            f"list_accounts: {list_accounts.status_code} | "
            f"count={list_count} excerpt={excerpt(list_accounts_body)}"
        )

        trigger_tx = client.post(
            "/api/transactions/trigger",
            json={"amount": -250, "merchant": "E2E Test", "category": "manual"},
            headers=headers,
        )
        print_step("trigger_transaction", trigger_tx.status_code, trigger_tx.json())

        chat = client.post(
            "/api/chat",
            json={"message": "show my balance"},
            headers=headers,
        )
        print_step("chat", chat.status_code, chat.json())

        checks = {
            "profile": client.get("/api/profile", headers=headers),
            "planning_plans": client.get("/api/planning/plans", headers=headers),
            "actions_requests": client.get("/api/actions/requests", headers=headers),
            "beneficiaries": client.get("/api/beneficiaries/", headers=headers),
            "bank_schedules": client.get("/api/bank-schedules/", headers=headers),
        }
        for name, response in checks.items():
            body: object
            try:
                body = response.json()
            except Exception:
                body = response.text
            print_step(name, response.status_code, body)

        statuses = [
            register.status_code,
            login.status_code,
            me.status_code,
            create_account.status_code,
            list_accounts.status_code,
            trigger_tx.status_code,
            chat.status_code,
            checks["profile"].status_code,
            checks["planning_plans"].status_code,
            checks["actions_requests"].status_code,
            checks["beneficiaries"].status_code,
            checks["bank_schedules"].status_code,
        ]

    has_failure = any(status >= 400 for status in statuses)
    print("overall:", "FAIL" if has_failure else "PASS")
    return 1 if has_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
