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

    def test_schedule_query_not_hijacked_by_balance_template(self):
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
                user_id="user_schedule",
                message="create a shedule to pay rent on next moth 5th",
                intent="planning",
                context={
                    "agent_results": agent_results,
                    "task": "Help create recurring rent schedule",
                },
            )
        )

        assert output.metadata.get("provider") != "balance_template"
        assert (
            "schedule" in output.response.lower() or "rent" in output.response.lower()
        )

    def test_schedule_query_prompts_for_missing_amount(self):
        agent = CommunicationAgent()
        output = agent.invoke(
            AgentInput(
                user_id="user_schedule_missing_amount",
                message="create a shedule to pay rent on next moth 5th",
                intent="planning",
                context={
                    "task": "Create recurring rent schedule",
                },
            )
        )

        assert output.metadata.get("provider") == "planning_executor"
        assert "amount" in output.response.lower()
        pending = output.metadata.get("pending_state") or {}
        assert pending.get("pending_intent") == "planning"

    def test_schedule_followup_amount_uses_history_day(self):
        agent = CommunicationAgent()
        output = agent.invoke(
            AgentInput(
                user_id="user_schedule_followup",
                message="5000",
                intent="planning",
                context={
                    "conversation_state": {
                        "pending_intent": "planning",
                        "planning": {
                            "flow": "schedule_from_text",
                            "source_text": "create a shedule to pay rent on next moth 5th",
                            "day_of_month": 5,
                            "amount": None,
                        },
                    },
                    "history": [
                        {
                            "role": "user",
                            "content": "create a shedule to pay rent on next moth 5th",
                        },
                        {
                            "role": "assistant",
                            "content": "Please share the rent amount",
                        },
                    ],
                },
            )
        )

        assert output.metadata.get("provider") == "planning_executor"
        assert output.metadata.get("clear_pending") is True
        action = output.metadata.get("action") or {}
        assert action.get("type") == "create_schedule_from_text"
        assert "day 5" in output.response.lower()
        assert "5,000.00" in output.response

    def test_stale_pending_planning_not_applied_to_balance_query(self):
        agent = CommunicationAgent()
        output = agent.invoke(
            AgentInput(
                user_id="user_pending_guard",
                message="what is my balance how can i improve my savings",
                intent="balance",
                context={
                    "conversation_state": {
                        "pending_intent": "planning",
                        "planning": {
                            "flow": "schedule_from_text",
                            "source_text": "create a shedule to pay rent on next moth 5th",
                            "day_of_month": 5,
                            "amount": None,
                        },
                    },
                    "history": [
                        {
                            "role": "user",
                            "content": "create a shedule to pay rent on next moth 5th",
                        },
                        {
                            "role": "assistant",
                            "content": "Please share the rent amount",
                        },
                    ],
                    "agent_results": [
                        {
                            "agent_name": "IntelligenceAgent",
                            "status": AgentStatus.success,
                            "metadata": {
                                "intent_handled": "balance",
                                "current_balance": 25540.52,
                                "available_balance": 24297.15,
                            },
                        }
                    ],
                    "task": "Answer balance and savings question",
                },
            )
        )

        assert output.metadata.get("provider") == "balance_template"
        assert output.metadata.get("action") is None
        assert "creating recurring payment schedule" not in output.response.lower()

    def test_action_query_prompts_for_missing_amount(self):
        agent = CommunicationAgent()
        output = agent.invoke(
            AgentInput(
                user_id="user_action_missing_amount",
                message="transfer to savings",
                intent="actions",
                context={
                    "task": "Create action request",
                },
            )
        )

        assert output.metadata.get("provider") == "action_engine_planner"
        assert "amount" in output.response.lower()
        pending = output.metadata.get("pending_state") or {}
        assert pending.get("pending_intent") == "actions"
        actions_state = pending.get("actions") or {}
        assert actions_state.get("action_type") == "transfer_savings"

    def test_action_followup_amount_emits_create_action_request(self):
        agent = CommunicationAgent()
        output = agent.invoke(
            AgentInput(
                user_id="user_action_followup_amount",
                message="5000",
                intent="actions",
                context={
                    "conversation_state": {
                        "pending_intent": "actions",
                        "actions": {
                            "flow": "action_request",
                            "action_type": "transfer_savings",
                            "action_payload": {"amount": None},
                        },
                    },
                    "history": [
                        {"role": "user", "content": "transfer to savings"},
                        {
                            "role": "assistant",
                            "content": "How much should I transfer?",
                        },
                    ],
                },
            )
        )

        assert output.metadata.get("provider") == "action_engine_planner"
        assert output.metadata.get("clear_pending") is True
        action = output.metadata.get("action") or {}
        assert action.get("type") == "create_action_request"
        assert action.get("action_type") == "transfer_savings"
        assert action.get("action_payload", {}).get("amount") == 5000

    def test_action_approval_followup_emits_approve(self):
        agent = CommunicationAgent()
        output = agent.invoke(
            AgentInput(
                user_id="user_action_approval",
                message="yes",
                intent="actions",
                context={
                    "conversation_state": {
                        "pending_intent": "actions",
                        "actions": {
                            "flow": "action_approval",
                            "request_id": 123,
                            "action_type": "pay_bill",
                            "action_payload": {"amount": 2000},
                        },
                    }
                },
            )
        )

        assert output.metadata.get("provider") == "action_engine_planner"
        action = output.metadata.get("action") or {}
        assert action.get("type") == "approve_action_request"
        assert action.get("request_id") == 123

    def test_action_rejection_followup_emits_reject(self):
        agent = CommunicationAgent()
        output = agent.invoke(
            AgentInput(
                user_id="user_action_rejection",
                message="no",
                intent="actions",
                context={
                    "conversation_state": {
                        "pending_intent": "actions",
                        "actions": {
                            "flow": "action_approval",
                            "request_id": 124,
                            "action_type": "pay_bill",
                            "action_payload": {"amount": 2000},
                        },
                    }
                },
            )
        )

        assert output.metadata.get("provider") == "action_engine_planner"
        action = output.metadata.get("action") or {}
        assert action.get("type") == "reject_action_request"
        assert action.get("request_id") == 124
