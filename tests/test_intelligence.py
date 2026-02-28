import pytest
import numpy as np

from app.services.data import generate_mock_transactions, aggregate_spending_profile, calculate_monthly_stats
from app.services.forecast import forecast_balance
from app.services.clustering import cluster_persona, PERSONAS
from app.services.anomaly import detect_anomaly
from app.services.health_score import compute_health_score
from app.agents.intelligence import IntelligenceAgent
from app.agents.base import AgentInput


# ── Data helpers ──────────────────────────────────────────────────────

class TestDataHelpers:
    def test_generate_mock_transactions(self):
        txns = generate_mock_transactions("test_user", days=30)
        assert len(txns) > 10
        assert all("date" in t and "amount" in t and "category" in t for t in txns)

    def test_aggregate_spending_profile(self):
        txns = generate_mock_transactions("test_user")
        profile = aggregate_spending_profile(txns)
        assert len(profile) > 0
        total = sum(profile.values())
        assert 0.99 <= total <= 1.01  # percentages sum ~1.0

    def test_calculate_monthly_stats(self):
        txns = generate_mock_transactions("test_user")
        stats = calculate_monthly_stats(txns)
        assert stats["income"] > 0
        assert stats["expenses"] > 0
        assert 0 <= stats["savings_ratio"] <= 1

    def test_empty_transactions(self):
        stats = calculate_monthly_stats([])
        assert stats["income"] == 0


# ── Forecast service ──────────────────────────────────────────────────

class TestForecast:
    def test_forecast_generates_prediction(self):
        txns = generate_mock_transactions("test_user", days=60)
        result = forecast_balance(txns, periods=30)
        assert "predicted_balance" in result
        assert "forecast_error" in result
        assert 0 <= result["forecast_error"] <= 1.0

    def test_forecast_few_datapoints_fallback(self):
        txns = [
            {"date": "2026-01-01T00:00:00", "amount": -500},
            {"date": "2026-01-02T00:00:00", "amount": -300},
        ]
        result = forecast_balance(txns, periods=10)
        assert "predicted_balance" in result

    def test_forecast_empty_returns_zeros(self):
        result = forecast_balance([], periods=10)
        assert result["predicted_balance"] == 0.0
        assert result["forecast_error"] == 1.0


# ── Clustering service ────────────────────────────────────────────────

class TestClustering:
    def test_cautious_saver(self):
        profile = {"food": 0.15, "transport": 0.10, "entertainment": 0.10,
                   "shopping": 0.10, "bills": 0.50, "other": 0.05}
        result = cluster_persona(profile)
        assert result["persona"] == "Cautious Saver"
        assert result["cluster_id"] == 0

    def test_social_spender(self):
        profile = {"food": 0.35, "transport": 0.10, "entertainment": 0.30,
                   "shopping": 0.10, "bills": 0.10, "other": 0.05}
        result = cluster_persona(profile)
        assert result["persona"] == "Social Spender"

    def test_impulse_buyer(self):
        profile = {"food": 0.20, "transport": 0.05, "entertainment": 0.15,
                   "shopping": 0.40, "bills": 0.10, "other": 0.10}
        result = cluster_persona(profile)
        assert result["persona"] == "Impulse Buyer"

    def test_returns_valid_persona(self):
        profile = {"food": 0.25, "transport": 0.15, "entertainment": 0.15,
                   "shopping": 0.15, "bills": 0.25, "other": 0.05}
        result = cluster_persona(profile)
        assert result["persona"] in PERSONAS
        assert 0 <= result["confidence"] <= 1

    def test_empty_profile_defaults(self):
        result = cluster_persona({})
        assert result["persona"] == "Balanced Manager"

    def test_different_profiles_different_personas(self):
        saver = {"food": 0.15, "transport": 0.10, "entertainment": 0.10,
                 "shopping": 0.10, "bills": 0.50, "other": 0.05}
        spender = {"food": 0.35, "transport": 0.10, "entertainment": 0.30,
                   "shopping": 0.10, "bills": 0.10, "other": 0.05}
        assert cluster_persona(saver)["persona"] != cluster_persona(spender)["persona"]


# ── Anomaly detection ─────────────────────────────────────────────────

class TestAnomalyDetection:
    def test_normal_not_flagged(self):
        history = [100, 120, 110, 95, 130, 105, 115, 100, 125, 90]
        result = detect_anomaly(110, history)
        assert result["is_anomaly"] is False

    def test_anomaly_flagged(self):
        history = [100, 120, 110, 95, 130, 105, 115, 100, 125, 90,
                   108, 112, 118, 102, 98, 107, 122, 113, 97, 103,
                   110, 105, 115, 100, 125, 90, 108, 112, 118, 102]
        result = detect_anomaly(10000, history)  # 100x normal
        assert result["is_anomaly"] is True
        assert result["severity"] in ("medium", "high")

    def test_few_history_no_flag(self):
        result = detect_anomaly(10000, [100, 200])
        assert result["is_anomaly"] is False


# ── Health Score service ──────────────────────────────────────────────

class TestHealthScore:
    def test_computes_valid_score(self):
        result = compute_health_score("test_user")
        assert 0 <= result["score"] <= 100
        assert "factors" in result
        assert "persona" in result
        assert result["persona"]["persona"] in PERSONAS

    def test_includes_forecast_data(self):
        result = compute_health_score("test_user")
        assert "forecast" in result
        assert "predicted_balance" in result["forecast"]


# ── Intelligence Agent (full integration) ─────────────────────────────

class TestIntelligenceAgent:
    def test_health_score_intent(self):
        agent = IntelligenceAgent()
        output = agent.invoke(AgentInput(user_id="u1", message="score", intent="health_score"))
        assert output.agent_name == "IntelligenceAgent"
        assert "Health Score" in output.response
        assert output.metadata.get("score") is not None

    def test_what_if_intent(self):
        agent = IntelligenceAgent()
        output = agent.invoke(AgentInput(
            user_id="u1", message="what if",
            intent="what_if",
            context={"expense_amount": 5000},
        ))
        assert "risk" in output.response.lower() or "impact" in output.response.lower()
        assert output.metadata.get("risk_level") in ("low", "medium", "high")

    def test_anomaly_intent(self):
        agent = IntelligenceAgent()
        output = agent.invoke(AgentInput(
            user_id="u1", message="check",
            intent="anomaly_check",
            context={"amount": 50000},
        ))
        assert output.agent_name == "IntelligenceAgent"
        assert "is_anomaly" in output.metadata
