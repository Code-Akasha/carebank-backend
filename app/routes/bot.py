"""Telegram webhook endpoint.

Receives updates from Telegram, extracts message text, maps the Telegram
user to a CareBank user (or creates a guest session), and calls the same
coordinator graph used by the web chat interface.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.models.user import User
from app.schemas.bot import (
    TelegramLinkRequest,
    TelegramLinkResponse,
    TelegramPairApproveRequest,
    TelegramPairApproveResponse,
    TelegramSpendingAlertRequest,
    TelegramSpendingAlertResponse,
    TelegramUnlinkResponse,
)
from app.services.bot_gateway import TelegramGatewayService
from app.services.telegram_alerts import TelegramAlertService
from app.services.telegram_bot import TelegramBot

router = APIRouter(prefix="/bot", tags=["bot"])
telegram_gateway = TelegramGatewayService()
telegram_alert_service = TelegramAlertService()
_TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def _get_bot() -> TelegramBot:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")
    return TelegramBot(settings.telegram_bot_token)


def _verify_telegram_webhook_secret(request: Request) -> None:
    settings = get_settings()
    expected_secret = settings.telegram_webhook_secret.strip()
    if not expected_secret:
        return

    provided_secret = request.headers.get(_TELEGRAM_SECRET_HEADER, "").strip()
    if provided_secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret")


# ---------------------------------------------------------------------------
# Background task: process update and reply
# ---------------------------------------------------------------------------


async def _process_update(
    update: dict[str, Any],
    bot: TelegramBot,
    db: DBSession,
) -> None:
    """Handle a single Telegram update via dedicated gateway service."""
    await telegram_gateway.process_update(update=update, bot=bot, db=db)


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    bot: TelegramBot = Depends(_get_bot),
) -> dict[str, str]:
    """Receive a Telegram update and queue it for processing."""
    _verify_telegram_webhook_secret(request)
    try:
        update: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    background_tasks.add_task(_process_update, update, bot, db)
    return {"status": "queued"}


# ---------------------------------------------------------------------------
# Management helpers (admin only)
# ---------------------------------------------------------------------------


@router.post("/telegram/set-webhook")
async def set_webhook(
    bot: TelegramBot = Depends(_get_bot),
    _admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """Register this server's webhook URL with Telegram."""
    settings = get_settings()
    webhook_url = f"{settings.backend_public_url.rstrip('/')}/bot/telegram/webhook"
    result = await bot.set_webhook(
        webhook_url,
        secret_token=settings.telegram_webhook_secret.strip() or None,
    )
    return {"webhook_url": webhook_url, "telegram_response": result}


@router.delete("/telegram/webhook")
async def delete_webhook(
    bot: TelegramBot = Depends(_get_bot),
    _admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """Unregister the Telegram webhook."""
    result = await bot.delete_webhook()
    return result


@router.post("/telegram/link", response_model=TelegramLinkResponse)
async def link_telegram_id(
    body: TelegramLinkRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TelegramLinkResponse:
    normalized = telegram_gateway.link_telegram_id(
        db=db,
        current_user=current_user,
        telegram_user_id_raw=body.telegram_user_id,
    )

    return TelegramLinkResponse(
        user_id=current_user.user_id,
        telegram_user_id=normalized,
        linked=True,
    )


@router.delete("/telegram/link", response_model=TelegramUnlinkResponse)
async def unlink_telegram_id(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TelegramUnlinkResponse:
    telegram_gateway.unlink_telegram_id(db=db, current_user=current_user)
    return TelegramUnlinkResponse(user_id=current_user.user_id, unlinked=True)


@router.post("/telegram/pair/approve", response_model=TelegramPairApproveResponse)
async def approve_telegram_pairing(
    body: TelegramPairApproveRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TelegramPairApproveResponse:
    telegram_user_id = telegram_gateway.approve_pairing(
        db=db,
        current_user=current_user,
        code=body.code,
    )

    return TelegramPairApproveResponse(
        user_id=current_user.user_id,
        telegram_user_id=telegram_user_id,
        paired=True,
    )


@router.post("/telegram/alerts/spending", response_model=TelegramSpendingAlertResponse)
async def trigger_spending_alert(
    body: TelegramSpendingAlertRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    bot: TelegramBot = Depends(_get_bot),
) -> TelegramSpendingAlertResponse:
    sent, reason = await telegram_alert_service.send_spending_usage_alert(
        db=db,
        bot=bot,
        user=current_user,
        amount=body.amount,
        threshold=body.threshold,
        category=body.category,
    )

    return TelegramSpendingAlertResponse(
        user_id=current_user.user_id,
        telegram_user_id=current_user.telegram_user_id or "",
        alert_sent=sent,
        reason=reason,
    )
