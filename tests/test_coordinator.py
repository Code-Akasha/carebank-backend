from app.agents.base import AgentInput, AgentOutput
from app.agents.intelligence import IntelligenceAgent
from app.agents.communication import CommunicationAgent
from app.agents.opportunity import OpportunityAgent
from app.agents.auto_savings import AutoSavingsAgent
from app.agents.coordinator import (
    ActionIntentResult,
    ClassificationResult,
    build_coordinator_graph,
    classify_intent,
    plan_tasks,
    execute_task,
    CoordinatorState,
    _classify_intent_keywords,
    _extract_amount_from_text,
    _get_agent,
    _AGENT_INSTANCES,
    _INTENT_TO_AGENT,
)


# ── Base agent tests ──────────────────────────────────────────────────


class TestBaseAgentInterface:
    def test_intelligence_implements_base(self):
        agent = IntelligenceAgent()
        assert agent.name == "IntelligenceAgent"

        output = agent.invoke(
            AgentInput(user_id="u1", message="score", intent="health_score")
        )
        assert isinstance(output, AgentOutput)
        assert output.agent_name == "IntelligenceAgent"
        assert output.status == "success"

    def test_communication_implements_base(self):
        agent = CommunicationAgent()
        assert agent.name == "CommunicationAgent"

        output = agent.invoke(AgentInput(user_id="u1", message="hello"))
        assert isinstance(output, AgentOutput)

    def test_opportunity_implements_base(self):
        agent = OpportunityAgent()
        assert agent.name == "OpportunityAgent"

        output = agent.invoke(AgentInput(user_id="u1", message="products"))
        assert isinstance(output, AgentOutput)

    def test_auto_savings_implements_base(self):
        agent = AutoSavingsAgent()
        assert agent.name == "AutoSavingsAgent"

        output = agent.invoke(AgentInput(user_id="u1", message="save"))
        assert isinstance(output, AgentOutput)


# ── Regex entity extraction tests ─────────────────────────────────────


class TestEntityExtraction:
    def test_extract_50k(self):
        assert _extract_amount_from_text("what if I spend 50k") == 50000

    def test_extract_50_thousand(self):
        assert _extract_amount_from_text("buy for 50 thousand") == 50000

    def test_extract_1_5_lakh(self):
        assert _extract_amount_from_text("can i buy this for 1.5 lakh") == 150000

    def test_extract_plain_number(self):
        assert _extract_amount_from_text("spend 5000 on flight") == 5000

    def test_no_amount_returns_none(self):
        assert _extract_amount_from_text("what if I buy something") is None

    def test_small_number_ignored(self):
        assert _extract_amount_from_text("buy 2 items") is None


# ── Keyword classification tests ──────────────────────────────────────


class TestKeywordClassification:
    def test_health_query(self):
        result = _classify_intent_keywords("What is my health score?")
        assert result.intent == "health_score"

    def test_what_if_with_amount(self):
        result = _classify_intent_keywords("What if I spend 5000 on a flight?")
        assert result.intent == "what_if"
        assert result.parameters.get("expense_amount") == 5000

    def test_what_if_without_amount(self):
        result = _classify_intent_keywords("What if I spend on something?")
        assert result.intent == "what_if"
        assert "expense_amount" not in result.parameters

    def test_savings_query(self):
        result = _classify_intent_keywords("Can I save money this week?")
        assert result.intent == "auto_savings"

    def test_affordability_query_with_amount(self):
        result = _classify_intent_keywords("Can I buy a laptop for 50k?")
        assert result.intent == "affordability"
        assert result.parameters.get("purchase_amount") == 50000

    def test_product_query(self):
        result = _classify_intent_keywords("Recommend me a loan product")
        assert result.intent == "opportunity"

    def test_general_query_fallback(self):
        result = _classify_intent_keywords("Tell me a joke")
        assert result.intent == "general"

    def test_balance_keyword_detected(self):
        result = _classify_intent_keywords("What is my balance?")
        assert result.intent == "balance"

    def test_schedule_query_detected_as_planning(self):
        result = _classify_intent_keywords(
            "create a shedule to pay rent on next moth 5th"
        )
        assert result.intent == "planning"

    def test_balance_plus_savings_sets_secondary_intent(self):
        result = _classify_intent_keywords(
            "what is my balance and how can i improve my savings"
        )
        assert result.intent == "balance"
        assert result.secondary_intent == "auto_savings"


