from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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
from app.routes.planning import create_schedule_from_text
from app.schemas.planning import ScheduleFromTextRequest

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    user_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    intent: str
    agent_used: str


def _apply_chat_actions(
    *,
    result: dict,
    current_user: User,
    db: DBSession,
) -> dict:
    if str(result.get("intent") or "").lower() != "planning":
        return result

    metadata = result.get("response_metadata") or {}
    if not isinstance(metadata, dict):
        return result

    action = metadata.get("action")
    if not isinstance(action, dict):
        return result

    action_type = action.get("type")
    if action_type != "create_schedule_from_text":
        return result

    text = str(action.get("text") or "").strip()
    if not text:
        return result

    default_amount_raw = action.get("default_amount", 0)
    try:
        default_amount = float(default_amount_raw or 0)
    except (TypeError, ValueError):
        default_amount = 0.0

    body = ScheduleFromTextRequest(
        text=text,
        default_amount=default_amount,
        autopay_enabled=bool(action.get("autopay_enabled", True)),
        requires_approval=bool(action.get("requires_approval", True)),
    )

    try:
        created = create_schedule_from_text(body, current_user=current_user, db=db)
    except Exception as exc:  # noqa: BLE001
        result["agent_response"] = (
            f"I parsed your scheduling request, but execution failed. Reason: {exc}"
        )
        result["response_metadata"] = {
            **metadata,
            "clear_pending": False,
        }
        return result

    rule = created.get("rule")
    extracted = created.get("extracted") or {}

    day_of_month = extracted.get("day_of_month")
    amount = extracted.get("amount")
    title = extracted.get("title")
    category = extracted.get("category")

    if hasattr(rule, "id"):
        rule_id = getattr(rule, "id", None)
    elif isinstance(rule, dict):
        rule_id = rule.get("id")
    else:
        rule_id = None

    result["agent_response"] = (
        f"Done. I created your recurring schedule: {title or 'payment'} "
        f"for INR {float(amount or 0):,.2f} on day {day_of_month}. "
        f"Category: {category or 'custom'}."
        + (f" Rule ID: {rule_id}." if rule_id is not None else "")
    )
    result["response_metadata"] = {
        **metadata,
        "clear_pending": True,
        "action_result": {
            "type": "create_schedule_from_text",
            "rule_id": rule_id,
            "day_of_month": day_of_month,
            "amount": amount,
            "category": category,
        },
    }
    return result


@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: DBSession = Depends(get_db),
):
    if request.user_id and request.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Cannot chat as another user")

    user_id = current_user.user_id
    history = get_conversation_history(user_id)
    conversation_state = get_conversation_state(user_id)

    result = coordinator_graph.invoke(
        {
            "user_id": user_id,
            "message": request.message,
            "audit_log": [],
            "conversation_history": history,
            "conversation_state": conversation_state,
        }
    )

    if result.get("pending_intent_ignored"):
        clear_conversation_state(user_id)
        conversation_state = {}

    result = _apply_chat_actions(
        result=result,
        current_user=current_user,
        db=db,
    )

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
    )
