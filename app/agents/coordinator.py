from __future__ import annotations

import logging
import re
from typing import TypedDict

from langgraph.graph import StateGraph, END
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

from app.agents.base import (
    AgentInput,
    AgentOutput,
    AgentContext,
    AgentStatus,
    BaseAgent,
)
from app.compliance.guard import validate_and_refine, log_compliance_decision
from app.services.llm import get_llm_provider
from app.services.conversation_store import InMemoryConversationStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conversation memory (abstracted via ConversationStore protocol)
# ---------------------------------------------------------------------------
_conversation_store = InMemoryConversationStore(max_history=10)


def get_conversation_history(user_id: str) -> list[dict]:
    return _conversation_store.get(user_id)


# ---------------------------------------------------------------------------
# Lazy agent registry — classes stored, instantiated on first access
# ---------------------------------------------------------------------------
_AGENT_CLASSES: dict[str, type[BaseAgent]] = {}
_AGENT_INSTANCES: dict[str, BaseAgent] = {}


def _register_agents() -> None:
    """Register agent classes lazily (import at module load, instantiate on demand)."""
    from app.agents.intelligence import IntelligenceAgent
    from app.agents.communication import CommunicationAgent
    from app.agents.opportunity import OpportunityAgent
    from app.agents.auto_savings import AutoSavingsAgent

    _AGENT_CLASSES.update(
        {
            "IntelligenceAgent": IntelligenceAgent,
            "CommunicationAgent": CommunicationAgent,
            "OpportunityAgent": OpportunityAgent,
            "AutoSavingsAgent": AutoSavingsAgent,
        }
    )


_register_agents()


def _get_agent(name: str) -> BaseAgent | None:
    """Get agent instance, instantiating lazily on first access."""
    if name not in _AGENT_INSTANCES:
        cls = _AGENT_CLASSES.get(name)
        if cls is None:
            return None
        _AGENT_INSTANCES[name] = cls()
    return _AGENT_INSTANCES[name]


def _get_all_agents() -> dict[str, BaseAgent]:
    """Get all agents (for descriptions). Instantiates any not yet created."""
    for name in _AGENT_CLASSES:
        _get_agent(name)
    return dict(_AGENT_INSTANCES)


# ---------------------------------------------------------------------------
# Structured Classification Output (agent_name REMOVED — deterministic routing)
# ---------------------------------------------------------------------------


class ClassificationResult(BaseModel):
    """Structured output from LLM intent classification."""

    intent: str = Field(
        description="One of: balance, forecast, health_score, what_if, auto_savings, opportunity, affordability, general"
    )
    confidence: float = Field(description="0.0 to 1.0 confidence in classification")
    parameters: dict = Field(
        default_factory=dict,
        description="Extracted entities: expense_amount (float), category (str), date (str), purchase_amount (float)",
    )
    secondary_intent: str | None = Field(
        default=None,
        description="Optional secondary intent if the query contains multiple requests",
    )


# ---------------------------------------------------------------------------
# Intent-to-agent mapping (deterministic — single source of truth)
# ---------------------------------------------------------------------------

_INTENT_TO_AGENT: dict[str, str] = {
    "balance": "IntelligenceAgent",
    "forecast": "IntelligenceAgent",
    "health_score": "IntelligenceAgent",
    "what_if": "IntelligenceAgent",
    "affordability": "IntelligenceAgent",
    "auto_savings": "AutoSavingsAgent",
    "opportunity": "OpportunityAgent",
    "general": "CommunicationAgent",
}


# ---------------------------------------------------------------------------
# Structured Classification Prompt (agent_name REMOVED)
# ---------------------------------------------------------------------------