class TestContextualIntentOverride:
    def test_amount_only_after_schedule_routes_to_planning(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "5000",
            "audit_log": [],
            "conversation_history": [
                {
                    "role": "user",
                    "content": "create a shedule to pay rent on next moth 5th",
                },
                {
                    "role": "assistant",
                    "content": "Please share the rent amount as well.",
                },
            ],
        }
        result = classify_intent(state)
        assert result["intent"] == "planning"
        assert result["agent_name"] == "CommunicationAgent"

    def test_stale_pending_planning_does_not_hijack_unrelated_query(self, monkeypatch):
        import app.agents.coordinator as coordinator_module

        monkeypatch.setattr(
            coordinator_module,
            "_detect_action_request",
            lambda _message, _history: None,
        )
        monkeypatch.setattr(
            coordinator_module,
            "_classify_intent_with_llm",
            lambda _message, _history: ClassificationResult(
                intent="balance",
                confidence=0.91,
                parameters={},
                secondary_intent="auto_savings",
            ),
        )

        state: CoordinatorState = {
            "user_id": "u1",
            "message": "what is my balance how can i improve my savings",
            "audit_log": [],
            "conversation_history": [
                {
                    "role": "user",
                    "content": "create a shedule to pay rent on next moth 5th",
                },
                {
                    "role": "assistant",
                    "content": "Please share the rent amount as well.",
                },
            ],
            "conversation_state": {
                "pending_intent": "planning",
                "planning": {
                    "flow": "schedule_from_text",
                    "source_text": "create a shedule to pay rent on next moth 5th",
                    "day_of_month": 5,
                    "amount": None,
                },
            },
        }

        result = classify_intent(state)
        assert result["intent"] == "balance"
        assert result["classification_secondary_intent"] == "auto_savings"
        assert result["pending_intent_ignored"] is True


class TestActionIntentRouting:
    def test_action_style_bill_query_routes_to_planning(self, monkeypatch):
        import app.agents.coordinator as coordinator_module

        monkeypatch.setattr(
            coordinator_module,
            "_classify_intent_with_llm",
            lambda _message, _history: ClassificationResult(
                intent="balance",
                confidence=0.9,
                parameters={"amount": 2000},
            ),
        )
        monkeypatch.setattr(
            coordinator_module,
            "_detect_action_request",
            lambda _message, _history: ActionIntentResult(
                is_action_request=True,
                action_family="schedule_payment",
                confidence=0.86,
                amount=2000,
                day_of_month=20,
                recurring=True,
            ),
        )

        state: CoordinatorState = {
            "user_id": "u1",
            "message": "pay my electricity bills of 2000 on 20",
            "audit_log": [],
            "conversation_history": [],
            "conversation_state": {},
        }
        result = classify_intent(state)
        assert result["intent"] == "planning"
        assert result["agent_name"] == "CommunicationAgent"
        assert result["classification_parameters"]["amount"] == 2000
        assert result["classification_parameters"]["day_of_month"] == 20


# ── Intent classification node tests ──────────────────────────────────


