from app.core.finance import calculate_surplus, forecast_impact, check_eligibility

def test_calculate_surplus():
    assert calculate_surplus(5000, 3000) == 2000
    assert calculate_surplus(2000, 3000) == 0.0

def test_forecast_impact():
    # current_balance = 5000, scheduled = 2000, simulated = 1000
    assert forecast_impact(5000, 2000, 1000) == 2000
    assert forecast_impact(1000, 500, 1000) == -500

def test_check_eligibility():
    user = {"credit_score": 750, "balance": 5000}
    rules = {"min_credit_score": 700, "min_balance": 1000}
    assert check_eligibility(user, rules) == True

    user2 = {"credit_score": 650, "balance": 5000}
    assert check_eligibility(user2, rules) == False
