from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.agents.coordinator import coordinator_graph
from app.core.database import get_db
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    response: str
    intent: str
    agent_used: str


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, db: DBSession = Depends(get_db)):
    result = coordinator_graph.invoke(
        {
            "user_id": request.user_id,
            "message": request.message,
            "audit_log": [],
            "conversation_history": [],
        }
    )

    # Persist audit log entry
    audit_entry = AuditLog(
        user_id=request.user_id,
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