class TestIntentClassification:
    def test_health_query(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "What is my health score?",
            "audit_log": [],
        }
        result = classify_intent(state)
        assert result["intent"] == "health_score"

    def test_what_if_query(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "What if I spend 5000 on a flight?",
            "audit_log": [],
        }
        result = classify_intent(state)
        assert result["intent"] == "what_if"

    def test_savings_query(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "Can I save money this week?",
            "audit_log": [],
        }
        result = classify_intent(state)
        assert result["intent"] == "auto_savings"

    def test_general_query_fallback(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "Tell me a joke",
            "audit_log": [],
        }
        result = classify_intent(state)
        assert result["intent"] == "general"


class TestDeterministicRouting:
    def test_balance_routes_via_mapping(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "Show me my balance",
            "audit_log": [],
            "conversation_history": [],
        }
        result = classify_intent(state)
        assert result["agent_name"] == _INTENT_TO_AGENT["balance"]

    def test_general_routes_to_communication(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "Tell me a joke",
            "audit_log": [],
            "conversation_history": [],
        }
        result = classify_intent(state)
        assert result["agent_name"] == _INTENT_TO_AGENT["general"]


class TestLazyRegistry:
    def test_agents_instantiate_on_demand(self):
        snapshot = dict(_AGENT_INSTANCES)
        try:
            _AGENT_INSTANCES.clear()
            assert _AGENT_INSTANCES == {}

            agent = _get_agent("IntelligenceAgent")
            assert agent is not None
            assert "IntelligenceAgent" in _AGENT_INSTANCES
        finally:
            _AGENT_INSTANCES.clear()
            _AGENT_INSTANCES.update(snapshot)


# ── Plan tasks tests ──────────────────────────────────────────────────


class TestPlanTasks:
    def test_creates_single_task(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "check score",
            "intent": "health_score",
            "agent_name": "IntelligenceAgent",
            "classification_parameters": {},
            "audit_log": [],
        }
        result = plan_tasks(state)
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["intent"] == "health_score"
        assert result["current_task_index"] == 0

    def test_passes_parameters(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "what if 50k",
            "intent": "what_if",
            "agent_name": "IntelligenceAgent",
            "classification_parameters": {"expense_amount": 50000.0},
            "audit_log": [],
        }
        result = plan_tasks(state)
        assert result["tasks"][0]["parameters"]["expense_amount"] == 50000.0

    def test_secondary_intent_creates_additional_task(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "Can I buy a laptop and what happens to my balance?",
            "intent": "balance",
            "agent_name": "IntelligenceAgent",
            "classification_parameters": {"purchase_amount": 50000.0},
            "classification_secondary_intent": "affordability",
        }
        result = plan_tasks(state)
        assert len(result["tasks"]) == 2
        assert result["tasks"][1]["intent"] == "affordability"
        assert result["tasks"][1]["agent_name"] == _INTENT_TO_AGENT["affordability"]


# ── Execute task tests ────────────────────────────────────────────────


class TestExecuteTask:
    def test_routes_to_intelligence_for_health(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "What is my health score?",
            "intent": "health_score",
            "tasks": [
                {
                    "intent": "health_score",
                    "agent_name": "IntelligenceAgent",
                    "parameters": {},
                }
            ],
            "current_task_index": 0,
            "agent_results": [],
            "audit_log": [],
        }
        result = execute_task(state)
        assert result["current_task_index"] == 1
        assert len(result["agent_results"]) == 1
        assert result["agent_results"][0]["agent_name"] == "IntelligenceAgent"
        assert result["agent_results"][0]["status"] == "success"

    def test_routes_to_auto_savings(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "Save money",
            "intent": "auto_savings",
            "tasks": [
                {
                    "intent": "auto_savings",
                    "agent_name": "AutoSavingsAgent",
                    "parameters": {},
                }
            ],
            "current_task_index": 0,
            "agent_results": [],
            "audit_log": [],
        }
        result = execute_task(state)
        assert result["agent_results"][0]["agent_name"] == "AutoSavingsAgent"

    def test_missing_agent_returns_error(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "test",
            "intent": "general",
            "tasks": [
                {
                    "intent": "general",
                    "agent_name": "NonExistentAgent",
                    "parameters": {},
                }
            ],
            "current_task_index": 0,
            "agent_results": [],
            "audit_log": [],
        }
        result = execute_task(state)
        assert result["agent_results"][0]["status"] == "error"
        assert result["error"] is not None


