from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.models.idempotency_record import IdempotencyRecord


class IdempotencyConflictError(ValueError):
    """Raised when the same idempotency key is reused with different payload."""


class IdempotencyReplayError(ValueError):
    """Raised when replayed key exists without persisted response payload."""


def hash_payload(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def reserve_or_replay(
    db: Session,
    *,
    user_id: str,
    scope: str,
    idempotency_key: str,
    payload: dict,
) -> tuple[IdempotencyRecord, bool]:
    request_hash = hash_payload(payload)
    existing = (
        db.query(IdempotencyRecord)
        .filter(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing:
        if existing.request_hash != request_hash:
            raise IdempotencyConflictError(
                "Idempotency key already used for a different request payload",
            )
        return existing, True

    record = IdempotencyRecord(
        user_id=user_id,
        scope=scope,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status="reserved",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record, False


def mark_completed(
    db: Session,
    record: IdempotencyRecord,
    *,
    status: str,
    response_payload: dict | None,
) -> IdempotencyRecord:
    record.status = status
    record.response_json = response_payload
    db.commit()
    db.refresh(record)
    return record