INTENT_CLASSIFICATION_PROMPT = """You are an intelligent financial assistant coordinator that routes user queries to the appropriate specialist.

Available capabilities:
{agent_descriptions}

Intent codes (use these exactly):
- balance: Account balance and transaction queries
- forecast: Future balance predictions
- health_score: Financial health assessment
- what_if: Scenario analysis ("what if I spend...", impact analysis)
- affordability: "Can I afford...", "should I buy..." purchase questions
- auto_savings: Savings advice and micro-savings
- opportunity: Product recommendations and offers
- general: Non-financial questions or small talk

User query: "{user_message}"
Recent conversation context: {conversation_summary}

Task: Analyze the user's query and determine:
1. The primary intent CODE from the list above
2. Your confidence (0.0-1.0)
3. Any extracted parameters (especially monetary amounts as expense_amount or purchase_amount)
4. If the query contains MULTIPLE intents, provide the secondary_intent code

IMPORTANT: If the user mentions a monetary amount (e.g. "50k", "50000", "2 lakhs"), extract it as a number in the parameters dict.
For what_if queries, put the amount in "expense_amount".
For affordability/buy queries, put the amount in "purchase_amount".

Now analyze the query:"""


# Keyword matching (safety net when LLM is unavailable)
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
    "what_if": ["what if", "what-if", "impact", "simulate", "scenario"],
    "affordability": ["can i buy", "should i buy", "afford", "purchase"],
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


# ---------------------------------------------------------------------------
# Regex entity extraction (keyword fallback path)
# ---------------------------------------------------------------------------

_AMOUNT_PATTERN = re.compile(
    r"(?:\b(?:rs\.?|inr)\b|₹)?\s*(\d+(?:\.\d+)?)\s*(k|thousand|lakh|lakhs|lac|lacs|crore|crores|cr)?\b"
)

_UNIT_MULTIPLIERS = {
    "k": 1_000,
    "thousand": 1_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "cr": 10_000_000,
}


def _extract_amount_from_text(message: str) -> float | None:
    """Regex-based amount extraction for keyword fallback path."""
    normalized = re.sub(r"\s+", " ", message.replace(",", "").lower()).strip()
    for match in _AMOUNT_PATTERN.finditer(normalized):
        try:
            amount = float(match.group(1))
        except ValueError:
            continue
        unit = (match.group(2) or "").lower()
        if unit:
            multiplier = _UNIT_MULTIPLIERS.get(unit)
            if multiplier:
                parsed = amount * multiplier
                if parsed > 0:
                    return parsed
        if amount >= 100:
            return amount
    return None


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


def _get_agent_descriptions() -> str:
    descriptions = []
    for agent_name, agent in _get_all_agents().items():
        caps = ", ".join(agent.capabilities)
        descriptions.append(
            f"- {agent_name}: {agent.description}\n  Capabilities: {caps}"
        )
    return "\n".join(descriptions)


def _classify_intent_with_llm(
    message: str, history: list[dict]
) -> ClassificationResult:
    """Use LLM with structured output to classify intent and extract entities."""
    llm, provider = get_llm_provider(temperature=0.1)

    if not llm:
        logger.warning(
            "🔄 LLM unavailable (provider: %s), falling back to keywords",
            provider,
        )
        return _classify_intent_keywords(message)

    try:
        structured_llm = llm.with_structured_output(ClassificationResult)

        conv_summary = "No previous context"
        if history:
            recent = history[-3:]
            conv_summary = " | ".join(
                [f"{msg['role']}: {msg['content'][:50]}" for msg in recent]
            )

        prompt = PromptTemplate.from_template(INTENT_CLASSIFICATION_PROMPT)
        chain = prompt | structured_llm

        logger.info("🧠 Using structured LLM classification (provider: %s)", provider)

        result: ClassificationResult = chain.invoke(
            {
                "agent_descriptions": _get_agent_descriptions(),
                "user_message": message,
                "conversation_summary": conv_summary,
            }
        )

        logger.info(
            "✅ Structured classification: intent='%s', confidence=%.2f, params=%s, secondary='%s'",
            result.intent,
            result.confidence,
            result.parameters,
            result.secondary_intent,
        )
        return result

    except Exception as e:
        logger.warning(
            "❌ Structured LLM classification failed: %s, falling back to keywords", e
        )
        return _classify_intent_keywords(message)