# ── Full graph tests ──────────────────────────────────────────────────


class TestCoordinatorGraph:
    def test_graph_compiles(self):
        graph = build_coordinator_graph()
        assert graph is not None

    def test_end_to_end_health(self):
        graph = build_coordinator_graph()
        result = graph.invoke(
            {
                "user_id": "test_user",
                "message": "What is my health score?",
                "audit_log": [],
                "conversation_history": [],
            }
        )
        assert result["intent"] == "health_score"
        assert "IntelligenceAgent" in result.get("agent_used", "")
        # Response is now NLG-generated, not hardcoded
        assert len(result.get("agent_response", "")) > 0

    def test_end_to_end_general(self):
        graph = build_coordinator_graph()
        result = graph.invoke(
            {
                "user_id": "test_user",
                "message": "Tell me something random",
                "audit_log": [],
                "conversation_history": [],
            }
        )
        assert result["intent"] == "general"
        assert len(result.get("agent_response", "")) > 0

    def test_end_to_end_what_if_with_amount(self):
        graph = build_coordinator_graph()
        result = graph.invoke(
            {
                "user_id": "test_user",
                "message": "What if I spend 5000 on a flight?",
                "audit_log": [],
                "conversation_history": [],
            }
        )
        assert result["intent"] == "what_if"
        # Should have agent results with data
        assert len(result.get("agent_results", [])) > 0

    def test_end_to_end_what_if_without_amount(self):
        graph = build_coordinator_graph()
        result = graph.invoke(
            {
                "user_id": "test_user",
                "message": "What if I buy something?",
                "audit_log": [],
                "conversation_history": [],
            }
        )
        assert result["intent"] in {"what_if", "affordability"}
        response = result.get("agent_response", "")
        assert len(response) > 0
        agent_results = result.get("agent_results", [])
        if agent_results and agent_results[-1]["status"] == "needs_input":
            assert (
                "amount" in response.lower()
                or "provide" in response.lower()
                or "expense_amount" in response.lower()
            )

    def test_audit_log_created(self):
        graph = build_coordinator_graph()
        result = graph.invoke(
            {
                "user_id": "test_user",
                "message": "What is my score?",
                "audit_log": [],
                "conversation_history": [],
            }
        )
        assert len(result["audit_log"]) >= 1
        assert result["audit_log"][0]["agent_used"] == "IntelligenceAgent"

    def test_end_to_end_schedule_followup_amount_keeps_day_context(self):
        graph = build_coordinator_graph()
        user_id = "schedule_followup_graph_test"

        first = graph.invoke(
            {
                "user_id": user_id,
                "message": "create a shedule to pay rent on next moth 5th",
                "audit_log": [],
                "conversation_history": [],
            }
        )

        second = graph.invoke(
            {
                "user_id": user_id,
                "message": "5000",
                "audit_log": [],
                "conversation_history": first.get("conversation_history", []),
            }
        )

        response = second.get("agent_response", "").lower()
        assert "day 5" in response
        assert "please share the day" not in response

    def test_error_handling_graceful(self):
        """Agent base class wraps exceptions gracefully."""
        from app.agents.base import BaseAgent

        class FailingAgent(BaseAgent):
            @property
            def name(self) -> str:
                return "FailingAgent"

            @property
            def description(self) -> str:
                return "Test agent that fails"

            @property
            def capabilities(self) -> list[str]:
                return ["test_failure"]

            def _invoke(self, agent_input):
                raise RuntimeError("Boom")

        agent = FailingAgent()
        output = agent.invoke(AgentInput(user_id="u1", message="crash"))
        assert output.confidence == 0.0
        assert "error" in output.metadata
