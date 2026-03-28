from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from secrets import token_hex
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.models.user import User
from app.services.mpin_service import has_active_mpin_session, verify_mpin
from app.services.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)

_SENSITIVE_BALANCE_KEYWORDS = (
    "balance",
    "account balance",
    "available balance",
    "saldo",
)
_SENSITIVE_SCORE_KEYWORDS = (
    "score",
    "health score",
    "financial health",
)
_SENSITIVE_MONEY_KEYWORDS = (
    "transfer",
    "pay",
    "payment",
    "rent",
    "bill",
    "upi",
    "send money",
)


class TelegramPairingStore:
    """In-memory pairing store for Telegram <-> CareBank account binding."""

    def __init__(self) -> None:
        self._requests: dict[str, dict[str, Any]] = {}

    def purge_expired(self) -> None:
        now = datetime.now(timezone.utc)
        expired: list[str] = []
        for code, payload in self._requests.items():
            expires_at = payload.get("expires_at")
            if isinstance(expires_at, datetime) and expires_at <= now:
                expired.append(code)
        for code in expired:
            self._requests.pop(code, None)

    def create(self, telegram_user_id: str) -> tuple[str, datetime]:
        self.purge_expired()

        settings = get_settings()
        ttl_seconds = max(int(settings.telegram_pairing_ttl_seconds or 3600), 60)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

        for _ in range(6):
            code = token_hex(3).upper()
            if code in self._requests:
                continue
            self._requests[code] = {
                "telegram_user_id": telegram_user_id,
                "expires_at": expires_at,
            }
            return code, expires_at

        raise HTTPException(status_code=500, detail="Could not allocate pairing code")

    def pop(self, code: str) -> dict[str, Any] | None:
        self.purge_expired()
        return self._requests.pop(code.upper(), None)


