from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.agents.coordinator import coordinator_graph, get_conversation_history
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    user_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    intent: str
    agent_used: str


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

    result = coordinator_graph.invoke(
        {
            "user_id": user_id,
            "message": request.message,
            "audit_log": [],
            "conversation_history": history,
        }
    )

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
