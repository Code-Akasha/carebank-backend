from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User
from app.services.telegram_bot import TelegramBot


class TelegramAlertService:
    async def send_spending_usage_alert(
        self,
        *,
        db: Session,
        bot: TelegramBot,
        user: User,
        amount: float,
        threshold: float,
        category: str | None,
    ) -> tuple[bool, str]:
        if not user.telegram_user_id:
            return False, "telegram_not_linked"

        if amount < threshold:
            return False, "below_threshold"

        now = datetime.now(timezone.utc)
        hour_bucket = now.strftime("%Y%m%d%H")
        safe_category = (category or "general").strip().lower() or "general"
        dedupe_key = f"spending_alert:{user.user_id}:{safe_category}:{hour_bucket}:{int(threshold)}"

        existing = (
            db.query(Notification)
            .filter(
                Notification.user_id == user.user_id,
                Notification.dedupe_key == dedupe_key,
            )
            .first()
        )
        if existing:
            return False, "deduped"

        category_line = (
            f"Category: <b>{safe_category.title()}</b>\n" if safe_category else ""
        )
        text = (
            "Usage Alert: Spending threshold crossed.\n"
            f"Amount: <b>{amount:.2f}</b>\n"
            f"Threshold: <b>{threshold:.2f}</b>\n"
            f"{category_line}"
            "Open CareBank bot for balance, score, and guidance."
        )
        await bot.send_message(chat_id=user.telegram_user_id, text=text)

        notification = Notification(
            user_id=user.user_id,
            dedupe_key=dedupe_key,
            kind="telegram_spending_alert",
            title="Spending usage alert",
            body=text,
            payload_json={
                "amount": amount,
                "threshold": threshold,
                "category": safe_category,
                "telegram_user_id": user.telegram_user_id,
            },
        )
        db.add(notification)
        db.commit()
        return True, "sent"
