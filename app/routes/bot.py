"""Telegram webhook endpoint.

Receives updates from Telegram, extracts message text, maps the Telegram
user to a CareBank user (or creates a guest session), and calls the same
coordinator graph used by the web chat interface.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.core.database import get_db
from app.services.telegram_bot import TelegramBot
from app.services.whatsapp_bot import WhatsAppBot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bot", tags=["bot"])


def _get_bot() -> TelegramBot:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")
    return TelegramBot(settings.telegram_bot_token)


def _get_whatsapp_bot() -> WhatsAppBot:
    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise HTTPException(status_code=503, detail="WhatsApp bot not configured")
    return WhatsAppBot(
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
        from_number=settings.twilio_whatsapp_from,
    )


# ---------------------------------------------------------------------------
# User lookup / session helpers
# ---------------------------------------------------------------------------


def _resolve_carebank_user(telegram_user_id: str, *, db: DBSession) -> Any:
    """Look up CareBank user by telegram_user_id stored in metadata.

    Falls back to a demo user (user_001) so the bot is always functional
    during hackathon — replace with full OAuth flow in production.
    """
    from app.models.user import User

    # Try to find user where telegram_user_id is stored in a metadata JSON field
    user = db.query(User).filter(User.telegram_user_id == telegram_user_id).first()
    if user:
        return user

    # Fallback: return the first seeded user so demos always work
    demo_user = db.query(User).order_by(User.id).first()
    return demo_user


# ---------------------------------------------------------------------------
# Background task: process update and reply
# ---------------------------------------------------------------------------


async def _process_update(
    update: dict[str, Any],
    bot: TelegramBot,
    db: DBSession,
) -> None:
    """Handle a single Telegram update: classify intent, run coordinator, reply."""
    message = bot.extract_message(update)
    if not message:
        return

    chat_id = bot.get_chat_id(message)
    if not chat_id:
        return

    text = bot.get_text(message)
    if not text:
        await bot.send_message(chat_id, "Please type a message to chat with CareBank.")
        return

    telegram_user_id = bot.get_telegram_user_id(message)

    # Show typing indicator
    await bot.send_typing(chat_id)

    # Resolve CareBank user
    current_user = None
    if telegram_user_id:
        current_user = _resolve_carebank_user(telegram_user_id, db=db)

    if not current_user:
        await bot.send_message(
            chat_id,
            (
                "Hi! I'm CareBank's AI assistant. 👋\n"
                "I couldn't find your linked bank account. "
                "Please log in via the CareBank app and link your Telegram account first."
            ),
        )
        return

    # Call the coordinator graph (same as web chat)
    try:
        from app.agents.coordinator import (
            coordinator_graph,
            get_conversation_history,
            get_conversation_state,
            set_conversation_state,
            clear_conversation_state,
        )

        history = get_conversation_history(telegram_user_id)
        conversation_state = get_conversation_state(telegram_user_id)

        result = coordinator_graph.invoke(
            {
                "user_id": telegram_user_id,
                "message": text,
                "audit_log": [],
                "conversation_history": history,
                "conversation_state": conversation_state,
                "db": db,
                "current_user": current_user,
            }
        )

        if result.get("pending_intent_ignored"):
            clear_conversation_state(telegram_user_id)
            conversation_state = {}

        response_metadata = result.get("response_metadata") or {}
        if isinstance(response_metadata, dict):
            if response_metadata.get("clear_pending"):
                clear_conversation_state(telegram_user_id)
            else:
                pending_state = response_metadata.get("pending_state")
                if isinstance(pending_state, dict):
                    next_state = {
                        **conversation_state,
                        **pending_state,
                    }
                    set_conversation_state(telegram_user_id, next_state)

        reply_text = (
            result.get("agent_response") or "I'm sorry, I didn't understand that."
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Coordinator error for telegram user %s: %s", telegram_user_id, exc
        )
        reply_text = "⚠️ I ran into a problem processing your request. Please try again."

    await bot.send_message(chat_id, reply_text)


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
    try:
        update: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    background_tasks.add_task(_process_update, update, bot, db)
    return {"status": "queued"}


async def _process_whatsapp_update(
    form_data: dict[str, Any],
    bot: WhatsAppBot,
    db: DBSession,
) -> None:
    """Handle a single WhatsApp update: classify intent, run coordinator, reply."""
    message = bot.extract_message(form_data)
    if not message:
        return

    to_number = bot.get_user_phone(message)
    if not to_number:
        return

    text = bot.get_text(message)
    if not text:
        await bot.send_message(
            to_number, "Please type a message to chat with CareBank."
        )
        return

    whatsapp_user_id = bot.get_whatsapp_user_id(message)

    # Resolve CareBank user
    current_user = None
    if whatsapp_user_id:
        current_user = _resolve_carebank_user(whatsapp_user_id, db=db)

    # Fallback identical to resolve algorithm if it returned None
    if not current_user:
        current_user = _resolve_carebank_user("fallback", db=db)

    # Call the coordinator graph
    try:
        from app.agents.coordinator import (
            coordinator_graph,
            get_conversation_history,
            get_conversation_state,
            set_conversation_state,
            clear_conversation_state,
        )

        history = get_conversation_history(whatsapp_user_id)
        conversation_state = get_conversation_state(whatsapp_user_id)

        result = coordinator_graph.invoke(
            {
                "user_id": whatsapp_user_id,
                "message": text,
                "audit_log": [],
                "conversation_history": history,
                "conversation_state": conversation_state,
                "db": db,
                "current_user": current_user,
            }
        )

        if result.get("pending_intent_ignored"):
            clear_conversation_state(whatsapp_user_id)
            conversation_state = {}

        response_metadata = result.get("response_metadata") or {}
        if isinstance(response_metadata, dict):
            if response_metadata.get("clear_pending"):
                clear_conversation_state(whatsapp_user_id)
            else:
                pending_state = response_metadata.get("pending_state")
                if isinstance(pending_state, dict):
                    next_state = {
                        **conversation_state,
                        **pending_state,
                    }
                    set_conversation_state(whatsapp_user_id, next_state)

        reply_text = (
            result.get("agent_response") or "I'm sorry, I didn't understand that."
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Coordinator error for whatsapp user %s: %s", whatsapp_user_id, exc
        )
        reply_text = "⚠️ I ran into a problem processing your request. Please try again."

    await bot.send_message(to_number, reply_text)


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    bot: WhatsAppBot = Depends(_get_whatsapp_bot),
) -> dict[str, str]:
    """Receive a WhatsApp update and queue it for processing."""
    try:
        if request.headers.get("Content-Type", "").startswith("application/json"):
            form_data: dict[str, Any] = await request.json()
        else:
            form_payload = await request.form()
            form_data = dict(form_payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    background_tasks.add_task(_process_whatsapp_update, form_data, bot, db)
    return {"status": "queued"}


# ---------------------------------------------------------------------------
# Management helpers (admin only — no auth for hackathon)
# ---------------------------------------------------------------------------


@router.post("/telegram/set-webhook")
async def set_webhook(bot: TelegramBot = Depends(_get_bot)) -> dict[str, Any]:
    """Register this server's webhook URL with Telegram."""
    settings = get_settings()
    webhook_url = f"{settings.backend_public_url.rstrip('/')}/bot/telegram/webhook"
    result = await bot.set_webhook(webhook_url)
    return {"webhook_url": webhook_url, "telegram_response": result}


@router.delete("/telegram/webhook")
async def delete_webhook(bot: TelegramBot = Depends(_get_bot)) -> dict[str, Any]:
    """Unregister the Telegram webhook."""
    result = await bot.delete_webhook()
    return result