def _classify_intent_keywords(message: str) -> ClassificationResult:
    """Fallback keyword-based classification with regex entity extraction."""
    message_lower = message.lower()

    detected_intent = "general"
    for intent, keywords in _INTENT_KEYWORDS.items():
        if any(kw in message_lower for kw in keywords):
            detected_intent = intent
            break

    # Extract amount via regex for intents that need it
    parameters: dict = {}
    if detected_intent in ("what_if", "affordability"):
        amount = _extract_amount_from_text(message)
        if amount is not None:
            param_key = (
                "expense_amount" if detected_intent == "what_if" else "purchase_amount"
            )
            parameters[param_key] = amount

    logger.info(
        "🔑 Keyword matched: intent='%s', confidence=0.6, params=%s",
        detected_intent,
        parameters,
    )
    return ClassificationResult(
        intent=detected_intent,
        confidence=0.6,
        parameters=parameters,
    )


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class _TaskItem(TypedDict):
    intent: str
    agent_name: str
    parameters: dict


class CoordinatorState(TypedDict, total=False):
    user_id: str
    message: str
    intent: str
    agent_name: str
    agent_response: str
    agent_used: str
    classification_confidence: float
    classification_parameters: dict
    classification_secondary_intent: str | None
    tasks: list
    current_task_index: int
    agent_results: list
    audit_log: list
    conversation_history: list
    error: str


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def classify_intent(state: CoordinatorState) -> CoordinatorState:
    """Classify user intent using structured LLM output, with keyword fallback."""
    message = state["message"]
    history = state.get("conversation_history", [])

    result = _classify_intent_with_llm(message, history)

    # Deterministic routing: intent → agent (code decides, not LLM)
    agent_name = _INTENT_TO_AGENT.get(result.intent, "CommunicationAgent")

    return {
        **state,
        "intent": result.intent,
        "agent_name": agent_name,
        "classification_confidence": result.confidence,
        "classification_parameters": result.parameters,
        "classification_secondary_intent": result.secondary_intent,
    }


def plan_tasks(state: CoordinatorState) -> CoordinatorState:
    """Decompose into tasks. Supports primary + optional secondary intent."""
    intent = state.get("intent", "general")
    agent_name = state.get("agent_name", "CommunicationAgent")
    parameters = state.get("classification_parameters", {})
    secondary_intent = state.get("classification_secondary_intent")

    tasks: list[_TaskItem] = [
        {"intent": intent, "agent_name": agent_name, "parameters": parameters}
    ]

    if secondary_intent and secondary_intent != intent:
        secondary_agent = _INTENT_TO_AGENT.get(secondary_intent, "CommunicationAgent")
        if secondary_agent != agent_name or secondary_intent != intent:
            tasks.append(
                {
                    "intent": secondary_intent,
                    "agent_name": secondary_agent,
                    "parameters": parameters,
                }
            )
            logger.info(
                "📋 Multi-intent detected: primary='%s', secondary='%s'",
                intent,
                secondary_intent,
            )

    return {
        **state,
        "tasks": tasks,
        "current_task_index": 0,
        "agent_results": [],
    }


def execute_task(state: CoordinatorState) -> CoordinatorState:
    """Execute the current task by routing to the appropriate agent."""
    tasks = state.get("tasks", [])
    idx = state.get("current_task_index", 0)

    if idx >= len(tasks):
        return state

    task = tasks[idx]
    agent_name = task["agent_name"]
    intent = task["intent"]
    parameters = task.get("parameters", {})

    agent = _get_agent(agent_name)
    if agent is None:
        logger.error("Agent '%s' not found in registry", agent_name)
        agent_results = list(state.get("agent_results", []))
        agent_results.append(
            {
                "agent_name": "none",
                "status": "error",
                "error": f"Agent '{agent_name}' not found",
                "metadata": {},
            }
        )
        return {
            **state,
            "agent_results": agent_results,
            "current_task_index": idx + 1,
            "error": f"Agent '{agent_name}' not found in registry",
        }

    # Build typed context with extracted parameters
    context = AgentContext(
        history=state.get("conversation_history", []),
        **parameters,
    )

    agent_input = AgentInput(
        user_id=state["user_id"],
        message=state["message"],
        intent=intent,
        context=context,
    )

    output: AgentOutput = agent.invoke(agent_input)

    agent_results = list(state.get("agent_results", []))
    agent_results.append(
        {
            "agent_name": output.agent_name,
            "status": output.status,
            "response": output.response,
            "confidence": output.confidence,
            "metadata": output.metadata,
            "required_params": output.required_params,
        }
    )

    audit_entry = {
        "intent": intent,
        "agent_used": output.agent_name,
        "confidence": output.confidence,
        "classification_confidence": state.get("classification_confidence", 0.0),
        "status": output.status,
        "latency_ms": output.latency_ms,
    }
    audit_log = list(state.get("audit_log", []))
    audit_log.append(audit_entry)

    return {
        **state,
        "agent_results": agent_results,
        "current_task_index": idx + 1,
        "agent_used": output.agent_name,
        "audit_log": audit_log,
    }


