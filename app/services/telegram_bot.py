"""Telegram bot service — sends and receives messages via the Bot API.

This module purely handles Telegram API I/O.  Business logic lives in the
coordinator graph (chat endpoint).  All requests go through the same
/api/chat endpoint so session state, health scores, and all agents work
identically for bot users.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramBot:
    """Thin wrapper around the Telegram Bot API for send/set-webhook helpers."""

    def __init__(self, token: str) -> None:
        self.token = token
        self._base = f"https://api.telegram.org/bot{token}"

    # ------------------------------------------------------------------
    # Webhook management
    # ------------------------------------------------------------------

    async def set_webhook(
        self,
        url: str,
        *,
        secret_token: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "url": url,
            "allowed_updates": ["message", "callback_query"],
        }
        if secret_token:
            payload["secret_token"] = secret_token

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self._base}/setWebhook",
                json=payload,
            )
            return resp.json()

    async def delete_webhook(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{self._base}/deleteWebhook")
            return resp.json()

    # ------------------------------------------------------------------
    # Message sending
    # ------------------------------------------------------------------

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_markup: dict | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.post(f"{self._base}/sendMessage", json=payload)
                return resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.error("Telegram sendMessage failed: %s", exc)
                return {"ok": False, "error": str(exc)}

    async def send_typing(self, chat_id: int | str) -> None:
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                await client.post(
                    f"{self._base}/sendChatAction",
                    json={"chat_id": chat_id, "action": "typing"},
                )
            except Exception:  # noqa: BLE001
                pass  # typing indicator failure is non-critical

    # ------------------------------------------------------------------
    # Update parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
        """Return the message dict regardless of update type."""
        if "message" in update:
            return update["message"]
        if "edited_message" in update:
            return update["edited_message"]
        return None

    @staticmethod
    def get_chat_id(message: dict[str, Any]) -> int | None:
        return message.get("chat", {}).get("id")

    @staticmethod
    def get_text(message: dict[str, Any]) -> str:
        return message.get("text", "").strip()

    @staticmethod
    def get_telegram_user_id(message: dict[str, Any]) -> str | None:
        """Return stable Telegram user_id string for mapping to CareBank users."""
        from_info = message.get("from", {})
        uid = from_info.get("id")
        return f"tg_{uid}" if uid else None
