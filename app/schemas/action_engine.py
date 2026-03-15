from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ApprovalStatus = Literal["pending", "approved", "rejected", "expired"]
ExecutionStatus = Literal["queued", "running", "success", "failure", "rollback"]


class ActionRequestCreate(BaseModel):
    action_type: str = Field(min_length=3, max_length=50)
    action_payload: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=120)
    expires_in_hours: int = Field(default=24, ge=1, le=168)


class ActionDecisionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class ActionRequestResponse(BaseModel):
    id: int
    user_id: str
    action_type: str
    action_payload: dict
    policy_snapshot: dict | None
    status: ApprovalStatus
    idempotency_key: str | None
    expires_at: datetime
    decided_at: datetime | None
    decision_reason: str | None
    linked_execution_id: int | None
    created_at: datetime
    updated_at: datetime
    replayed: bool = False


class ActionExecutionResponse(BaseModel):
    id: int
    user_id: str
    approval_request_id: int | None
    action_type: str
    status: ExecutionStatus
    idempotency_key: str | None
    request_payload: dict
    result_payload: dict | None
    attempt_count: int
    max_retries: int
    last_error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActionRequestCreateResult(BaseModel):
    request: ActionRequestResponse
    execution: ActionExecutionResponse | None = None


class ActionDecisionResult(BaseModel):
    request: ActionRequestResponse
    execution: ActionExecutionResponse | None = None