def check_remaining(state: CoordinatorState) -> str:
    """Conditional edge: loop back to execute_task or proceed to synthesize."""
    tasks = state.get("tasks", [])
    idx = state.get("current_task_index", 0)

    # Check if last result was needs_input → short-circuit to synthesize
    agent_results = state.get("agent_results", [])
    if agent_results and agent_results[-1].get("status") == AgentStatus.needs_input:
        return "synthesize"

    if idx < len(tasks):
        return "execute_task"
    return "synthesize"


def synthesize_response(state: CoordinatorState) -> CoordinatorState:
    """Send all agent results through CommunicationAgent for NLG synthesis."""
    agent_results = state.get("agent_results", [])

    # Handle needs_input: generate a follow-up question
    if agent_results and agent_results[-1].get("status") == AgentStatus.needs_input:
        required = agent_results[-1].get("required_params", [])
        param_names = ", ".join(required) if required else "more details"
        response = (
            f"I'd love to help with that! Could you provide {param_names}? "
            "For example, specify an amount like ₹50,000 or 50k."
        )
        return {
            **state,
            "agent_response": response,
            "agent_used": agent_results[-1].get("agent_name", "Coordinator"),
        }

    # Route through CommunicationAgent for NLG
    comm_agent = _get_agent("CommunicationAgent")
    if comm_agent is None:
        # Fallback: use raw response from first result
        raw = agent_results[0].get("response", "") if agent_results else ""
        return {**state, "agent_response": raw or "I couldn't process that."}

    comm_input = AgentInput(
        user_id=state["user_id"],
        message=state["message"],
        intent=state.get("intent", "general"),
        context=AgentContext(
            agent_results=agent_results,
            task="Summarize the financial data for the user in a helpful way.",
        ),
    )

    comm_output = comm_agent.invoke(comm_input)

    return {
        **state,
        "agent_response": comm_output.response,
    }


def validate_response(state: CoordinatorState) -> CoordinatorState:
    try:
        refined_response, metadata = validate_and_refine(
            response=state.get("agent_response", ""),
            intent=state.get("intent", "general"),
            original_data=None,
        )

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
        return state


def format_response(state: CoordinatorState) -> CoordinatorState:
    user_id = state["user_id"]
    _conversation_store.add(user_id, "user", state["message"])
    _conversation_store.add(user_id, "assistant", state.get("agent_response", ""))

    return {
        **state,
        "conversation_history": _conversation_store.get(user_id),
    }


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_coordinator_graph():
    graph = StateGraph(CoordinatorState)

    graph.add_node("classify", classify_intent)
    graph.add_node("plan_tasks", plan_tasks)
    graph.add_node("execute_task", execute_task)
    graph.add_node("synthesize", synthesize_response)
    graph.add_node("validate", validate_response)
    graph.add_node("respond", format_response)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "plan_tasks")
    graph.add_edge("plan_tasks", "execute_task")
    graph.add_conditional_edges("execute_task", check_remaining)
    graph.add_edge("synthesize", "validate")
    graph.add_edge("validate", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


# Singleton compiled graph
coordinator_graph = build_coordinator_graph()
