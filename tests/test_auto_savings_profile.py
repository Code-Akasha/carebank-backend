from types import SimpleNamespace

from app.agents.auto_savings import AutoSavingsAgent


def test_safety_threshold_respects_profile_floor():
    agent = AutoSavingsAgent()
    profile = SimpleNamespace(
        min_safe_balance=20000, savings_goal_pct=0.25, monthly_salary=120000
    )
    accounts = [
        {
            "account_type": "checking",
            "available_balance": 10000,
            "current_balance": 10000,
        }
    ]

    threshold = agent._derive_safety_threshold(accounts, profile)
    assert threshold == 20000.0


def test_target_savings_ratio_is_clamped():
    agent = AutoSavingsAgent()

    high_profile = SimpleNamespace(
        savings_goal_pct=0.9, min_safe_balance=5000, monthly_salary=100000
    )
    low_profile = SimpleNamespace(
        savings_goal_pct=0.01, min_safe_balance=5000, monthly_salary=100000
    )

    assert agent._target_savings_ratio(high_profile) == 0.4
    assert agent._target_savings_ratio(low_profile) == 0.05
