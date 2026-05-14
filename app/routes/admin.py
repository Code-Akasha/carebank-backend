from __future__ import annotations

import asyncio

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


class WebhookReplayRequest(BaseModel):
    webhook_url: str | None = None


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
    bulk_balances: dict[str, dict] = {}
    try:
        upstream_users = await client.get_admin_users(page=1, per_page=500)
        bulk_balances = {
            str(item.get("user_id")): item
            for item in upstream_users
            if isinstance(item, dict) and item.get("user_id")
        }
    except BankingClientError:
        bulk_balances = {}

    async def build_user_entry(u: User) -> dict:
        entry = {
            "user_id": u.user_id,
            "email": u.email,
            "full_name": u.full_name,
            "is_active": u.is_active,
        }
        if u.user_id in bulk_balances:
            entry["current_balance"] = bulk_balances[u.user_id].get(
                "current_balance", 0.0
            )
            entry["available_balance"] = bulk_balances[u.user_id].get(
                "available_balance", 0.0
            )
            return entry
        try:
            balance = await client.get_balance(u.user_id)
            entry["current_balance"] = balance.get("current_balance", 0.0)
            entry["available_balance"] = balance.get("available_balance", 0.0)
        except BankingClientError:
            entry["current_balance"] = None
            entry["available_balance"] = None
        return entry

    user_list = await asyncio.gather(*(build_user_entry(u) for u in users))

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
            status_code=exc.status_code or 503,
            detail=f"Banking API unavailable: {exc}",
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
            status_code=exc.status_code or 503,
            detail=f"Banking API unavailable: {exc}",
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
            status_code=exc.status_code or 503,
            detail=f"Banking API unavailable: {exc}",
        ) from exc


@router.get("/webhooks/dead-letter")
async def admin_webhook_dead_letters(
    status_filter: str | None = None,
    _admin: User = Depends(require_admin),
):
    client = get_banking_client()
    try:
        response = await client.get_webhook_dead_letters(status_filter=status_filter)
    except BankingClientError as exc:
        raise HTTPException(
            status_code=exc.status_code or 503,
            detail=f"Banking API unavailable: {exc}",
        ) from exc

    records = response.get("records", []) if isinstance(response, dict) else []
    normalized = []
    for record in records:
        payload = record.get("payload") or {}
        attempts = record.get("attempts") or []
        last_error = record.get("last_error")
        if not last_error and attempts:
            last_attempt = attempts[-1]
            if isinstance(last_attempt, dict):
                last_error = last_attempt.get("error")
        normalized.append(
            {
                "id": record.get("id"),
                "event_type": payload.get("event_type") or record.get("event_type"),
                "payload": payload,
                "failed_at": record.get("created_at"),
                "attempts": record.get("attempt_count") or len(attempts),
                "last_error": last_error,
                "status": record.get("status"),
            }
        )

    return {
        "count": len(normalized),
        "records": normalized,
    }


@router.post("/webhooks/dead-letter/{dead_letter_id}/replay")
async def admin_webhook_replay_dead_letter(
    dead_letter_id: str,
    body: WebhookReplayRequest | None = None,
    _admin: User = Depends(require_admin),
):
    client = get_banking_client()
    try:
        return await client.replay_webhook_dead_letter(
            dead_letter_id,
            webhook_url=(body.webhook_url if body else None),
        )
    except BankingClientError as exc:
        raise HTTPException(
            status_code=exc.status_code or 503,
            detail=f"Banking API unavailable: {exc}",
        ) from exc
