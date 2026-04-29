from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from threading import Lock
from typing import Any

import httpx
import jwt

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class BankingClientError(RuntimeError):
    """Raised when the Banking API cannot be reached."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    while value.count("+00:00") > 1:
        value = value.replace("+00:00+00:00", "+00:00")
    sep_index = value.find("T")
    if sep_index == -1:
        sep_index = value.find(" ")
    time_and_tz = value[sep_index + 1 :] if sep_index != -1 else ""
    if "+" not in time_and_tz and "-" not in time_and_tz:
        value = f"{value}+00:00"
    return datetime.fromisoformat(value)


class BankingClient:
    """HTTP client for the connected Banking API.

    This client is API-agnostic — it communicates with whatever banking
    service is configured via ``BANKING_API_URL`` and ``BANKING_API_SECRET``.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.banking_api_url.rstrip("/")
        self._secret = settings.banking_api_secret
        self._timeout = httpx.Timeout(10.0, connect=5.0)

    def _auth_headers(
        self, user_id: str | None, *, role: str = "user"
    ) -> dict[str, str]:
        payload = {
            "user_id": user_id or "system",
            "role": role,
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        }
        token = jwt.encode(payload, self._secret, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        user_id: str | None = None,
        role: str = "user",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        headers = self._auth_headers(user_id, role=role)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.request(
                    method, url, params=params, json=json_body, headers=headers
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                detail = exc.response.text
                logger.error(
                    "Banking API status error %s for %s %s: %s",
                    status_code,
                    method,
                    url,
                    detail,
                )
                raise BankingClientError(
                    f"status={status_code}: {detail}", status_code=status_code
                ) from exc
            except httpx.HTTPError as exc:
                logger.error("Banking API request failed: %s", exc)
                raise BankingClientError(str(exc)) from exc
        return data

    # ── User-scoped endpoints ────────────────────────────────────────

    async def get_transactions(
        self,
        user_id: str,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        category: str | None = None,
        settlement_status: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()
        if category:
            params["category"] = category
        if settlement_status:
            params["settlement_status"] = settlement_status

        data = await self._request(
            "GET", "/transactions", user_id=user_id, params=params
        )
        return [self._normalize_transaction(item) for item in data]

    async def get_balance(self, user_id: str) -> dict[str, Any]:
        data = await self._request("GET", "/balances", user_id=user_id)
        parsed = data.copy()
        parsed["last_updated"] = (
            _parse_iso(parsed.get("last_updated")) or datetime.utcnow()
        )
        return parsed

    async def get_products(self, user_id: str | None = None) -> list[dict[str, Any]]:
        data = await self._request("GET", "/products", user_id=user_id or "system")
        return data

    async def get_bank_plans(self, user_id: str | None = None) -> dict[str, Any]:
        data = await self._request("GET", "/banking/plans", user_id=user_id or "system")
        return data

    async def get_banking_policies(self, user_id: str | None = None) -> dict[str, Any]:
        data = await self._request(
            "GET", "/banking/policies", user_id=user_id or "system"
        )
        return data

    async def get_action_policy(
        self, action_type: str, user_id: str | None = None
    ) -> dict[str, Any]:
        data = await self._request(
            "GET",
            f"/banking/policies/actions/{action_type}",
            user_id=user_id or "system",
        )
        return data

    async def get_accounts(self, user_id: str) -> list[dict[str, Any]]:
        data = await self._request("GET", "/accounts", user_id=user_id)
        return data

    async def create_account(
        self,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        body = {
            "user_id": user_id,
            **payload,
        }
        return await self._request(
            "POST",
            "/accounts",
            user_id=user_id,
            json_body=body,
        )

    async def delete_account(
        self,
        user_id: str,
        account_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            f"/accounts/{account_id}",
            user_id=user_id,
        )

    async def get_beneficiaries(self, user_id: str) -> list[dict[str, Any]]:
        data = await self._request("GET", "/beneficiaries", user_id=user_id)
        if isinstance(data, list):
            return data
        return []

    async def create_beneficiary(
        self, user_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "POST", "/beneficiaries", user_id=user_id, json_body=payload
        )

    async def verify_beneficiary(
        self,
        user_id: str,
        beneficiary_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"/beneficiaries/{beneficiary_id}/verify",
            user_id=user_id,
        )

    async def get_settlement_windows(
        self,
        user_id: str,
        *,
        for_date: date | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] | None = None
        if for_date:
            params = {"for_date": for_date.isoformat()}
        return await self._request(
            "GET",
            "/settlement-windows",
            user_id=user_id,
            params=params,
        )

    async def get_schedules(
        self,
        user_id: str,
        *,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "/schedules",
            user_id=user_id,
            params={"include_inactive": str(include_inactive).lower()},
        )
        if isinstance(data, list):
            return data
        return []

    async def create_schedule(
        self,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/schedules",
            user_id=user_id,
            json_body=payload,
        )

    async def run_schedule(
        self,
        user_id: str,
        schedule_id: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/schedules/{schedule_id}/run",
            user_id=user_id,
            params={"force": str(force).lower()},
        )

    async def cancel_schedule(
        self,
        user_id: str,
        schedule_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            f"/schedules/{schedule_id}",
            user_id=user_id,
        )

    async def get_transaction_lifecycle(
        self,
        user_id: str,
        transaction_id: int,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/transactions/{transaction_id}/lifecycle",
            user_id=user_id,
        )

    async def get_providers(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/providers", user_id="system")
        return data

    async def trigger_transaction(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_id = payload.get("user_id")
        if not user_id:
            raise ValueError("user_id required to trigger transaction")
        return await self._request(
            "POST", "/transactions/trigger", user_id=user_id, json_body=payload
        )

    # ── Admin-scoped endpoints ───────────────────────────────────────

    async def create_profile(
        self, user_id: str, balance: float = 25000.0
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/profiles",
            user_id="admin",
            role="admin",
            json_body={
                "user_id": user_id,
                "current_balance": balance,
            },
        )

    async def toggle_simulation(self, enabled: bool) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/admin/simulation/toggle",
            user_id="admin",
            role="admin",
            json_body={"enabled": enabled},
        )

    async def get_simulation_status(self) -> dict[str, Any]:
        return await self._request(
            "GET", "/admin/simulation/status", user_id="admin", role="admin"
        )

    async def trigger_scenario(
        self, user_id: str, scenario_type: str
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/admin/scenario",
            user_id="admin",
            role="admin",
            json_body={"user_id": user_id, "scenario_type": scenario_type},
        )

    async def get_admin_users(
        self, *, page: int = 1, per_page: int = 200
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "/admin/users",
            user_id="admin",
            role="admin",
            params={"page": page, "per_page": per_page},
        )
        if isinstance(data, dict):
            return data.get("users", []) or []
        return []

    async def get_webhook_dead_letters(
        self, *, status_filter: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] | None = None
        if status_filter:
            params = {"status_filter": status_filter}
        return await self._request(
            "GET",
            "/admin/webhooks/dead-letter",
            user_id="admin",
            role="admin",
            params=params,
        )

    async def replay_webhook_dead_letter(
        self, dead_letter_id: str, *, webhook_url: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] | None = None
        if webhook_url:
            body = {"webhook_url": webhook_url}
        return await self._request(
            "POST",
            f"/admin/webhooks/dead-letter/{dead_letter_id}/replay",
            user_id="admin",
            role="admin",
            json_body=body,
        )

    @staticmethod
    def _normalize_transaction(data: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "id": data.get("id"),
            "user_id": data.get("user_id"),
            "amount": float(data.get("amount", 0.0)),
            "merchant": data.get("merchant"),
            "category": data.get("category", "unknown"),
            "description": data.get("description"),
        }
        normalized["date"] = _parse_iso(data.get("date")) or datetime.utcnow()
        return normalized


_client: BankingClient | None = None
_client_lock = Lock()


def get_banking_client() -> BankingClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = BankingClient()
    return _client


def _run_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # If we're already inside an event loop, execute in a dedicated thread.
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


def get_transactions_sync(
    *,
    user_id: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    category: str | None = None,
    settlement_status: str | None = None,
) -> list[dict[str, Any]]:
    client = get_banking_client()
    return _run_sync(
        client.get_transactions(
            user_id,
            start_date=start_date,
            end_date=end_date,
            category=category,
            settlement_status=settlement_status,
        )
    )


def get_balance_sync(user_id: str) -> dict[str, Any]:
    client = get_banking_client()
    return _run_sync(client.get_balance(user_id))


def get_products_sync(user_id: str | None = None) -> list[dict[str, Any]]:
    client = get_banking_client()
    return _run_sync(client.get_products(user_id))


def get_bank_plans_sync(user_id: str | None = None) -> dict[str, Any]:
    client = get_banking_client()
    return _run_sync(client.get_bank_plans(user_id))


def get_banking_policies_sync(user_id: str | None = None) -> dict[str, Any]:
    client = get_banking_client()
    return _run_sync(client.get_banking_policies(user_id))


def get_action_policy_sync(
    action_type: str, user_id: str | None = None
) -> dict[str, Any]:
    client = get_banking_client()
    return _run_sync(client.get_action_policy(action_type, user_id=user_id))


def get_accounts_sync(user_id: str) -> list[dict[str, Any]]:
    client = get_banking_client()
    return _run_sync(client.get_accounts(user_id))


def get_beneficiaries_sync(user_id: str) -> list[dict[str, Any]]:
    client = get_banking_client()
    return _run_sync(client.get_beneficiaries(user_id))


def get_providers_sync() -> list[dict[str, Any]]:
    client = get_banking_client()
    return _run_sync(client.get_providers())


def trigger_transaction_sync(payload: dict[str, Any]) -> dict[str, Any]:
    client = get_banking_client()
    return _run_sync(client.trigger_transaction(payload))


def get_transaction_lifecycle_sync(user_id: str, transaction_id: int) -> dict[str, Any]:
    client = get_banking_client()
    return _run_sync(client.get_transaction_lifecycle(user_id, transaction_id))
