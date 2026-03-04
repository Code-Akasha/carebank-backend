from app.agents.base import AgentInput, AgentOutput
from app.agents.intelligence import IntelligenceAgent
from app.agents.communication import CommunicationAgent
from app.agents.opportunity import OpportunityAgent
from app.agents.auto_savings import AutoSavingsAgent
from app.agents.coordinator import (
    build_coordinator_graph,
    classify_intent,
    route_to_agent,
    CoordinatorState,
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


# ── Intent classification tests ───────────────────────────────────────


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

    def test_product_query(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "Recommend me a loan product",
            "audit_log": [],
        }
        result = classify_intent(state)
        assert result["intent"] == "opportunity"

    def test_general_query_fallback(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "Tell me a joke",
            "audit_log": [],
        }
        result = classify_intent(state)
        assert result["intent"] == "general"


# ── Routing tests ─────────────────────────────────────────────────────


class TestRouting:
    def test_health_routes_to_intelligence(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "What is my health score?",
            "intent": "health_score",
            "audit_log": [],
        }
        result = route_to_agent(state)
        assert result["agent_used"] == "IntelligenceAgent"
        assert result["agent_response"] != ""

    def test_what_if_routes_to_intelligence(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "What if I spend 5000?",
            "intent": "what_if",
            "audit_log": [],
        }
        result = route_to_agent(state)
        assert result["agent_used"] == "IntelligenceAgent"

    def test_savings_routes_to_auto_savings(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "Save money",
            "intent": "auto_savings",
            "audit_log": [],
        }
        result = route_to_agent(state)
        assert result["agent_used"] == "AutoSavingsAgent"

    def test_product_routes_to_opportunity(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "Show products",
            "intent": "opportunity",
            "audit_log": [],
        }
        result = route_to_agent(state)
        assert result["agent_used"] == "OpportunityAgent"

    def test_general_routes_to_communication(self):
        state: CoordinatorState = {
            "user_id": "u1",
            "message": "Hello there",
            "intent": "general",
            "audit_log": [],
        }
        result = route_to_agent(state)
        assert result["agent_used"] == "CommunicationAgent"


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
        assert result["agent_used"] == "IntelligenceAgent"
        assert "Health Score" in result["agent_response"]

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
        assert result["agent_used"] == "CommunicationAgent"

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
        assert len(result["audit_log"]) == 1
        assert result["audit_log"][0]["agent_used"] == "IntelligenceAgent"

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
