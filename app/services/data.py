from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def generate_mock_transactions(
    user_id: str = "user_001",
    days: int = 90,
    base_daily_spend: float = 500.0,
) -> list[dict[str, Any]]:
    """Generate realistic mock transaction data for ML services."""
    import random

    random.seed(42)
    categories = ["food", "transport", "entertainment", "shopping", "bills", "other"]
    weights = [0.30, 0.15, 0.20, 0.15, 0.15, 0.05]
    merchants = {
        "food": ["Swiggy", "Zomato", "BigBasket", "DMart"],
        "transport": ["Uber", "Ola", "Metro", "PetrolPump"],
        "entertainment": ["Netflix", "BookMyShow", "Spotify"],
        "shopping": ["Amazon", "Flipkart", "Myntra"],
        "bills": ["Electricity", "Internet", "Mobile"],
        "other": ["ATM", "Transfer", "Misc"],
    }

    transactions: list[dict] = []
    today = datetime.now(timezone.utc).date()

    for day_offset in range(days, 0, -1):
        date = today - timedelta(days=day_offset)
        num_txns = random.randint(1, 4)

        for _ in range(num_txns):
            cat = random.choices(categories, weights=weights, k=1)[0]
            amount = round(base_daily_spend * random.uniform(0.2, 2.5) * weights[categories.index(cat)] * 3, 2)
            transactions.append({
                "user_id": user_id,
                "date": datetime.combine(date, datetime.min.time()),
                "amount": -amount,
                "category": cat,
                "merchant": random.choice(merchants[cat]),
            })

        # Periodic income (every 30 days)
        if day_offset % 30 == 0:
            transactions.append({
                "user_id": user_id,
                "date": datetime.combine(date, datetime.min.time()),
                "amount": 50000.0,
                "category": "income",
                "merchant": "Salary",
            })

    return transactions


def aggregate_spending_profile(transactions: list[dict]) -> dict[str, float]:
    """Calculate spending percentage by category for clustering."""
    category_totals: dict[str, float] = {}
    total_spend = 0.0

    for txn in transactions:
        if txn["amount"] < 0:
            cat = txn.get("category", "other")
            abs_amount = abs(txn["amount"])
            category_totals[cat] = category_totals.get(cat, 0.0) + abs_amount
            total_spend += abs_amount

    if total_spend == 0:
        return {}

    return {cat: round(amt / total_spend, 4) for cat, amt in category_totals.items()}


def calculate_monthly_stats(transactions: list[dict]) -> dict:
    """Calculate income, expenses, savings ratio, and expense variance."""
    monthly: dict[str, dict[str, float]] = {}

    for txn in transactions:
        month_key = txn["date"].strftime("%Y-%m")
        if month_key not in monthly:
            monthly[month_key] = {"income": 0.0, "expenses": 0.0}

        if txn["amount"] > 0:
            monthly[month_key]["income"] += txn["amount"]
        else:
            monthly[month_key]["expenses"] += abs(txn["amount"])

    months = sorted(monthly.keys())
    if not months:
        return {"income": 0, "expenses": 0, "savings_ratio": 0, "expense_variance": 0}

    latest = monthly[months[-1]]
    income = latest["income"] if latest["income"] > 0 else 50000.0
    expenses = latest["expenses"]
    savings_ratio = max(0, (income - expenses) / income) if income > 0 else 0

    # Month-over-month expense variance
    expense_values = [monthly[m]["expenses"] for m in months if monthly[m]["expenses"] > 0]
    if len(expense_values) >= 2:
        import numpy as np
        mean_exp = np.mean(expense_values)
        std_exp = np.std(expense_values)
        expense_variance = float(std_exp / mean_exp) if mean_exp > 0 else 0
    else:
        expense_variance = 0.0

    return {
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "savings_ratio": round(savings_ratio, 4),
        "expense_variance": round(min(expense_variance, 1.0), 4),
    }
