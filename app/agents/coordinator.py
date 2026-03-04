from __future__ import annotations

import logging
from typing import TypedDict

from langgraph.graph import StateGraph, END
from langchain_core.prompts import PromptTemplate

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.intelligence import IntelligenceAgent
from app.agents.communication import CommunicationAgent
from app.agents.opportunity import OpportunityAgent
from app.agents.auto_savings import AutoSavingsAgent
from app.compliance.guard import validate_and_refine, log_compliance_decision
from app.services.llm import get_llm_provider

logger = logging.getLogger(__name__)


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
# Intelligent Intent Classification (LLM-based)
# ---------------------------------------------------------------------------

INTENT_CLASSIFICATION_PROMPT = """You are an intelligent financial assistant coordinator that routes user queries to the appropriate specialist agent.

Available agents and their capabilities:
{agent_descriptions}

Intent codes (use these exactly):
- balance: Account balance and transaction queries
- forecast: Future balance predictions
- health_score: Financial health assessment
- what_if: Scenario analysis ("what if I spend...", impact analysis)
- auto_savings: Savings advice and micro-savings
- opportunity: Product recommendations and offers
- general: Non-financial questions or small talk

User query: "{user_message}"
Recent conversation context: {conversation_summary}

Task: Analyze the user's query and determine:
1. The primary intent CODE (from the list above)
2. Which agent is best suited to handle it
3. Your confidence in this classification

Respond in this exact format:
INTENT: <one of: balance, forecast, health_score, what_if, auto_savings, opportunity, general>
AGENT: <exact agent name from the list>
CONFIDENCE: <0.0 to 1.0>

Example:
INTENT: balance
AGENT: CommunicationAgent
CONFIDENCE: 0.95

Now analyze the query:"""

# Fallback keyword matching (safety net when LLM is unavailable)
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "balance": [
        "balance",
        "current balance",
        "account balance",
        "available balance",
        "how much do i have",
        "how much money",
    ],
    "forecast": [
        "forecast",
        "prediction",
        "predict",
        "future balance",
        "next month",
        "end of month",
    ],
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
    "balance": "CommunicationAgent",
    "forecast": "IntelligenceAgent",
    "health_score": "IntelligenceAgent",
    "what_if": "IntelligenceAgent",
    "auto_savings": "AutoSavingsAgent",
    "opportunity": "OpportunityAgent",
    "general": "CommunicationAgent",
}

# Reverse mapping: agent name -> primary intent it handles
_AGENT_TO_INTENT: dict[str, str] = {
    "IntelligenceAgent": "health_score",
    "CommunicationAgent": "balance",
    "AutoSavingsAgent": "auto_savings",
    "OpportunityAgent": "opportunity",
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
# Intelligent Classification Helpers
# ---------------------------------------------------------------------------


def _get_agent_descriptions() -> str:
    """Generate formatted agent descriptions for LLM prompt."""
    descriptions = []
    for agent_name, agent in _AGENT_REGISTRY.items():
        caps = ", ".join(agent.capabilities)
        descriptions.append(
            f"- {agent_name}: {agent.description}\n  Capabilities: {caps}"
        )
    return "\n".join(descriptions)


def _parse_llm_classification(response: str) -> tuple[str, str, float]:
    """Parse LLM response to extract intent, agent, and confidence."""
    lines = response.strip().split("\n")
    intent = "general"
    agent = "CommunicationAgent"
    confidence = 0.7

    for line in lines:
        line = line.strip()
        if line.startswith("INTENT:"):
            intent = line.split(":", 1)[1].strip()
        elif line.startswith("AGENT:"):
            agent = line.split(":", 1)[1].strip()
        elif line.startswith("CONFIDENCE:"):
            try:
                confidence = float(line.split(":", 1)[1].strip())
            except ValueError:
                confidence = 0.7

    return intent, agent, confidence


def _classify_intent_with_llm(
    message: str, history: list[dict]
) -> tuple[str, str, float]:
    """Use LLM to intelligently classify intent and route to appropriate agent."""
    llm, provider = get_llm_provider(temperature=0.3)

    if not llm:
        logger.warning(
            "🔄 LLM unavailable (provider: %s), falling back to keyword matching",
            provider,
        )
        return _classify_intent_keywords(message)

    try:
        # Summarize recent conversation
        conv_summary = "No previous context"
        if history:
            recent = history[-3:]
            conv_summary = " | ".join(
                [f"{msg['role']}: {msg['content'][:50]}" for msg in recent]
            )

        prompt = PromptTemplate.from_template(INTENT_CLASSIFICATION_PROMPT)
        chain = prompt | llm

        logger.info("🧠 Using LLM-based classification (provider: %s)", provider)

        response = chain.invoke(
            {
                "agent_descriptions": _get_agent_descriptions(),
                "user_message": message,
                "conversation_summary": conv_summary,
            }
        )

        intent, agent_name, confidence = _parse_llm_classification(response.content)

        # Validate agent exists
        if agent_name not in _AGENT_REGISTRY:
            logger.warning(
                "⚠️ LLM suggested non-existent agent: %s, using keyword fallback",
                agent_name,
            )
            return _classify_intent_keywords(message)

        logger.info(
            "✅ LLM classified: intent='%s', agent='%s', confidence=%.2f",
            intent,
            agent_name,
            confidence,
        )
        return intent, agent_name, confidence

    except Exception as e:
        logger.warning("❌ LLM classification failed: %s, falling back to keywords", e)
        return _classify_intent_keywords(message)


def _classify_intent_keywords(message: str) -> tuple[str, str, float]:
    """Fallback keyword-based classification."""
    message_lower = message.lower()

    detected_intent = "general"
    for intent, keywords in _INTENT_KEYWORDS.items():
        if any(kw in message_lower for kw in keywords):
            detected_intent = intent
            break

    agent_name = _INTENT_TO_AGENT.get(detected_intent, "CommunicationAgent")
    logger.info(
        "🔑 Keyword matched: intent='%s', agent='%s', confidence=0.6",
        detected_intent,
        agent_name,
    )
    return detected_intent, agent_name, 0.6  # Lower confidence for keyword matching


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class CoordinatorState(TypedDict, total=False):
    user_id: str
    message: str
    intent: str
    agent_name: str
    agent_response: str
    agent_used: str
    classification_confidence: float
    audit_log: list
    conversation_history: list
    error: str


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def classify_intent(state: CoordinatorState) -> CoordinatorState:
    """Intelligently classify user intent using LLM, with keyword fallback."""
    message = state["message"]
    history = state.get("conversation_history", [])

    # Use LLM-based intelligent classification
    intent, agent_name, confidence = _classify_intent_with_llm(message, history)

    return {
        **state,
        "intent": intent,
        "agent_name": agent_name,
        "classification_confidence": confidence,
    }


def route_to_agent(state: CoordinatorState) -> CoordinatorState:
    """Route to the appropriate agent based on classification."""
    intent = state.get("intent", "general")
    agent_name = state.get("agent_name")

    # If agent_name not provided, derive it from intent
    if not agent_name:
        agent_name = _INTENT_TO_AGENT.get(intent, "CommunicationAgent")
        logger.info("Derived agent '%s' from intent '%s'", agent_name, intent)

    agent = _AGENT_REGISTRY.get(agent_name)

    if agent is None:
        logger.error(f"Agent '{agent_name}' not found in registry")
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
        "classification_confidence": state.get("classification_confidence", 0.0),
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
