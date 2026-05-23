from app.core.finance import (
    calculate_health_score,
    calculate_surplus,
    check_eligibility,
    forecast_impact,
)


def test_calculate_surplus():
    assert calculate_surplus(5000, 3000) == 2000
    assert calculate_surplus(2000, 3000) == 0.0


def test_forecast_impact():
    assert forecast_impact(5000, 2000, 1000) == 2000
    assert forecast_impact(1000, 500, 1000) == -500


def test_check_eligibility():
    user = {"credit_score": 750, "balance": 5000}
    rules = {"min_credit_score": 700, "min_balance": 1000}
    assert check_eligibility(user, rules) is True

    user2 = {"credit_score": 650, "balance": 5000}
    assert check_eligibility(user2, rules) is False


def test_health_score_perfect():
    result = calculate_health_score(
        savings_ratio=0.20,
        expense_variance=0.0,
        liquidity_days=30.0,
        forecast_error=0.0,
    )
    assert result["score"] == 100.0
    assert result["factors"]["savings"]["score"] == 25.0
    assert result["factors"]["stability"]["score"] == 25.0
    assert result["factors"]["liquidity"]["score"] == 25.0
    assert result["factors"]["confidence"]["score"] == 25.0


def test_health_score_zero():
    result = calculate_health_score(
        savings_ratio=0.0,
        expense_variance=1.0,
        liquidity_days=0.0,
        forecast_error=1.0,
    )
    assert result["score"] == 0.0


def test_health_score_mixed():
    result = calculate_health_score(
        savings_ratio=0.18,
        expense_variance=0.15,
        liquidity_days=12.0,
        forecast_error=0.10,
    )
    assert 0 < result["score"] < 100
    assert result["factors"]["savings"]["label"] == "Good"
    assert result["factors"]["stability"]["label"] == "Stable"
    assert result["factors"]["liquidity"]["label"] == "Low"
    assert result["factors"]["confidence"]["label"] == "High"


def test_health_score_labels():
    result = calculate_health_score(
        savings_ratio=0.05,
        expense_variance=0.5,
        liquidity_days=5.0,
        forecast_error=0.5,
    )
    assert result["factors"]["savings"]["label"] == "Needs Work"
    assert result["factors"]["stability"]["label"] == "Volatile"
    assert result["factors"]["liquidity"]["label"] == "Low"
    assert result["factors"]["confidence"]["label"] == "Low"
