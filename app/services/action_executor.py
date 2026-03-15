from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.action_execution import ActionExecution
from app.services.idempotency import (
    IdempotencyConflictError,
    hash_payload,
    mark_completed,
    reserve_or_replay,
)
from app.tools.registry import ToolNotFoundError, get_tool_registry


def execute_action(
    db: Session,
    *,
    user_id: str,
    action_type: str,
    action_payload: dict,
    idempotency_key: str | None = None,
    approval_request_id: int | None = None,
    max_retries: int = 2,
) -> ActionExecution:
    idempotency_record = None

    if idempotency_key:
        idempotency_record, replayed = reserve_or_replay(
            db,
            user_id=user_id,
            scope="execution",
            idempotency_key=idempotency_key,
            payload={
                "action_type": action_type,
                "action_payload": action_payload,
                "approval_request_id": approval_request_id,
            },
        )
        if replayed and idempotency_record.response_json:
            cached_execution_id = idempotency_record.response_json.get("execution_id")
            if cached_execution_id:
                cached = (
                    db.query(ActionExecution)
                    .filter(
                        ActionExecution.id == int(cached_execution_id),
                        ActionExecution.user_id == user_id,
                    )
                    .first()
                )
                if cached:
                    return cached

    execution = ActionExecution(
        user_id=user_id,
        approval_request_id=approval_request_id,
        action_type=action_type,
        status="queued",
        idempotency_key=idempotency_key,
        request_hash=hash_payload(action_payload),
        request_payload_json=action_payload,
        max_retries=max_retries,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    execution.status = "running"
    execution.started_at = datetime.now(timezone.utc)
    db.commit()

    tool = get_tool_registry().get(action_type)

    tool_payload = dict(action_payload)
    tool_payload["_execution_id"] = execution.id
    if approval_request_id is not None:
        tool_payload["_approval_request_id"] = approval_request_id
    if idempotency_key:
        tool_payload["_execution_idempotency_key"] = idempotency_key

    last_error = None
    for attempt in range(1, max_retries + 2):
        execution.attempt_count = attempt
        try:
            result = tool.execute(
                user_id=user_id, action_type=action_type, payload=tool_payload
            )
            execution.status = "success"
            execution.result_payload_json = result
            execution.last_error = None
            execution.finished_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(execution)

            if idempotency_record:
                mark_completed(
                    db,
                    idempotency_record,
                    status="completed",
                    response_payload={
                        "execution_id": execution.id,
                        "status": execution.status,
                    },
                )
            return execution
        except (ToolNotFoundError, ValueError, IdempotencyConflictError) as exc:
            # Non-retryable errors.
            last_error = str(exc)
            break
        except Exception as exc:  # noqa: BLE001
            # Retryable generic execution errors.
            last_error = str(exc)
            if attempt <= max_retries:
                continue
            break

    execution.status = "failure"
    execution.last_error = last_error
    execution.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(execution)

    if idempotency_record:
        mark_completed(
            db,
            idempotency_record,
            status="failed",
            response_payload={
                "execution_id": execution.id,
                "status": execution.status,
                "error": execution.last_error,
            },
        )

    return execution
