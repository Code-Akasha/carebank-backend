from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.health_score import compute_health_score
from app.services.banking_client import get_banking_client, BankingClientError

router = APIRouter(prefix="/api/health-score", tags=["health-score"])


class HealthScoreResponse(BaseModel):
    score: float
    factors: dict
    persona: dict | None = None
    forecast: dict | None = None
    stats: dict | None = None


@router.get("/{user_id}", response_model=HealthScoreResponse)
async def get_health_score(user_id: str):
    client = get_banking_client()
    try:
        transactions = await client.get_transactions(user_id)
        balance = await client.get_balance(user_id)
    except BankingClientError as exc:
        raise HTTPException(
            status_code=503, detail=f"Banking API unavailable: {exc}"
        ) from exc

    result = compute_health_score(
        user_id,
        transactions=transactions,
        current_balance=balance.get("current_balance", 0.0),
    )
    return result
