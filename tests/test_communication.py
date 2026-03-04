from app.agents.communication import CommunicationAgent
from app.agents.base import AgentInput
from app.agents import communication as communication_module
from app.compliance.guard import validate_and_refine
from app.services.nlg import generate_response
from app.services.nudge import can_send_nudge, record_nudge, _user_nudge_history


# ── Nudge Fatigue Tests ───────────────────────────────────────────────


class TestNudgeFatigue:
    def setup_method(self):
        # Clear history before each test
        _user_nudge_history.clear()

    def test_can_send_first_nudge(self):
        allowed, reason = can_send_nudge("user_test")
        assert allowed is True

    def test_blocks_nudge_during_cooldown(self):
        record_nudge("user_test")
        allowed, reason = can_send_nudge("user_test")
        assert allowed is False
        assert "cooldown" in reason.lower()

    def test_daily_limit(self):
        # Manually set history to simulate 2 nudges past cooldown but within 24h
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        _user_nudge_history["user_test"] = [
            now - timedelta(hours=10),
            now - timedelta(hours=5),
        ]
        allowed, reason = can_send_nudge("user_test")
        assert allowed is False
        assert "limit" in reason.lower()


# ── NLG / Template Fallback Tests ─────────────────────────────────────


class TestNLGService:
    def test_template_fallback_cautious(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.nlg.get_llm_provider",
            lambda *args, **kwargs: (None, "template_fallback"),
        )
        result = generate_response(
            "Cautious Saver", "Low savings", "Increase emergency fund"
        )
        assert result["provider"] == "template_fallback"
        assert "prioritize stability" in result["text"].lower()

    def test_template_fallback_social(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.nlg.get_llm_provider",
            lambda *args, **kwargs: (None, "template_fallback"),
        )
        result = generate_response(
            "Social Spender", "High dining", "Cut back eating out"
        )
        assert result["provider"] == "template_fallback"
        assert "fits your budget" in result["text"].lower()


# ── Compliance Guard Tests ────────────────────────────────────────────


class TestComplianceGuard:
    def test_blacklist_redaction(self):
        response = "This investment is 100% safe and we guarantee high returns."
        refined, metadata = validate_and_refine(response, "general")
        assert metadata["blacklist_flagged"] is True
        assert "[REDACTED]" in refined
        assert "100% safe" not in refined.lower()
        assert "guarantee" not in refined.lower()

    def test_disclaimer_injection_for_health_score(self):
        response = "Your health score is 80."
        refined, metadata = validate_and_refine(response, "health_score")
        assert metadata["disclaimer_added"] is True
        assert "Disclaimer" in refined

    def test_no_disclaimer_for_general_intent(self):
        response = "Hello there!"
        refined, metadata = validate_and_refine(response, "general")
        assert metadata["disclaimer_added"] is False
        assert "Disclaimer" not in refined

    def test_number_hallucination_detection(self):
        response = "You spent 50000 on shopping."
        original_data = {"shopping_spend": 200}
        refined, metadata = validate_and_refine(response, "what_if", original_data)
        assert metadata["numbers_verified"] is False


# ── Communication Agent Tests ─────────────────────────────────────────


class TestCommunicationAgent:
    def setup_method(self):
        _user_nudge_history.clear()

    def test_agent_invokes_nlg(self):
        agent = CommunicationAgent()
        output = agent.invoke(
            AgentInput(
                user_id="user123",
                message="Explain my score",
                intent="general",
                context={"data": "Score is 75", "task": "explain"},
            )
        )
        assert output.agent_name == "CommunicationAgent"
        assert len(output.response) > 0
        assert "provider" in output.metadata

    def test_agent_blocks_nudge(self):
        agent = CommunicationAgent()
        # First nudge
        agent.invoke(
            AgentInput(
                user_id="user456",
                message="Nudge user",
                intent="general",
                context={"is_nudge": True},
            )
        )
        # Second nudge (should be blocked by cooldown)
        output = agent.invoke(
            AgentInput(
                user_id="user456",
                message="Nudge user again",
                intent="general",
                context={"is_nudge": True},
            )
        )
        assert "Nudge Blocked" in output.response
        assert output.metadata["nudge"] == "blocked"

    def test_extract_purchase_amount_supports_indian_units(self):
        assert (
            CommunicationAgent._extract_purchase_amount("can i buy this for 50k")
            == 50000
        )
        assert (
            CommunicationAgent._extract_purchase_amount(
                "can i buy this for 50 thousand"
            )
            == 50000
        )
        assert (
            CommunicationAgent._extract_purchase_amount("can i buy this for 1.5 lakh")
            == 150000
        )

    def test_purchase_question_without_amount_returns_clarification(self):
        agent = CommunicationAgent()
        output = agent.invoke(
            AgentInput(
                user_id="user123",
                message="can i buy a laptop?",
                intent="general",
                context={},
            )
        )
        assert "Share the purchase amount in ₹" in output.response
        assert output.metadata["intent_handled"] == "affordability_clarification"

    def test_purchase_question_with_thousand_uses_affordability_flow(self, monkeypatch):
        monkeypatch.setattr(
            communication_module,
            "get_balance_sync",
            lambda _user_id: {"available_balance": 24297.0},
        )

        agent = CommunicationAgent()
        output = agent.invoke(
            AgentInput(
                user_id="user123",
                message="can i buy a laptop of 50 thousand ?",
                intent="general",
                context={},
            )
        )

        assert "Purchase amount: ₹50,000" in output.response
        assert output.metadata["intent_handled"] == "affordability_check"
