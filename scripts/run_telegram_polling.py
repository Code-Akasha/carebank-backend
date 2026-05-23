from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _read_env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


async def _main() -> None:
    from app.services.telegram_polling_service import TelegramPollingService

    token = _read_env("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    forward_url = _read_env(
        "TELEGRAM_POLL_FORWARD_URL", "http://127.0.0.1:8000/bot/telegram/webhook",
    )
    webhook_secret = _read_env("TELEGRAM_WEBHOOK_SECRET")

    service = TelegramPollingService(
        bot_token=token,
        forward_url=forward_url,
        webhook_secret=webhook_secret,
    )
    await service.run_forever()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("Polling stopped")
    except Exception as exc:
        print(f"Fatal: {exc}", file=sys.stderr)
        raise
