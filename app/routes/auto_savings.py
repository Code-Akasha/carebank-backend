"""Auto-Savings endpoints: trigger agent recommendations and approve micro-transfers."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.agents.auto_savings import AutoSavingsAgent
from app.agents.base import AgentInput
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.routes.events import push_event
from app.services.banking_client import BankingClient, BankingClientError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auto-savings", tags=["auto-savings"])

_agent = AutoSavingsAgent()


class SavingsRecommendation(BaseModel):
    suggested_amount: int = 0
    goal_progress: float = 0.0
    safety_threshold: float = 0.0
    message: str = ""


class ApproveRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Amount to transfer to savings")


class ApproveResponse(BaseModel):
    success: bool
    message: str
    transaction_id: str | None = None


@router.get("/recommend", response_model=SavingsRecommendation)
def get_recommendation(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get auto-savings recommendation based on current financial forecast."""
    result = _agent._invoke(
        AgentInput(user_id=current_user.user_id, message="auto savings recommendation")
    )
    metadata = result.metadata or {}
    return SavingsRecommendation(
        suggested_amount=metadata.get("suggested_amount", 0),
        goal_progress=metadata.get("goal_progress", 0.0),
        safety_threshold=metadata.get("safety_threshold", 0.0),
        message=result.response,
    )


@router.post("/approve", response_model=ApproveResponse)
async def approve_savings(
    request: ApproveRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: DBSession = Depends(get_db),
):
    """Approve and execute a micro-savings transfer."""
    user_id = current_user.user_id

    # Validate amount against recommendation
    result = _agent._invoke(
        AgentInput(user_id=user_id, message="auto savings recommendation")
    )
    metadata = result.metadata or {}
    max_suggested = metadata.get("suggested_amount", 0)

    if request.amount > max_suggested > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Requested amount ₹{request.amount} exceeds recommended maximum ₹{max_suggested}",
        )

    if request.amount < 50:
        raise HTTPException(
            status_code=400,
            detail="Minimum savings transfer is ₹50",
        )

    # Execute the transfer via MockBank
    try:
        client = BankingClient()
        tx_result = await client.trigger_transaction({
            "user_id": user_id,
            "amount": request.amount,
            "type": "debit",
            "category": "savings",
            "merchant": "CareBank Auto-Savings",
            "description": f"Auto-savings transfer: ₹{request.amount}",
        })

        transaction_id = tx_result.get("transaction_id") or tx_result.get("id", "")

        # Push real-time event
        push_event(user_id, "auto_savings_completed", {
            "amount": request.amount,
            "transaction_id": str(transaction_id),
        })

        # Persist notification
        from app.services.notification_service import notify_savings_transfer
        notify_savings_transfer(
            db,
            user_id=user_id,
            amount=request.amount,
            transaction_id=str(transaction_id),
        )

        return ApproveResponse(
            success=True,
            message=f"Successfully transferred ₹{request.amount} to savings!",
            transaction_id=str(transaction_id),
        )

    except BankingClientError as exc:
        logger.error("Auto-savings transfer failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Banking service error: {exc}",
        )
