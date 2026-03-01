from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.data import generate_mock_transactions
from app.services.forecast import forecast_balance
from app.core.finance import forecast_impact
from app.services.mockbank_client import get_mockbank_client, MockBankClientError

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
async def simulate(request: SimulateRequest):
    client = get_mockbank_client()
    try:
        transactions = await client.get_transactions(request.user_id)
        balance = await client.get_balance(request.user_id)
    except MockBankClientError as exc:
        raise HTTPException(status_code=503, detail=f"MockBank unavailable: {exc}") from exc

    if not transactions:
        transactions = generate_mock_transactions(request.user_id)

    current = forecast_balance(transactions)
    base_balance = balance.get("current_balance", current.get("predicted_balance", 0.0))

    simulated_balance = forecast_impact(
        current_balance=base_balance,
        scheduled_expenses=0,
        simulated_expense=request.expense_amount,
    )

    impact_amount = simulated_balance - base_balance
    retained_pct = (simulated_balance / base_balance * 100) if base_balance > 0 else 0

    if retained_pct > 70:
        risk_level = "low"
    elif retained_pct > 30:
        risk_level = "medium"
    else:
        risk_level = "high"

    explanation = (
        f"With this ₹{request.expense_amount:,.0f} {request.category} expense, "
        f"your projected balance drops from ₹{base_balance:,.0f} to ₹{simulated_balance:,.0f}. "
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
        current_forecast=current,
        simulated_forecast={"predicted_balance": simulated_balance},
        impact={"amount": impact_amount, "retained_pct": retained_pct, "risk_level": risk_level},
        explanation=explanation,
        suggestions=suggestions,
    )
