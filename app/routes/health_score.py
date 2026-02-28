from fastapi import APIRouter
from pydantic import BaseModel

from app.services.health_score import compute_health_score

router = APIRouter(prefix="/api/health-score", tags=["health-score"])


class HealthScoreResponse(BaseModel):
    score: float
    factors: dict
    persona: dict | None = None
    forecast: dict | None = None
    stats: dict | None = None


@router.get("/{user_id}", response_model=HealthScoreResponse)
def get_health_score(user_id: str):
    """
    Health Score endpoint — dynamically computed from ML pipeline + Deterministic Core.
    Uses mock transaction data for MVP; real DB integration in Phase 5.
    """
    result = compute_health_score(user_id)
    return result
