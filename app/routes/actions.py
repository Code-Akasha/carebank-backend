from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
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
from app.services.banking_client import BankingClientError, get_banking_client
from app.services.idempotency import (
    IdempotencyConflictError,
    hash_payload,
    mark_completed,
    reserve_or_replay,
)

router = APIRouter(prefix="/api/actions", tags=["actions"])


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _serialize_request(
    model: ActionRequest, *, replayed: bool = False
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


def _serialize_execution(model: ActionExecution) -> ActionExecutionResponse:
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


def _verify_mockbank_signature(
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

    now_ts = int(_utc_now().timestamp())
    if abs(now_ts - ts) > settings.mockbank_webhook_signature_tolerance_seconds:
        return False

    signed_payload = f"{timestamp}.{body.decode('utf-8')}"
    expected = hmac.new(
        settings.mockbank_webhook_secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature.strip(), expected)


def _is_trusted_recurring(db: Session, user_id: str, payload: dict) -> bool:
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


class ExecutionReconcileRequest(BaseModel):
    execution_id: int | None = Field(default=None, ge=1)
    lookback_hours: int = Field(default=72, ge=1, le=24 * 30)
    max_items: int = Field(default=50, ge=1, le=500)


def _extract_transaction_id(execution: ActionExecution) -> int | None:
    payload = execution.result_payload_json or {}
    upstream = payload.get("upstream_response")
    if not isinstance(upstream, dict):
        return None
    transaction = upstream.get("transaction")
    if not isinstance(transaction, dict):
        return None
    transaction_id = transaction.get("id")
    if transaction_id is None:
        return None
    try:
        return int(transaction_id)
    except (TypeError, ValueError):
        return None


def _map_bank_status(bank_status: str) -> str | None:
    normalized = bank_status.lower().strip()
    if normalized == "success":
        return "success"
    if normalized in {"failure", "failed"}:
        return "failure"
    if normalized in {"reversed", "rollback"}:
        return "rollback"
    return None


@router.post(
    "/requests",
    response_model=ActionRequestCreateResult,
    status_code=status.HTTP_201_CREATED,
)
def create_action_request(
    body: ActionRequestCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    trusted_recurring = _is_trusted_recurring(
        db, current_user.user_id, body.action_payload
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
                        request=_serialize_request(existing_request, replayed=True),
                        execution=_serialize_execution(execution)
                        if execution
                        else None,
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
        expires_at=_utc_now() + timedelta(hours=body.expires_in_hours),
        decided_at=_utc_now() if not requires_approval else None,
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
        request=_serialize_request(request),
        execution=_serialize_execution(execution) if execution else None,
    )


@router.get("/requests", response_model=list[ActionRequestResponse])
def list_action_requests(
    current_user: Annotated[User, Depends(get_current_user)],
    status_filter: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(ActionRequest).filter(
        ActionRequest.user_id == current_user.user_id
    )
    if status_filter:
        query = query.filter(ActionRequest.status == status_filter)

    requests = query.order_by(ActionRequest.created_at.desc()).all()
    return [_serialize_request(item) for item in requests]


@router.post("/requests/{request_id}/approve", response_model=ActionDecisionResult)
def approve_action_request(
    request_id: int,
    body: ActionDecisionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
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
            request=_serialize_request(request),
            execution=_serialize_execution(existing_execution)
            if existing_execution
            else None,
        )

    if request.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Action request cannot be approved from status={request.status}",
        )

    if _as_utc(request.expires_at) < _utc_now():
        request.status = "expired"
        request.decided_at = _utc_now()
        request.decision_reason = "Expired before approval"
        db.commit()
        db.refresh(request)
        raise HTTPException(status_code=400, detail="Action request has expired")

    request.status = "approved"
    request.decided_at = _utc_now()
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
        request=_serialize_request(request),
        execution=_serialize_execution(execution),
    )


@router.post("/requests/{request_id}/reject", response_model=ActionDecisionResult)
def reject_action_request(
    request_id: int,
    body: ActionDecisionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
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
    request.decided_at = _utc_now()
    request.decision_reason = body.reason or "Rejected by user"
    db.commit()
    db.refresh(request)

    return ActionDecisionResult(request=_serialize_request(request), execution=None)


@router.get("/executions", response_model=list[ActionExecutionResponse])
def list_action_executions(
    current_user: Annotated[User, Depends(get_current_user)],
    status_filter: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(ActionExecution).filter(
        ActionExecution.user_id == current_user.user_id
    )
    if status_filter:
        query = query.filter(ActionExecution.status == status_filter)

    executions = query.order_by(ActionExecution.created_at.desc()).all()
    return [_serialize_execution(item) for item in executions]


@router.get("/executions/{execution_id}", response_model=ActionExecutionResponse)
def get_action_execution(
    execution_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    execution = (
        db.query(ActionExecution)
        .filter(
            ActionExecution.id == execution_id,
            ActionExecution.user_id == current_user.user_id,
        )
        .first()
    )
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    return _serialize_execution(execution)


@router.post("/executions/reconcile")
async def reconcile_action_executions(
    body: ExecutionReconcileRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    client = get_banking_client()

    query = db.query(ActionExecution).filter(
        ActionExecution.user_id == current_user.user_id
    )
    if body.execution_id is not None:
        query = query.filter(ActionExecution.id == body.execution_id)
    else:
        cutoff = _utc_now() - timedelta(hours=body.lookback_hours)
        query = query.filter(
            ActionExecution.created_at >= cutoff,
            ActionExecution.status.in_(["running", "success"]),
        ).order_by(ActionExecution.created_at.desc())

    executions = query.limit(body.max_items).all()
    if body.execution_id is not None and not executions:
        raise HTTPException(status_code=404, detail="Execution not found")

    updated_count = 0
    inspected_count = 0
    results: list[dict] = []

    for execution in executions:
        inspected_count += 1
        transaction_id = _extract_transaction_id(execution)
        if transaction_id is None:
            results.append(
                {
                    "execution_id": execution.id,
                    "status": "skipped",
                    "reason": "transaction_id_missing",
                }
            )
            continue

        try:
            lifecycle = await client.get_transaction_lifecycle(
                current_user.user_id,
                transaction_id,
            )
        except BankingClientError as exc:
            results.append(
                {
                    "execution_id": execution.id,
                    "status": "error",
                    "reason": str(exc),
                    "transaction_id": transaction_id,
                }
            )
            continue

        bank_status = str(lifecycle.get("status") or "").lower()
        target_status = _map_bank_status(bank_status)
        lifecycle_events = lifecycle.get("lifecycle")
        latest_event = (
            lifecycle_events[-1]
            if isinstance(lifecycle_events, list) and lifecycle_events
            else None
        )

        changed = False
        if target_status and target_status != execution.status:
            execution.status = target_status
            changed = True
            if target_status == "success":
                execution.last_error = None
            elif target_status == "failure":
                execution.last_error = str(
                    (latest_event or {}).get("reason")
                    or "Reconciled failure from MockBank"
                )
            elif target_status == "rollback":
                execution.last_error = str(
                    (latest_event or {}).get("reason")
                    or "Reconciled reversal from MockBank"
                )

            if target_status in {"success", "failure", "rollback"}:
                execution.finished_at = _utc_now()

        reconciliation_snapshot = {
            "checked_at": _utc_now().isoformat(),
            "transaction_id": transaction_id,
            "bank_status": bank_status,
            "updated": changed,
        }
        if latest_event:
            reconciliation_snapshot["latest_event"] = latest_event

        existing_payload = execution.result_payload_json or {}
        new_payload = {
            **existing_payload,
            "mockbank_reconciliation": reconciliation_snapshot,
        }
        if latest_event:
            new_payload["mockbank_lifecycle"] = {
                "event_type": "transaction.lifecycle.reconciled",
                "transaction_id": transaction_id,
                "user_id": current_user.user_id,
                "status": latest_event.get("status", bank_status),
                "timestamp": latest_event.get("timestamp"),
                "reason": latest_event.get("reason"),
                "metadata": latest_event.get("metadata") or {},
            }
        execution.result_payload_json = new_payload

        if changed:
            updated_count += 1

        results.append(
            {
                "execution_id": execution.id,
                "status": "updated" if changed else "unchanged",
                "execution_status": execution.status,
                "bank_status": bank_status,
                "transaction_id": transaction_id,
            }
        )

    db.commit()

    return {
        "status": "completed",
        "inspected_count": inspected_count,
        "updated_count": updated_count,
        "results": results,
    }


@router.post("/webhooks/mockbank", status_code=status.HTTP_202_ACCEPTED)
async def mockbank_lifecycle_webhook(
    request: Request,
    x_carebank_signature: Annotated[
        str | None, Header(alias="X-CareBank-Signature")
    ] = None,
    x_carebank_timestamp: Annotated[
        str | None, Header(alias="X-CareBank-Timestamp")
    ] = None,
    db: Session = Depends(get_db),
):
    body = await request.body()
    if not _verify_mockbank_signature(
        body=body,
        signature=x_carebank_signature,
        timestamp=x_carebank_timestamp,
    ):
        raise HTTPException(
            status_code=401, detail="Invalid MockBank webhook signature"
        )

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc

    metadata = payload.get("metadata") or {}
    execution_id = metadata.get("execution_id")
    execution: ActionExecution | None = None

    if execution_id is not None:
        try:
            execution = (
                db.query(ActionExecution)
                .filter(ActionExecution.id == int(execution_id))
                .first()
            )
        except (TypeError, ValueError):
            execution = None

    if execution is None:
        idempotency_key = payload.get("idempotency_key")
        user_id = payload.get("user_id")
        if idempotency_key:
            query = db.query(ActionExecution).filter(
                ActionExecution.idempotency_key == str(idempotency_key)
            )
            if user_id:
                query = query.filter(ActionExecution.user_id == str(user_id))
            execution = query.order_by(ActionExecution.id.desc()).first()

    if execution is None:
        return {
            "status": "ignored",
            "reason": "execution_not_found",
        }

    transaction_status = str(payload.get("status") or "").lower()
    reason = payload.get("reason")

    existing_result_payload = execution.result_payload_json or {}
    execution.result_payload_json = {
        **existing_result_payload,
        "mockbank_lifecycle": payload,
    }

    if transaction_status == "success":
        execution.status = "success"
        execution.last_error = None
    elif transaction_status == "failure":
        execution.status = "failure"
        execution.last_error = str(reason or "MockBank reported failure")
    elif transaction_status == "reversed":
        execution.status = "rollback"
        execution.last_error = str(reason or "Transaction reversed by bank")

    if transaction_status in {"success", "failure", "reversed"}:
        execution.finished_at = _utc_now()

    db.commit()
    db.refresh(execution)

    return {
        "status": "accepted",
        "execution_id": execution.id,
        "execution_status": execution.status,
    }
