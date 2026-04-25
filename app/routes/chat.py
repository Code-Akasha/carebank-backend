import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.agents.coordinator import (
    clear_conversation_state,
    coordinator_graph,
    get_conversation_history,
    get_conversation_state,
    set_conversation_state,
)
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ---------------------------------------------------------------------------
# Rate limiter: 10 requests per 60 seconds per user (token bucket)
# ---------------------------------------------------------------------------
_RATE_LIMIT = 10
_RATE_WINDOW = 60.0
_user_request_log: dict[str, list[float]] = {}


def _check_rate_limit(user_id: str) -> None:
    now = time.monotonic()
    timestamps = _user_request_log.get(user_id, [])
    timestamps = [t for t in timestamps if now - t < _RATE_WINDOW]
    if len(timestamps) >= _RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {_RATE_LIMIT} messages per minute.",
        )
    timestamps.append(now)
    _user_request_log[user_id] = timestamps


class ChatRequest(BaseModel):
    message: str
    user_id: str | None = None


class ChatUIAction(BaseModel):
    label: str
    message: str


class ChatResponse(BaseModel):
    response: str
    intent: str
    agent_used: str
    ui_actions: list[ChatUIAction] = Field(default_factory=list)


@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: DBSession = Depends(get_db),
):
    if request.user_id and request.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Cannot chat as another user")

    user_id = current_user.user_id
    _check_rate_limit(user_id)

    history = get_conversation_history(user_id)
    conversation_state = get_conversation_state(user_id)

    result = coordinator_graph.invoke(
        {
            "user_id": user_id,
            "message": request.message,
            "audit_log": [],
            "conversation_history": history,
            "conversation_state": conversation_state,
            "db": db,
            "current_user": current_user,
        }
    )

    if result.get("pending_intent_ignored"):
        clear_conversation_state(user_id)
        conversation_state = {}

    response_metadata = result.get("response_metadata") or {}
    if isinstance(response_metadata, dict):
        if response_metadata.get("clear_pending"):
            clear_conversation_state(user_id)
        else:
            pending_state = response_metadata.get("pending_state")
            if isinstance(pending_state, dict):
                next_state = {
                    **conversation_state,
                    **pending_state,
                }
                set_conversation_state(user_id, next_state)

    ui_actions: list[dict] = []
    if isinstance(response_metadata, dict):
        raw_ui_actions = response_metadata.get("ui_actions")
        if isinstance(raw_ui_actions, list):
            for item in raw_ui_actions:
                if not isinstance(item, dict):
                    continue
                label = item.get("label")
                message = item.get("message")
                if isinstance(label, str) and isinstance(message, str):
                    ui_actions.append({"label": label, "message": message})

    # Persist audit log entry
    audit_entry = AuditLog(
        user_id=user_id,
        user_message=request.message,
        intent=result.get("intent", "unknown"),
        agent_used=result.get("agent_used", "unknown"),
        agent_response=result.get("agent_response", ""),
    )
    db.add(audit_entry)
    db.commit()

    return ChatResponse(
        response=result.get("agent_response", ""),
        intent=result.get("intent", "unknown"),
        agent_used=result.get("agent_used", "unknown"),
        ui_actions=ui_actions,
    )
