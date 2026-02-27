def calculate_surplus(income: float, expenses: float) -> float:
    return max(0.0, income - expenses)

def forecast_impact(current_balance: float, scheduled_expenses: float, simulated_expense: float) -> float:
    """
    Calculates the end of month balance if a simulated expense is incurred.
    This guarantees accuracy for the What-If Simulator feature.
    """
    return current_balance - scheduled_expenses - simulated_expense

def check_eligibility(user_profile: dict, product_rules: dict) -> bool:
    """
    Checks if a user is eligible for a product based on deterministic rules.
    Example:
    user_profile = {"credit_score": 750, "balance": 5000}
    product_rules = {"min_credit_score": 700, "min_balance": 1000}
    """
    for rule_key, required_value in product_rules.items():
        # Map product rule keys to user profile keys if necessary, or assume direct match
        user_key = rule_key.replace("min_", "").replace("max_", "")
        user_val = user_profile.get(user_key)
        
        if user_val is None:
            return False
        
        if rule_key.startswith("min_"):
            if user_val < required_value:
                return False
        elif rule_key.startswith("max_"):
            if user_val > required_value:
                return False
        elif user_val != required_value:
            return False
            
    return True


def calculate_health_score(
    savings_ratio: float,
    expense_variance: float,
    liquidity_days: float,
    forecast_error: float,
) -> dict:
    """
    Composite Financial Health Score (0-100) from 4 equally-weighted factors.
    All financial calculations happen here — NO LLM involvement.

    Args:
        savings_ratio: fraction of income saved (target 0.20 = 20%)
        expense_variance: month-over-month expense variance (0 = stable, 1 = volatile)
        liquidity_days: days of expenses covered by current balance
        forecast_error: Prophet prediction error margin (0 = perfect, 1 = useless)

    Returns:
        dict with total score + per-factor breakdown
    """
    factors = {
        "savings": {
            "value": savings_ratio,
            "score": round(min(savings_ratio / 0.20, 1.0) * 25, 1),
            "label": "Good" if savings_ratio >= 0.15 else "Needs Work",
        },
        "stability": {
            "value": expense_variance,
            "score": round(max(1 - expense_variance, 0) * 25, 1),
            "label": "Stable" if expense_variance < 0.3 else "Volatile",
        },
        "liquidity": {
            "value": liquidity_days,
            "score": round(min(liquidity_days / 30, 1.0) * 25, 1),
            "label": "Good" if liquidity_days >= 15 else "Low",
        },
        "confidence": {
            "value": forecast_error,
            "score": round(max(1 - forecast_error, 0) * 25, 1),
            "label": "High" if forecast_error < 0.2 else "Low",
        },
    }

    total = round(sum(f["score"] for f in factors.values()), 1)

    return {"score": total, "factors": factors}
