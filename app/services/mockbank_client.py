from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from threading import Lock
from typing import Any

import httpx
import jwt
import nest_asyncio

from app.core.config import get_settings

nest_asyncio.apply()

logger = logging.getLogger(__name__)


class MockBankClientError(RuntimeError):
    """Raised when MockBank cannot be reached."""


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    # Replace trailing Z
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    # Collapse duplicate timezone suffix e.g. "...+00:00+00:00"
    while value.count("+00:00") > 1:
        value = value.replace("+00:00+00:00", "+00:00")
    # Add UTC if no timezone present (check only in the time portion)
    sep_index = value.find("T")
    if sep_index == -1:
        sep_index = value.find(" ")
    time_and_tz = value[sep_index + 1 :] if sep_index != -1 else ""
    if "+" not in time_and_tz and "-" not in time_and_tz:
        value = f"{value}+00:00"
    return datetime.fromisoformat(value)


class MockBankClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.mock_bank_url.rstrip("/")
        self._secret = settings.mockbank_jwt_secret
        self._timeout = httpx.Timeout(10.0, connect=5.0)

    def _auth_headers(self, user_id: str | None) -> dict[str, str]:
        payload = {
            "user_id": user_id or "system",
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
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        headers = self._auth_headers(user_id)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.request(
                    method, url, params=params, json=json_body, headers=headers
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                logger.error("MockBank request failed: %s", exc)
                raise MockBankClientError(str(exc)) from exc
        return data

    async def get_transactions(
        self,
        user_id: str,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()
        if category:
            params["category"] = category

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

    async def get_accounts(self, user_id: str) -> list[dict[str, Any]]:
        data = await self._request("GET", "/accounts", user_id=user_id)
        return data

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


_client: MockBankClient | None = None
_client_lock = Lock()


def get_mockbank_client() -> MockBankClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = MockBankClient()
    return _client


def _run_sync(coro: Any) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def get_transactions_sync(
    *,
    user_id: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    client = get_mockbank_client()
    return _run_sync(
        client.get_transactions(
            user_id,
            start_date=start_date,
            end_date=end_date,
            category=category,
        )
    )


def get_balance_sync(user_id: str) -> dict[str, Any]:
    client = get_mockbank_client()
    return _run_sync(client.get_balance(user_id))


def get_products_sync(user_id: str | None = None) -> list[dict[str, Any]]:
    client = get_mockbank_client()
    return _run_sync(client.get_products(user_id))


def get_accounts_sync(user_id: str) -> list[dict[str, Any]]:
    client = get_mockbank_client()
    return _run_sync(client.get_accounts(user_id))


def get_providers_sync() -> list[dict[str, Any]]:
    client = get_mockbank_client()
    return _run_sync(client.get_providers())
