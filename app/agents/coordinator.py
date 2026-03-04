from __future__ import annotations

from typing import TypedDict

from langgraph.graph import StateGraph, END

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.intelligence import IntelligenceAgent
from app.agents.communication import CommunicationAgent
from app.agents.opportunity import OpportunityAgent
from app.agents.auto_savings import AutoSavingsAgent
from app.compliance.guard import validate_and_refine, log_compliance_decision

# ---------------------------------------------------------------------------
# Intent keywords → intent label mapping
# ---------------------------------------------------------------------------
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "health_score": [
        "health",
        "score",
        "wellness",
        "how am i doing",
        "financial health",
    ],
    "what_if": ["what if", "what-if", "spend", "impact", "simulate", "scenario"],
    "auto_savings": ["save", "saving", "savings", "budget", "micro", "transfer"],
    "opportunity": [
        "product",
        "recommend",
        "loan",
        "subscription",
        "offer",
        "eligible",
    ],
}

_INTENT_TO_AGENT: dict[str, str] = {
    "health_score": "IntelligenceAgent",
    "what_if": "IntelligenceAgent",
    "auto_savings": "AutoSavingsAgent",
    "opportunity": "OpportunityAgent",
    "general": "CommunicationAgent",
}

# ---------------------------------------------------------------------------
# Conversation memory (in-memory for MVP)
# ---------------------------------------------------------------------------
MAX_HISTORY = 10
_conversation_store: dict[str, list[dict]] = {}


def _get_history(user_id: str) -> list[dict]:
    return _conversation_store.setdefault(user_id, [])


def get_conversation_history(user_id: str) -> list[dict]:
    return list(_get_history(user_id))


def _add_to_history(user_id: str, role: str, content: str) -> None:
    history = _get_history(user_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY:
        _conversation_store[user_id] = history[-MAX_HISTORY:]


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------
def _build_agent_registry() -> dict[str, BaseAgent]:
    agents: list[BaseAgent] = [
        IntelligenceAgent(),
        CommunicationAgent(),
        OpportunityAgent(),
        AutoSavingsAgent(),
    ]
    return {agent.name: agent for agent in agents}


_AGENT_REGISTRY = _build_agent_registry()

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class CoordinatorState(TypedDict, total=False):
    user_id: str
    message: str
    intent: str
    agent_response: str
    agent_used: str
    audit_log: list
    conversation_history: list
    error: str


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def classify_intent(state: CoordinatorState) -> CoordinatorState:
    message = state["message"].lower()

    detected_intent = "general"
    for intent, keywords in _INTENT_KEYWORDS.items():
        if any(kw in message for kw in keywords):
            detected_intent = intent
            break

    return {**state, "intent": detected_intent}


def route_to_agent(state: CoordinatorState) -> CoordinatorState:
    intent = state.get("intent", "general")
    agent_name = _INTENT_TO_AGENT.get(intent, "CommunicationAgent")
    agent = _AGENT_REGISTRY.get(agent_name)

    if agent is None:
        return {
            **state,
            "agent_response": "I'm sorry, I couldn't find the right specialist. Please try again.",
            "agent_used": "none",
            "error": f"Agent '{agent_name}' not found in registry",
        }

    agent_input = AgentInput(
        user_id=state["user_id"],
        message=state["message"],
        intent=intent,
        context={"history": state.get("conversation_history", [])},
    )

    output: AgentOutput = agent.invoke(agent_input)

    audit_entry = {
        "intent": intent,
        "agent_used": output.agent_name,
        "confidence": output.confidence,
    }
    audit_log = list(state.get("audit_log", []))
    audit_log.append(audit_entry)

    return {
        **state,
        "agent_response": output.response,
        "agent_used": output.agent_name,
        "audit_log": audit_log,
    }


def validate_response(state: CoordinatorState) -> CoordinatorState:
    try:
        refined_response, metadata = validate_and_refine(
            response=state.get("agent_response", ""),
            intent=state.get("intent", "general"),
            original_data=None,  # In a full system, we'd pass original data context here
        )

        # Determine strict blocking or just logging based on flags (MVP: just log/redact)

        if (
            metadata.get("blacklist_flagged")
            or metadata.get("disclaimer_added")
            or not metadata.get("numbers_verified")
        ):
            log_compliance_decision(
                user_id=state["user_id"],
                intent=state.get("intent", "general"),
                original_response=state.get("agent_response", ""),
                final_response=refined_response,
                metadata=metadata,
            )

        return {**state, "agent_response": refined_response}
    except Exception:
        # Fail open or fail closed? MVP: fail open with original response if compliance bugs out
        return state


def format_response(state: CoordinatorState) -> CoordinatorState:
    user_id = state["user_id"]
    _add_to_history(user_id, "user", state["message"])
    _add_to_history(user_id, "assistant", state.get("agent_response", ""))

    return {
        **state,
        "conversation_history": _get_history(user_id),
    }


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_coordinator_graph():
    graph = StateGraph(CoordinatorState)

    graph.add_node("classify", classify_intent)
    graph.add_node("route", route_to_agent)
    graph.add_node("validate", validate_response)
    graph.add_node("respond", format_response)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "route")
    graph.add_edge("route", "validate")
    graph.add_edge("validate", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


# Singleton compiled graph
coordinator_graph = build_coordinator_graph()