def normalize_telegram_user_id(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    value = str(raw_value).strip().lower()
    if not value:
        return None
    if value.startswith("telegram:"):
        value = value[len("telegram:") :]
    if value.startswith("tg:"):
        value = value[len("tg:") :]
    if value.startswith("tg_"):
        return value
    if re.fullmatch(r"\d+", value):
        return f"tg_{value}"
    return None


def resolve_telegram_dm_policy() -> str:
    policy = (get_settings().telegram_dm_policy or "pairing").strip().lower()
    if policy not in {"pairing", "allowlist", "open"}:
        return "pairing"
    return policy


class TelegramGatewayService:
    """Business service for Telegram bot auth, pairing and message processing."""

    def __init__(self, pairing_store: TelegramPairingStore | None = None) -> None:
        self.pairing_store = pairing_store or TelegramPairingStore()

    @staticmethod
    def _extract_mpin_submission(message_text: str) -> str | None:
        text = str(message_text or "").strip()
        if not text:
            return None
        lowered = text.lower()
        if lowered.startswith("mpin "):
            candidate = text[5:].strip()
        elif lowered.startswith("/mpin "):
            candidate = text[6:].strip()
        else:
            return None
        if len(candidate) == 4 and candidate.isdigit():
            return candidate
        return ""

    @staticmethod
    def _is_sensitive_intent(message_text: str) -> bool:
        lowered = str(message_text or "").strip().lower()
        if not lowered:
            return False
        for keyword in (
            *_SENSITIVE_BALANCE_KEYWORDS,
            *_SENSITIVE_SCORE_KEYWORDS,
            *_SENSITIVE_MONEY_KEYWORDS,
        ):
            if keyword in lowered:
                return True
        return False

    async def _maybe_handle_mpin_submission(
        self,
        *,
        db: DBSession,
        bot: TelegramBot,
        chat_id: int | str,
        user_key: str,
        current_user: User,
        message_text: str,
        conversation_state: dict[str, Any],
    ) -> bool:
        from app.agents.coordinator import set_conversation_state

        submitted_mpin = self._extract_mpin_submission(message_text)
        if submitted_mpin is None:
            return False

        pending_message = conversation_state.get("mpin_pending_message")
        if not pending_message:
            await bot.send_message(
                chat_id,
                "No pending sensitive request. Ask for balance, score, or a payment action first.",
            )
            return True

        if submitted_mpin == "":
            await bot.send_message(
                chat_id,
                "Invalid MPIN format. Use exactly 4 digits, for example: MPIN 1234",
            )
            return True

        result = verify_mpin(db=db, current_user=current_user, mpin=submitted_mpin)
        if not result.verified:
            if result.lockout_until:
                await bot.send_message(
                    chat_id,
                    (
                        "MPIN temporarily locked due to repeated failures.\n"
                        f"Try again after: {result.lockout_until.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    ),
                )
                return True

            await bot.send_message(
                chat_id,
                (f"Incorrect MPIN. Remaining attempts: {result.remaining_attempts}."),
            )
            return True

        cleaned_state = {
            key: value
            for key, value in conversation_state.items()
            if key not in {"mpin_required", "mpin_pending_message"}
        }
        set_conversation_state(user_key, cleaned_state)

        expires_text = (
            result.verified_until.strftime("%Y-%m-%d %H:%M:%S UTC")
            if result.verified_until
            else "soon"
        )
        await bot.send_message(
            chat_id,
            f"MPIN verified. Sensitive access enabled until {expires_text}.",
        )
        await self._run_coordinator(
            bot=bot,
            db=db,
            chat_id=chat_id,
            user_key=user_key,
            message_text=str(pending_message),
            current_user=current_user,
        )
        return True

    @staticmethod
    def resolve_carebank_user(telegram_user_id: str, *, db: DBSession) -> User | None:
        return db.query(User).filter(User.telegram_user_id == telegram_user_id).first()

    @staticmethod
    def _build_whoami_linked_response(normalized_sender: str) -> str:
        return (
            "Hi, I am CareBank Bot.\n"
            f"Your Telegram id is: <code>{normalized_sender}</code>.\n"
            "Your Telegram id is linked to your CareBank account."
        )

    async def process_update(
        self,
        *,
        update: dict[str, Any],
        bot: TelegramBot,
        db: DBSession,
    ) -> None:
        message = bot.extract_message(update)
        if not message:
            return

        chat_id = bot.get_chat_id(message)
        if not chat_id:
            return

        text = bot.get_text(message)
        if not text:
            await bot.send_message(
                chat_id, "Please type a message to chat with CareBank."
            )
            return

        telegram_user_id = bot.get_telegram_user_id(message)
        normalized_sender = normalize_telegram_user_id(telegram_user_id)
        if not normalized_sender:
            await bot.send_message(
                chat_id,
                "I could not determine your Telegram user id. Please retry from a normal DM.",
            )
            return

        current_user = self.resolve_carebank_user(normalized_sender, db=db)

        if text.strip().lower() in {"/start", "/whoami", "whoami"}:
            if current_user:
                await bot.send_message(
                    chat_id, self._build_whoami_linked_response(normalized_sender)
                )
                return
            if await self._handle_unlinked_user(
                bot=bot,
                chat_id=chat_id,
                normalized_sender=normalized_sender,
            ):
                return

        await bot.send_typing(chat_id)

        if not current_user:
            if await self._handle_unlinked_user(
                bot=bot,
                chat_id=chat_id,
                normalized_sender=normalized_sender,
            ):
                return

        from app.agents.coordinator import (
            get_conversation_state,
            set_conversation_state,
        )

        conversation_state = get_conversation_state(normalized_sender)
        if await self._maybe_handle_mpin_submission(
            db=db,
            bot=bot,
            chat_id=chat_id,
            user_key=normalized_sender,
            current_user=current_user,
            message_text=text,
            conversation_state=conversation_state,
        ):
            return

        if self._is_sensitive_intent(text) and not has_active_mpin_session(
            db=db,
            user_id=current_user.user_id,
        ):
            next_state = {
                **conversation_state,
                "mpin_required": True,
                "mpin_pending_message": text,
            }
            set_conversation_state(normalized_sender, next_state)
            await bot.send_message(
                chat_id,
                (
                    "This request needs MPIN verification.\n"
                    "Reply with: <code>MPIN 1234</code>\n"
                    "(Use your configured 4-digit MPIN.)"
                ),
            )
            return

        await self._run_coordinator(
            bot=bot,
            db=db,
            chat_id=chat_id,
            user_key=normalized_sender,
            message_text=text,
            current_user=current_user,
        )

    async def _handle_unlinked_user(
        self,
        *,
        bot: TelegramBot,
        chat_id: int | str,
        normalized_sender: str,
    ) -> bool:
        settings = get_settings()
        dm_policy = resolve_telegram_dm_policy()
        allowed = normalized_sender in settings.get_telegram_allow_from()

        if dm_policy == "open":
            await bot.send_message(
                chat_id,
                (
                    "Your Telegram id is not linked to a CareBank user yet.\n"
                    f"ID: <code>{normalized_sender}</code>\n"
                    "Please link this id in CareBank to continue."
                ),
            )
            return True

        if dm_policy == "allowlist" and not allowed:
            await bot.send_message(
                chat_id,
                (
                    "Access denied by bot policy.\n"
                    f"Your Telegram id: <code>{normalized_sender}</code>\n"
                    "Ask an admin to add it to TELEGRAM_ALLOW_FROM and then link it to your account."
                ),
            )
            return True

        if dm_policy == "pairing":
            code, expires_at = self.pairing_store.create(normalized_sender)
            await bot.send_message(
                chat_id,
                (
                    "Pairing required before chat access.\n"
                    f"Your Telegram id: <code>{normalized_sender}</code>\n"
                    f"Pairing code: <code>{code}</code>\n"
                    f"Expires at: {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                    "Open CareBank and call POST /bot/telegram/pair/approve with this code."
                ),
            )
            return True

        await bot.send_message(
            chat_id,
            (
                "Pairing required before chat access.\n"
                f"Your Telegram id: <code>{normalized_sender}</code>\n"
                "Log in to CareBank and call POST /bot/telegram/link to link this id."
            ),
        )
        return True

    async def _run_coordinator(
        self,
        *,
        bot: TelegramBot,
        db: DBSession,
        chat_id: int | str,
        user_key: str,
        message_text: str,
        current_user: User,
    ) -> None:
        try:
            from app.agents.coordinator import (
                clear_conversation_state,
                coordinator_graph,
                get_conversation_history,
                get_conversation_state,
                set_conversation_state,
            )

            history = get_conversation_history(user_key)
            conversation_state = get_conversation_state(user_key)

            result = coordinator_graph.invoke(
                {
                    "user_id": user_key,
                    "message": message_text,
                    "audit_log": [],
                    "conversation_history": history,
                    "conversation_state": conversation_state,
                    "db": db,
                    "current_user": current_user,
                }
            )

            if result.get("pending_intent_ignored"):
                clear_conversation_state(user_key)
                conversation_state = {}

            response_metadata = result.get("response_metadata") or {}
            if isinstance(response_metadata, dict):
                if response_metadata.get("clear_pending"):
                    clear_conversation_state(user_key)
                else:
                    pending_state = response_metadata.get("pending_state")
                    if isinstance(pending_state, dict):
                        next_state = {
                            **conversation_state,
                            **pending_state,
                        }
                        set_conversation_state(user_key, next_state)

            reply_text = (
                result.get("agent_response") or "I'm sorry, I didn't understand that."
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Coordinator error for telegram user %s: %s", user_key, exc)
            reply_text = (
                "⚠️ I ran into a problem processing your request. Please try again."
            )

        await bot.send_message(chat_id=chat_id, text=reply_text)

    def link_telegram_id(
        self,
        *,
        db: DBSession,
        current_user: User,
        telegram_user_id_raw: str,
    ) -> str:
        normalized = normalize_telegram_user_id(telegram_user_id_raw)
        if not normalized:
            raise HTTPException(
                status_code=400,
                detail="telegram_user_id must be tg_<numeric_id> or numeric id",
            )

        existing = db.query(User).filter(User.telegram_user_id == normalized).first()
        if existing and existing.user_id != current_user.user_id:
            raise HTTPException(
                status_code=409,
                detail="telegram_user_id already linked to another account",
            )

        current_user.telegram_user_id = normalized
        db.add(current_user)
        db.commit()
        db.refresh(current_user)
        return normalized

    def unlink_telegram_id(self, *, db: DBSession, current_user: User) -> None:
        current_user.telegram_user_id = None
        db.add(current_user)
        db.commit()

    def approve_pairing(
        self,
        *,
        db: DBSession,
        current_user: User,
        code: str,
    ) -> str:
        clean_code = str(code or "").strip().upper()
        if not clean_code:
            raise HTTPException(status_code=400, detail="code is required")

        payload = self.pairing_store.pop(clean_code)
        if not payload:
            raise HTTPException(
                status_code=404, detail="pairing code not found or expired"
            )

        telegram_user_id = normalize_telegram_user_id(payload.get("telegram_user_id"))
        if not telegram_user_id:
            raise HTTPException(status_code=400, detail="invalid pairing payload")

        existing = (
            db.query(User).filter(User.telegram_user_id == telegram_user_id).first()
        )
        if existing and existing.user_id != current_user.user_id:
            raise HTTPException(
                status_code=409,
                detail="telegram_user_id already linked to another account",
            )

        current_user.telegram_user_id = telegram_user_id
        db.add(current_user)
        db.commit()
        db.refresh(current_user)
        return telegram_user_id
