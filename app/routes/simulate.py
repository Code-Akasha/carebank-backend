from fastapi import APIRouter
from pydantic import BaseModel

from app.services.data import generate_mock_transactions
from app.services.forecast import forecast_balance
from app.core.finance import forecast_impact

router = APIRouter(prefix="/api/simulate", tags=["simulate"])


class SimulateRequest(BaseModel):
    user_id: str
    expense_amount: float
    category: str = "general"
    description: str = ""


class SimulateResponse(BaseModel):
    current_forecast: dict
    simulated_forecast: dict
    impact: dict
    explanation: str
    suggestions: list[dict] = []


@router.post("", response_model=SimulateResponse)
def simulate(request: SimulateRequest):
    """
    What-If Simulator — runs dual forecast (with/without expense).
    Uses Deterministic Core for impact calculation.
    """
    transactions = generate_mock_transactions(request.user_id)

    # Current forecast (without expense)
    current = forecast_balance(transactions)
    current_balance = current["predicted_balance"]

    # Simulated balance (Deterministic Core)
    simulated_balance = forecast_impact(
        current_balance=current_balance,
        scheduled_expenses=0,
        simulated_expense=request.expense_amount,
    )

    impact_amount = simulated_balance - current_balance
    retained_pct = (
        (simulated_balance / current_balance * 100) if current_balance > 0 else 0
    )

    if retained_pct > 70:
        risk_level = "low"
    elif retained_pct > 30:
        risk_level = "medium"
    else:
        risk_level = "high"

    explanation = (
        f"With this ₹{request.expense_amount:,.0f} {request.category} expense, "
        f"your projected balance drops from ₹{current_balance:,.0f} to ₹{simulated_balance:,.0f}. "
        f"Risk level: {risk_level}."
    )

    suggestions = []
    if risk_level in ("medium", "high"):
        suggestions.append(
            {
                "type": "product",
                "name": "3-Month EMI",
                "description": f"Split into 3 payments of ₹{request.expense_amount / 3:,.0f}",
            }
        )

    return SimulateResponse(
        current_forecast={
            "end_of_month_balance": current_balance,
            "confidence": 1.0 - current.get("forecast_error", 0.5),
        },
        simulated_forecast={
            "end_of_month_balance": simulated_balance,
            "confidence": 1.0 - current.get("forecast_error", 0.5),
        },
        impact={
            "amount": impact_amount,
            "risk_level": risk_level,
            "retained_percentage": round(retained_pct, 1),
        },
        explanation=explanation,
        suggestions=suggestions,
    )
