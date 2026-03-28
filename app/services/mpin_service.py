from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.models.user_mpin import UserMPIN


@dataclass
class MPINVerifyResult:
    verified: bool
    remaining_attempts: int
    lockout_until: datetime | None
    verified_until: datetime | None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create_record(*, db: Session, user_id: str) -> UserMPIN:
    record = db.query(UserMPIN).filter(UserMPIN.user_id == user_id).first()
    if record:
        return record
    record = UserMPIN(user_id=user_id, mpin_hash="", failed_attempts=0)
    db.add(record)
    db.flush()
    return record


def _require_valid_mpin_format(mpin: str) -> str:
    normalized = str(mpin or "").strip()
    if len(normalized) != 4 or not normalized.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MPIN must be exactly 4 digits",
        )
    return normalized


def set_mpin(*, db: Session, current_user: User, mpin: str) -> None:
    normalized = _require_valid_mpin_format(mpin)
    record = _get_or_create_record(db=db, user_id=current_user.user_id)
    record.mpin_hash = hash_password(normalized)
    record.failed_attempts = 0
    record.lockout_until = None
    record.last_verified_at = None
    db.add(record)
    db.commit()


def has_active_mpin_session(*, db: Session, user_id: str) -> bool:
    settings = get_settings()
    ttl_seconds = max(int(settings.mpin_session_ttl_seconds or 900), 60)
    record = db.query(UserMPIN).filter(UserMPIN.user_id == user_id).first()
    if not record or not record.last_verified_at:
        return False
    return record.last_verified_at + timedelta(seconds=ttl_seconds) > _now_utc()


def verify_mpin(*, db: Session, current_user: User, mpin: str) -> MPINVerifyResult:
    settings = get_settings()
    max_attempts = max(int(settings.mpin_max_attempts or 3), 1)
    lockout_seconds = max(int(settings.mpin_lockout_seconds or 300), 60)
    ttl_seconds = max(int(settings.mpin_session_ttl_seconds or 900), 60)

    normalized = _require_valid_mpin_format(mpin)
    record = db.query(UserMPIN).filter(UserMPIN.user_id == current_user.user_id).first()
    if not record or not record.mpin_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MPIN not set. Configure MPIN in your account first.",
        )

    now = _now_utc()
    if record.lockout_until and record.lockout_until > now:
        remaining = max(max_attempts - record.failed_attempts, 0)
        return MPINVerifyResult(
            verified=False,
            remaining_attempts=remaining,
            lockout_until=record.lockout_until,
            verified_until=None,
        )

    if verify_password(normalized, record.mpin_hash):
        record.failed_attempts = 0
        record.lockout_until = None
        record.last_verified_at = now
        db.add(record)
        db.commit()
        return MPINVerifyResult(
            verified=True,
            remaining_attempts=max_attempts,
            lockout_until=None,
            verified_until=now + timedelta(seconds=ttl_seconds),
        )

    record.failed_attempts += 1
    remaining_attempts = max(max_attempts - record.failed_attempts, 0)
    lockout_until: datetime | None = None
    if record.failed_attempts >= max_attempts:
        lockout_until = now + timedelta(seconds=lockout_seconds)
        record.lockout_until = lockout_until
        record.failed_attempts = max_attempts

    db.add(record)
    db.commit()
    return MPINVerifyResult(
        verified=False,
        remaining_attempts=remaining_attempts,
        lockout_until=lockout_until,
        verified_until=None,
    )
