from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_current_user, require_admin
from app.models.user import User
from app.services.banking_client import BankingClientError, get_banking_client
from app.services.health_score import compute_health_score

router = APIRouter(prefix="/api/health-score", tags=["health-score"])


class HealthScoreResponse(BaseModel):
    score: float
    message: str
    factors: dict
    persona: dict | None = None
    forecast: dict | None = None
    stats: dict | None = None


def _score_to_message(score: float) -> str:
    if score >= 80:
        return "Excellent! Your finances are in great shape."
    if score >= 65:
        return "Good financial health. Keep up the momentum!"
    if score >= 50:
        return "Fair. There are a few areas to improve."
    if score >= 35:
        return "Your finances need attention. Let's work on a plan."
    return "Your financial health is at risk. Consider acting now."


@router.get("/", response_model=HealthScoreResponse)
async def get_my_health_score(
    current_user: Annotated[User, Depends(get_current_user)],
):
    client = get_banking_client()
    try:
        transactions = await client.get_transactions(current_user.user_id)
        balance = await client.get_balance(current_user.user_id)
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Banking API unavailable: {exc}",
        ) from exc

    result = compute_health_score(
        current_user.user_id,
        transactions=transactions,
        current_balance=balance.get("current_balance", 0.0),
    )
    result["message"] = _score_to_message(result.get("score", 0))
    return result


@router.get("/{user_id}", response_model=HealthScoreResponse)
async def get_health_score(
    user_id: str,
    _admin: User = Depends(require_admin),
):
    """Legacy endpoint for admin use — now restricted to admins."""
    client = get_banking_client()
    try:
        transactions = await client.get_transactions(user_id)
        balance = await client.get_balance(user_id)
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Banking API unavailable: {exc}",
        ) from exc

    result = compute_health_score(
        user_id,
        transactions=transactions,
        current_balance=balance.get("current_balance", 0.0),
    )
    result["message"] = _score_to_message(result.get("score", 0))
    return result
