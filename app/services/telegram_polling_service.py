from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TelegramPollingService:
    """Long-poll updates from Telegram and forward to local webhook handler."""

    def __init__(
        self,
        *,
        bot_token: str,
        forward_url: str,
        webhook_secret: str = "",
        request_timeout_seconds: int = 35,
    ) -> None:
        self.bot_token = bot_token
        self.forward_url = forward_url
        self.webhook_secret = webhook_secret
        self.request_timeout_seconds = request_timeout_seconds
        self._base = f"https://api.telegram.org/bot{bot_token}"
        self._offset: int | None = None

    async def delete_webhook(self) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{self._base}/deleteWebhook")
            data = resp.json()
            if not data.get("ok"):
                logger.warning("deleteWebhook failed: %s", data)

    async def run_forever(self) -> None:
        await self.delete_webhook()
        logger.info(
            "Telegram polling started. Forwarding updates to %s", self.forward_url
        )

        async with httpx.AsyncClient(timeout=self.request_timeout_seconds) as client:
            while True:
                try:
                    params: dict[str, Any] = {
                        "timeout": 30,
                        "allowed_updates": ["message", "callback_query"],
                    }
                    if self._offset is not None:
                        params["offset"] = self._offset

                    resp = await client.get(f"{self._base}/getUpdates", params=params)
                    payload = resp.json()
                    if not payload.get("ok"):
                        logger.warning("getUpdates failed: %s", payload)
                        await asyncio.sleep(2)
                        continue

                    updates = payload.get("result", [])
                    for update in updates:
                        update_id = update.get("update_id")
                        if isinstance(update_id, int):
                            self._offset = update_id + 1

                        try:
                            headers = {}
                            if self.webhook_secret:
                                headers["X-Telegram-Bot-Api-Secret-Token"] = (
                                    self.webhook_secret
                                )
                            await client.post(
                                self.forward_url,
                                json=update,
                                headers=headers,
                                timeout=20,
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.error("Forward to local webhook failed: %s", exc)

                except Exception as exc:  # noqa: BLE001
                    logger.error("Polling loop error: %s", exc)
                    await asyncio.sleep(2)
