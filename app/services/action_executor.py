from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.action_execution import ActionExecution
from app.services.execution_error_handler import format_execution_error
from app.services.idempotency import (
    IdempotencyConflictError,
    hash_payload,
    mark_completed,
    reserve_or_replay,
)
from app.services.payload_validator import PayloadValidationError, validate_action_payload
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

    # VALIDATE PAYLOAD BEFORE EXECUTION
    is_valid, validation_errors = validate_action_payload(action_type, action_payload)
    if not is_valid:
        error_msg = "; ".join(validation_errors)
        validation_error = ValueError(error_msg)
        friendly_error = format_execution_error(validation_error, action_type)

        execution.status = "failure"
        execution.last_error = friendly_error.message
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

    tool_payload = dict(action_payload)
    tool_payload["_execution_id"] = execution.id
    if approval_request_id is not None:
        tool_payload["_approval_request_id"] = approval_request_id
    if idempotency_key:
        tool_payload["_execution_idempotency_key"] = idempotency_key

    # RETRY LOOP WITH EXPONENTIAL BACKOFF
    # Attempt 1: Immediate
    # Attempt 2: Wait 1 second before retry
    # Attempt 3: Wait 5 seconds before retry
    backoff_seconds = [0, 1, 5]  # Delays before each retry attempt
    last_error = None

    for attempt in range(1, max_retries + 2):
        # Apply backoff delay if this is a retry (not first attempt)
        if attempt > 1 and attempt - 2 < len(backoff_seconds):
            delay = backoff_seconds[attempt - 2]
            if delay > 0:
                time.sleep(delay)

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
        except (ToolNotFoundError, ValueError, IdempotencyConflictError, PayloadValidationError) as exc:
            # Non-retryable errors — fail immediately with user-friendly message
            friendly_error = format_execution_error(exc, action_type)
            last_error = friendly_error.message
            break
        except Exception as exc:  # noqa: BLE001
            # Retryable errors — continue if attempts remain
            friendly_error = format_execution_error(exc, action_type)
            last_error = friendly_error.message
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
