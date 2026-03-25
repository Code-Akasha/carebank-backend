"""WhatsApp bot service — sends and receives messages via Twilio API.

This module purely handles Twilio API I/O for WhatsApp. Business logic lives in the
coordinator graph (chat endpoint).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class WhatsAppBot:
    """Thin wrapper around the Twilio API for WhatsApp sendMessage helper."""

    def __init__(self, account_sid: str, auth_token: str, from_number: str) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self._base = (
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        )

    # ------------------------------------------------------------------
    # Message sending
    # ------------------------------------------------------------------

    async def send_message(self, to_number: str, text: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                # Twilio requires form data, not JSON
                data = {
                    "To": to_number,
                    "From": self.from_number,
                    "Body": text,
                }
                # Basic Auth with Twilio SID and Token
                resp = await client.post(
                    self._base,
                    data=data,
                    auth=(self.account_sid, self.auth_token),
                )
                return resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.error("WhatsApp sendMessage failed: %s", exc)
                return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Update parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def extract_message(form_data: dict[str, Any]) -> dict[str, Any] | None:
        """Return the form data if it contains a message body."""
        if "Body" in form_data:
            return form_data
        return None

    @staticmethod
    def get_user_phone(message: dict[str, Any]) -> str | None:
        # Twilio sends "From": "whatsapp:+1415..."
        return message.get("From")

    @staticmethod
    def get_text(message: dict[str, Any]) -> str:
        return message.get("Body", "").strip()

    @staticmethod
    def get_whatsapp_user_id(message: dict[str, Any]) -> str | None:
        """Return stable WhatsApp user_id string for mapping to CareBank users."""
        from_phone = message.get("From")
        if from_phone and from_phone.startswith("whatsapp:"):
            # strip 'whatsapp:' prefix to store cleanly
            plain_phone = from_phone[9:]
            return f"wa_{plain_phone}"
        return None
