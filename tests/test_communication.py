from app.agents.communication import CommunicationAgent
from app.agents.base import AgentInput, AgentStatus
from app.compliance.guard import validate_and_refine
from app.services.nlg import generate_response
from app.services.nudge import can_send_nudge, record_nudge, _user_nudge_history


# ── Nudge Fatigue Tests ───────────────────────────────────────────────


class TestNudgeFatigue:
    def setup_method(self):
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


# ── Communication Agent (Pure NLG) Tests ──────────────────────────────


class TestCommunicationAgent:
    def setup_method(self):
        _user_nudge_history.clear()

    def test_agent_handles_structured_agent_results(self):
        """CommunicationAgent takes structured JSON agent_results and generates NLG."""
        agent = CommunicationAgent()
        agent_results = [
            {
                "agent_name": "IntelligenceAgent",
                "status": "success",
                "metadata": {
                    "intent_handled": "health_score",
                    "score": 75,
                    "persona": "Balanced Manager",
                    "top_factor": "savings",
                    "weak_factor": "liquidity",
                },
            }
        ]
        output = agent.invoke(
            AgentInput(
                user_id="user123",
                message="What is my health score?",
                intent="health_score",
                context={
                    "agent_results": agent_results,
                    "task": "Summarize the health score data.",
                },
            )
        )
        assert output.agent_name == "CommunicationAgent"
        assert len(output.response) > 0
        assert "provider" in output.metadata

    def test_agent_handles_general_query(self):
        """CommunicationAgent handles general queries without agent_results."""
        agent = CommunicationAgent()
        output = agent.invoke(
            AgentInput(
                user_id="user123",
                message="Tell me something helpful",
                intent="general",
                context={
                    "data": "General financial inquiry",
                    "task": "Be helpful",
                },
            )
        )
        assert output.agent_name == "CommunicationAgent"
        assert len(output.response) > 0

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

    def test_multi_agent_results_synthesis(self):
        """CommunicationAgent handles results from multiple agents."""
        agent = CommunicationAgent()
        agent_results = [
            {
                "agent_name": "IntelligenceAgent",
                "status": "success",
                "metadata": {
                    "intent_handled": "balance",
                    "current_balance": 25000,
                    "available_balance": 20000,
                },
            },
            {
                "agent_name": "IntelligenceAgent",
                "status": "success",
                "metadata": {
                    "intent_handled": "what_if",
                    "expense_amount": 5000,
                    "simulated_balance": 20000,
                    "risk_level": "low",
                },
            },
        ]
        output = agent.invoke(
            AgentInput(
                user_id="user123",
                message="Balance and what if I spend 5000?",
                intent="balance",
                context={
                    "agent_results": agent_results,
                    "task": "Synthesize balance and what-if results.",
                },
            )
        )
        assert output.agent_name == "CommunicationAgent"
        assert len(output.response) > 0

    def test_enriched_metadata_returned(self):
        """CommunicationAgent returns model and tokens in metadata via NLG service."""
        agent = CommunicationAgent()
        output = agent.invoke(
            AgentInput(
                user_id="user_metadata",
                message="Tell me a fun fact",
                intent="general",
                context={"task": "Answer the question"},
            )
        )

        assert output.status == "success"
        # Since we use actual NLG or fallback here, we assert the keys exist
        assert "provider" in output.metadata
        assert "model" in output.metadata
        assert "tokens" in output.metadata

    def test_balance_template_includes_total_and_current(self):
        agent = CommunicationAgent()
        agent_results = [
            {
                "agent_name": "IntelligenceAgent",
                "status": AgentStatus.success,
                "metadata": {
                    "intent_handled": "balance",
                    "current_balance": 25540.52,
                    "available_balance": 24297.15,
                },
            }
        ]
        output = agent.invoke(
            AgentInput(
                user_id="user_balance",
                message="What's my balance?",
                intent="balance",
                context={
                    "agent_results": agent_results,
                    "task": "Summarize the user's balance.",
                },
            )
        )
        assert "Total balance ₹ 24,297.15" in output.response
        assert "Current balance ₹ 25,540.52" in output.response
        assert output.metadata.get("provider") == "balance_template"
