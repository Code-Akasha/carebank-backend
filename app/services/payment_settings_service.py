"""Payment settings service."""

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.core.security import hash_password, verify_password

from app.models.payment_settings import PaymentSettings
from app.models.user import User
from app.schemas.payments import PaymentSettingsUpdate, SetMPINRequest


def get_or_create_payment_settings(db: Session, user_id: str) -> PaymentSettings:
    """Get existing payment settings or create default ones."""
    settings = db.query(PaymentSettings).filter(PaymentSettings.user_id == user_id).first()

    if not settings:
        settings = PaymentSettings(
            user_id=user_id,
            mpin_threshold=50000.0,
            auto_approve_trusted=True,
            daily_limit=1000000.0,
            recurring_payment_max=100000.0,
            max_active_recurring_rules=10,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return settings


def get_payment_settings(db: Session, user_id: str) -> PaymentSettings:
    """Get payment settings for user."""
    return get_or_create_payment_settings(db, user_id)


def update_payment_settings(
    db: Session,
    user_id: str,
    body: PaymentSettingsUpdate,
) -> PaymentSettings:
    """Update payment settings."""
    settings = get_or_create_payment_settings(db, user_id)

    if body.mpin_threshold is not None:
        settings.mpin_threshold = body.mpin_threshold
    if body.auto_approve_trusted is not None:
        settings.auto_approve_trusted = body.auto_approve_trusted
    if body.daily_limit is not None:
        settings.daily_limit = body.daily_limit
    if body.recurring_payment_max is not None:
        settings.recurring_payment_max = body.recurring_payment_max

    settings.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)
    return settings


def set_mpin(db: Session, user_id: str, body: SetMPINRequest) -> None:
    """Set or update user MPIN."""
    settings = get_or_create_payment_settings(db, user_id)

    # Hash MPIN with bcrypt
    settings.mpin_hash = hash_password(body.mpin)
    settings.updated_at = datetime.now(timezone.utc)

    db.commit()


def verify_mpin(db: Session, user_id: str, mpin: str) -> bool:
    """Verify user's MPIN."""
    settings = db.query(PaymentSettings).filter(PaymentSettings.user_id == user_id).first()

    if not settings or not settings.mpin_hash:
        raise HTTPException(status_code=400, detail="MPIN not configured")

    return verify_password(mpin, settings.mpin_hash)


def check_daily_limit(
    db: Session,
    user_id: str,
    payment_amount: float,
) -> tuple[bool, str | None]:
    """Check if payment is within daily limit.

    Returns: (is_within_limit, error_message)
    """
    from app.models.payment_history import PaymentHistory
    from datetime import date

    settings = get_or_create_payment_settings(db, user_id)

    # Get total paid today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = datetime.now(timezone.utc)

    total_today = (
        db.query(PaymentHistory.__table__.c.amount)
        .filter(
            PaymentHistory.user_id == user_id,
            PaymentHistory.status == "success",
            PaymentHistory.execution_date >= today_start,
            PaymentHistory.execution_date <= today_end,
        )
        .scalar()
        or 0.0
    )

    if total_today + payment_amount > settings.daily_limit:
        remaining = max(0, settings.daily_limit - total_today)
        return False, f"Daily limit exceeded. Remaining: ₹{remaining}"

    return True, None


def reset_daily_limit_if_needed(db: Session, user_id: str) -> None:
    """Reset daily limit counter if it's a new day."""
    from datetime import date

    settings = get_or_create_payment_settings(db, user_id)

    if settings.daily_limit_used_date is None:
        settings.daily_limit_used_date = datetime.now(timezone.utc)
        settings.daily_limit_used = 0.0
        db.commit()
    else:
        last_date = settings.daily_limit_used_date.date() if isinstance(settings.daily_limit_used_date, datetime) else settings.daily_limit_used_date
        today = date.today()

        if last_date < today:
            settings.daily_limit_used_date = datetime.now(timezone.utc)
            settings.daily_limit_used = 0.0
            db.commit()
