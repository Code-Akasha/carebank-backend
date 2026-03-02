from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_admin
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.banking_client import get_banking_client, BankingClientError

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UserSummary(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    is_active: bool


class SimulationToggleRequest(BaseModel):
    enabled: bool


class ScenarioTriggerRequest(BaseModel):
    user_id: str
    scenario_type: str


@router.get("/users")
async def admin_list_users(
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = db.query(User).filter(User.role == "user")
    if search:
        query = query.filter(
            (User.full_name.ilike(f"%{search}%"))
            | (User.email.ilike(f"%{search}%"))
            | (User.user_id.ilike(f"%{search}%"))
        )

    total = query.count()
    users = (
        query.order_by(User.user_id).offset((page - 1) * per_page).limit(per_page).all()
    )

    client = get_banking_client()
    user_list = []
    for u in users:
        entry = {
            "user_id": u.user_id,
            "email": u.email,
            "full_name": u.full_name,
            "is_active": u.is_active,
        }
        try:
            balance = await client.get_balance(u.user_id)
            entry["current_balance"] = balance.get("current_balance", 0.0)
            entry["available_balance"] = balance.get("available_balance", 0.0)
        except BankingClientError:
            entry["current_balance"] = None
            entry["available_balance"] = None
        user_list.append(entry)

    return {"total": total, "page": page, "per_page": per_page, "users": user_list}


@router.get("/users/{user_id}")
async def admin_get_user(
    user_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    client = get_banking_client()
    result = {
        "user_id": user.user_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": str(user.created_at) if user.created_at else None,
    }

    try:
        result["balance"] = await client.get_balance(user_id)
        result["accounts"] = await client.get_accounts(user_id)
        result["recent_transactions"] = await client.get_transactions(user_id)
    except BankingClientError:
        result["balance"] = None
        result["accounts"] = []
        result["recent_transactions"] = []

    return result


@router.get("/agent-logs")
async def admin_agent_logs(
    page: int = 1,
    per_page: int = 50,
    user_id: str | None = None,
    agent_name: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = db.query(AuditLog)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if agent_name:
        query = query.filter(AuditLog.agent_used.ilike(f"%{agent_name}%"))

    total = query.count()
    logs = (
        query.order_by(AuditLog.timestamp.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "logs": [
            {
                "id": log.id,
                "session_id": log.session_id,
                "user_id": log.user_id,
                "user_message": log.user_message,
                "intent": log.intent,
                "agent_used": log.agent_used,
                "agent_response": log.agent_response,
                "timestamp": str(log.timestamp) if log.timestamp else None,
            }
            for log in logs
        ],
    }


@router.get("/agent-logs/{user_id}")
async def admin_agent_logs_for_user(
    user_id: str,
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = db.query(AuditLog).filter(AuditLog.user_id == user_id)
    total = query.count()
    logs = (
        query.order_by(AuditLog.timestamp.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "logs": [
            {
                "id": log.id,
                "session_id": log.session_id,
                "user_id": log.user_id,
                "user_message": log.user_message,
                "intent": log.intent,
                "agent_used": log.agent_used,
                "agent_response": log.agent_response,
                "timestamp": str(log.timestamp) if log.timestamp else None,
            }
            for log in logs
        ],
    }


@router.post("/simulation/toggle")
async def admin_simulation_toggle(
    body: SimulationToggleRequest,
    _admin: User = Depends(require_admin),
):
    client = get_banking_client()
    try:
        result = await client.toggle_simulation(body.enabled)
        return result
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503, detail=f"Banking API unavailable: {exc}"
        ) from exc


@router.get("/simulation/status")
async def admin_simulation_status(
    _admin: User = Depends(require_admin),
):
    client = get_banking_client()
    try:
        result = await client.get_simulation_status()
        return result
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503, detail=f"Banking API unavailable: {exc}"
        ) from exc


@router.post("/scenario")
async def admin_trigger_scenario(
    body: ScenarioTriggerRequest,
    _admin: User = Depends(require_admin),
):
    client = get_banking_client()
    try:
        result = await client.trigger_scenario(body.user_id, body.scenario_type)
        return result
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503, detail=f"Banking API unavailable: {exc}"
        ) from exc
