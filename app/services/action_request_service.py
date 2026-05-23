from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.action_execution import ActionExecution
from app.models.action_request import ActionRequest
from app.models.recurring_rule import RecurringRule
from app.models.user import User
from app.schemas.action_engine import (
    ActionDecisionRequest,
    ActionDecisionResult,
    ActionExecutionResponse,
    ActionRequestCreate,
    ActionRequestCreateResult,
    ActionRequestResponse,
)
from app.services.action_executor import execute_action
from app.services.action_policy import evaluate_action_policy
from app.services.idempotency import (
    IdempotencyConflictError,
    hash_payload,
    mark_completed,
    reserve_or_replay,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def serialize_request(
    model: ActionRequest,
    *,
    replayed: bool = False,
) -> ActionRequestResponse:
    return ActionRequestResponse(
        id=model.id,
        user_id=model.user_id,
        action_type=model.action_type,
        action_payload=model.action_payload_json or {},
        policy_snapshot=model.policy_snapshot_json,
        status=model.status,
        idempotency_key=model.idempotency_key,
        expires_at=model.expires_at,
        decided_at=model.decided_at,
        decision_reason=model.decision_reason,
        linked_execution_id=model.linked_execution_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        replayed=replayed,
    )


def serialize_execution(model: ActionExecution) -> ActionExecutionResponse:
    return ActionExecutionResponse(
        id=model.id,
        user_id=model.user_id,
        approval_request_id=model.approval_request_id,
        action_type=model.action_type,
        status=model.status,
        idempotency_key=model.idempotency_key,
        request_payload=model.request_payload_json or {},
        result_payload=model.result_payload_json,
        attempt_count=model.attempt_count,
        max_retries=model.max_retries,
        last_error=model.last_error,
        started_at=model.started_at,
        finished_at=model.finished_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def verify_mockbank_signature(
    *,
    body: bytes,
    signature: str | None,
    timestamp: str | None,
) -> bool:
    if not signature or not timestamp:
        return False

    settings = get_settings()
    try:
        ts = int(timestamp)
    except ValueError:
        return False

    now_ts = int(utc_now().timestamp())
    if abs(now_ts - ts) > settings.mockbank_webhook_signature_tolerance_seconds:
        return False

    signed_payload = f"{timestamp}.{body.decode('utf-8')}"
    expected = hmac.new(
        settings.mockbank_webhook_secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature.strip(), expected)


def is_trusted_recurring(db: Session, user_id: str, payload: dict) -> bool:
    recurring_rule_id = payload.get("recurring_rule_id")
    if recurring_rule_id is None:
        return False

    rule = (
        db.query(RecurringRule)
        .filter(RecurringRule.id == recurring_rule_id, RecurringRule.user_id == user_id)
        .first()
    )
    if not rule:
        return False

    return bool(rule.trusted_recurring and rule.autopay_enabled)


def create_action_request_for_user(
    db: Session,
    *,
    current_user: User,
    body: ActionRequestCreate,
) -> ActionRequestCreateResult:
    trusted_recurring = is_trusted_recurring(
        db,
        current_user.user_id,
        body.action_payload,
    )
    policy = evaluate_action_policy(
        body.action_type,
        body.action_payload,
        trusted_recurring=trusted_recurring,
    )
    if not policy.get("allowed"):
        raise HTTPException(status_code=400, detail=str(policy.get("reason")))

    idempotency_record = None
    if body.idempotency_key:
        try:
            idempotency_record, replayed = reserve_or_replay(
                db,
                user_id=current_user.user_id,
                scope="action_request",
                idempotency_key=body.idempotency_key,
                payload={
                    "action_type": body.action_type,
                    "action_payload": body.action_payload,
                    "expires_in_hours": body.expires_in_hours,
                },
            )
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        if replayed and idempotency_record.response_json:
            request_id = idempotency_record.response_json.get("request_id")
            if request_id:
                existing_request = (
                    db.query(ActionRequest)
                    .filter(
                        ActionRequest.id == int(request_id),
                        ActionRequest.user_id == current_user.user_id,
                    )
                    .first()
                )
                if existing_request:
                    execution = None
                    if existing_request.linked_execution_id:
                        execution = (
                            db.query(ActionExecution)
                            .filter(
                                ActionExecution.id
                                == existing_request.linked_execution_id,
                                ActionExecution.user_id == current_user.user_id,
                            )
                            .first()
                        )
                    return ActionRequestCreateResult(
                        request=serialize_request(existing_request, replayed=True),
                        execution=serialize_execution(execution) if execution else None,
                    )

    requires_approval = bool(policy.get("requires_approval", True))

    request = ActionRequest(
        user_id=current_user.user_id,
        action_type=body.action_type,
        action_payload_json=body.action_payload,
        policy_snapshot_json=policy,
        status="pending" if requires_approval else "approved",
        idempotency_key=body.idempotency_key,
        request_hash=hash_payload(body.action_payload),
        expires_at=utc_now() + timedelta(hours=body.expires_in_hours),
        decided_at=utc_now() if not requires_approval else None,
        decision_reason=(
            "Auto-approved: trusted recurring policy"
            if not requires_approval and trusted_recurring
            else "Auto-approved by action policy"
            if not requires_approval
            else None
        ),
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    if idempotency_record:
        mark_completed(
            db,
            idempotency_record,
            status="completed",
            response_payload={"request_id": request.id},
        )

    execution = None
    if request.status == "approved":
        execution = execute_action(
            db,
            user_id=current_user.user_id,
            action_type=request.action_type,
            action_payload=request.action_payload_json or {},
            idempotency_key=request.idempotency_key,
            approval_request_id=request.id,
        )
        request.linked_execution_id = execution.id
        db.commit()
        db.refresh(request)

    return ActionRequestCreateResult(
        request=serialize_request(request),
        execution=serialize_execution(execution) if execution else None,
    )


def approve_action_request_for_user(
    db: Session,
    *,
    request_id: int,
    body: ActionDecisionRequest,
    current_user: User,
) -> ActionDecisionResult:
    request = (
        db.query(ActionRequest)
        .filter(
            ActionRequest.id == request_id,
            ActionRequest.user_id == current_user.user_id,
        )
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Action request not found")

    if request.status == "approved" and request.linked_execution_id:
        existing_execution = (
            db.query(ActionExecution)
            .filter(
                ActionExecution.id == request.linked_execution_id,
                ActionExecution.user_id == current_user.user_id,
            )
            .first()
        )
        return ActionDecisionResult(
            request=serialize_request(request),
            execution=serialize_execution(existing_execution)
            if existing_execution
            else None,
        )

    if request.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Action request cannot be approved from status={request.status}",
        )

    if as_utc(request.expires_at) < utc_now():
        request.status = "expired"
        request.decided_at = utc_now()
        request.decision_reason = "Expired before approval"
        db.commit()
        db.refresh(request)
        raise HTTPException(status_code=400, detail="Action request has expired")

    request.status = "approved"
    request.decided_at = utc_now()
    request.decision_reason = body.reason or "Approved by user"
    db.commit()
    db.refresh(request)

    execution = execute_action(
        db,
        user_id=current_user.user_id,
        action_type=request.action_type,
        action_payload=request.action_payload_json or {},
        idempotency_key=request.idempotency_key,
        approval_request_id=request.id,
    )
    request.linked_execution_id = execution.id
    db.commit()
    db.refresh(request)

    return ActionDecisionResult(
        request=serialize_request(request),
        execution=serialize_execution(execution),
    )


def reject_action_request_for_user(
    db: Session,
    *,
    request_id: int,
    body: ActionDecisionRequest,
    current_user: User,
) -> ActionDecisionResult:
    request = (
        db.query(ActionRequest)
        .filter(
            ActionRequest.id == request_id,
            ActionRequest.user_id == current_user.user_id,
        )
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Action request not found")

    if request.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Action request cannot be rejected from status={request.status}",
        )

    request.status = "rejected"
    request.decided_at = utc_now()
    request.decision_reason = body.reason or "Rejected by user"
    db.commit()
    db.refresh(request)

    return ActionDecisionResult(request=serialize_request(request), execution=None)
