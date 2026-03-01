from __future__ import annotations

from app.core.finance import calculate_health_score
from app.services.data import (
    calculate_monthly_stats,
    aggregate_spending_profile,
    generate_mock_transactions,
)
from app.services.forecast import forecast_balance
from app.services.clustering import cluster_persona


def compute_health_score(
    user_id: str,
    transactions: list[dict] | None = None,
    current_balance: float | None = None,
) -> dict:
    """
    Full Health Score computation pipeline.

    1. Get transactions (or generate mock data)
    2. Calculate savings_ratio & expense_variance from monthly stats
    3. Calculate liquidity_days from balance / avg daily expense
    4. Get forecast_error from Prophet forecast
    5. Get persona from clustering
    6. Pass to Deterministic Core for final score
    """
    if not transactions:
        transactions = generate_mock_transactions(user_id)

    if current_balance is None:
        current_balance = 25000.0

    # Monthly financial stats
    stats = calculate_monthly_stats(transactions)
    savings_ratio = stats["savings_ratio"]
    expense_variance = stats["expense_variance"]

    # Liquidity days
    daily_expense = stats["expenses"] / 30 if stats["expenses"] > 0 else 1.0
    liquidity_days = current_balance / daily_expense if daily_expense > 0 else 30.0

    # Forecast error from Prophet
    forecast = forecast_balance(transactions)
    forecast_error = forecast.get("forecast_error", 0.5)

    # Persona clustering
    profile = aggregate_spending_profile(transactions)
    persona = cluster_persona(profile)

    # Deterministic Core — source of truth for the score
    score_result = calculate_health_score(
        savings_ratio=savings_ratio,
        expense_variance=expense_variance,
        liquidity_days=liquidity_days,
        forecast_error=forecast_error,
    )

    # Enrich with additional context
    score_result["persona"] = persona
    score_result["forecast"] = {
        "predicted_balance": forecast.get("predicted_balance", 0),
        "forecast_error": forecast_error,
    }
    score_result["stats"] = stats

    return score_result
