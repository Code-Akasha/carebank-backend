from fastapi import APIRouter
from app.core.finance import calculate_health_score
from app.schemas.models import HealthScoreResponse

router = APIRouter(prefix="/api/health-score", tags=["health-score"])


@router.get("/{user_id}", response_model=HealthScoreResponse)
def get_health_score(user_id: str):
    """
    Health Score endpoint.
    Currently returns a deterministic calculation from placeholder values.
    In Phase 3, this will pull real data from the Intelligence Agent (Prophet forecasts)
    and the database (savings ratio, expense variance, liquidity days).
    """
    result = calculate_health_score(
        savings_ratio=0.18,
        expense_variance=0.15,
        liquidity_days=12.0,
        forecast_error=0.10,
    )
    return result
