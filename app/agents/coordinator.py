from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, TypedDict

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

try:
    from langgraph.graph import StateGraph, END
except ImportError:  # pragma: no cover - fallback path for lightweight dev/test envs
    END = "__end__"

    class _CompiledStateGraph:
        def __init__(
            self,
            *,
            nodes: dict[str, Any],
            entry_point: str,
            edges: dict[str, list[str]],
            conditional_edges: dict[str, Any],
        ) -> None:
            self._nodes = nodes
            self._entry_point = entry_point
            self._edges = edges
            self._conditional_edges = conditional_edges

        def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
            current = self._entry_point
            working_state = dict(state)

            while current != END:
                node = self._nodes[current]
                next_state = node(working_state)
                if next_state is not None:
                    working_state = next_state

                if current in self._conditional_edges:
                    current = self._conditional_edges[current](working_state)
                    continue

                next_nodes = self._edges.get(current, [])
                current = next_nodes[0] if next_nodes else END

            return working_state

    class StateGraph:
        def __init__(self, _state_type: Any) -> None:
            self._nodes: dict[str, Any] = {}
            self._edges: dict[str, list[str]] = {}
            self._conditional_edges: dict[str, Any] = {}
            self._entry_point: str | None = None

        def add_node(self, name: str, handler: Any) -> None:
            self._nodes[name] = handler

        def set_entry_point(self, name: str) -> None:
            self._entry_point = name

        def add_edge(self, source: str, target: str) -> None:
            self._edges.setdefault(source, []).append(target)

        def add_conditional_edges(self, source: str, router: Any) -> None:
            self._conditional_edges[source] = router

        def compile(self) -> _CompiledStateGraph:
            if not self._entry_point:
                raise ValueError("Coordinator graph entry point is not set")
            logger.warning(
                "langgraph is not installed; using a lightweight coordinator graph fallback"
            )
            return _CompiledStateGraph(
                nodes=self._nodes,
                entry_point=self._entry_point,
                edges=self._edges,
                conditional_edges=self._conditional_edges,
            )


if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session as DBSession
    from app.models.user import User
else:  # LangGraph introspects type hints at runtime
    DBSession = Any  # type: ignore[assignment]
    User = Any  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Conversation memory (abstracted via ConversationStore protocol)
# ---------------------------------------------------------------------------
_conversation_store = InMemoryConversationStore(max_history=10)


def get_conversation_history(user_id: str) -> list[dict]:
    return _conversation_store.get(user_id)


def get_conversation_state(user_id: str) -> dict:
    return _conversation_store.get_state(user_id)


def set_conversation_state(user_id: str, state: dict) -> None:
    _conversation_store.set_state(user_id, state)


def clear_conversation_state(user_id: str) -> None:
    _conversation_store.clear_state(user_id)


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
        description="One of: actions, balance, forecast, health_score, what_if, auto_savings, opportunity, affordability, planning, general"
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


class ActionIntentResult(BaseModel):
    """Signal that user is asking the assistant to perform an action, not just answer."""

    is_action_request: bool = Field(
        description="True when user asks assistant to execute or schedule a task"
    )
    action_family: str = Field(
        default="none",
        description="One of: schedule_payment, manage_beneficiary, manage_schedule, action_approval, none",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    amount: float | None = None
    day_of_month: int | None = None
    recurring: bool | None = None


ACTION_INTENT_PROMPT = """You are classifying whether a user message is an actionable instruction.

Classify as is_action_request=true when user asks to DO something (pay, schedule, set up recurring payment, approve/reject an action, create beneficiary, run/cancel schedule).
Classify as is_action_request=false when user only asks for information (balance, forecast, analysis, score).

User message: "{user_message}"
Recent context: {conversation_summary}

Return JSON with:
- is_action_request: boolean
- action_family: schedule_payment | manage_beneficiary | manage_schedule | action_approval | none
- confidence: 0-1
- amount: number or null
- day_of_month: integer 1-31 or null
- recurring: boolean or null

Guidelines:
- Bills/rent/utility payment instructions should be schedule_payment.
- If there is due day/date language like "on 20", extract day_of_month where possible.
- If wording implies monthly/recurring/autopay, set recurring=true.
"""


# ---------------------------------------------------------------------------
# Intent-to-agent mapping (deterministic — single source of truth)
# ---------------------------------------------------------------------------

_INTENT_TO_AGENT: dict[str, str] = {
    "actions": "CommunicationAgent",
    "balance": "IntelligenceAgent",
    "forecast": "IntelligenceAgent",
    "health_score": "IntelligenceAgent",
    "what_if": "IntelligenceAgent",
    "affordability": "IntelligenceAgent",
    "advice": "IntelligenceAgent",
    "auto_savings": "AutoSavingsAgent",
    "opportunity": "OpportunityAgent",
    "planning": "CommunicationAgent",
    "general": "CommunicationAgent",
}


# ---------------------------------------------------------------------------
# Structured Classification Prompt (agent_name REMOVED)
# ---------------------------------------------------------------------------

INTENT_CLASSIFICATION_PROMPT = """You are an intelligent financial assistant coordinator that routes user queries to the appropriate specialist.

Available capabilities:
{agent_descriptions}

Intent codes (use these exactly):
- actions: Execute or approve actions (pay/transfer/approve/reject)
- balance: Account balance and transaction queries
- forecast: Future balance predictions
- health_score: Financial health assessment
- what_if: Scenario analysis ("what if I spend...", impact analysis)
- affordability: "Can I afford...", "should I buy..." purchase questions
- advice: "How can I save more", "improve my spending", "where am I overspending", "cut back" advice
- auto_savings: Savings advice and micro-savings
- opportunity: Product recommendations and offers
- planning: Scheduling, recurring payment setup, reminder/checklist planning requests
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
    "planning": [
        "schedule",
        "shedule",
        "recurring",
        "autopay",
        "every month",
        "monthly",
        "pay rent",
        "due on",
    ],
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
    "advice": [
        "improve",
        "suggestions",
        "save more",
        "cut back",
        "spend less",
        "overspending",
        "how to improve",
        "ways to save",
        "spending tips",
        "financial advice",
        "better habits",
        "where am i spending",
        "where am i overspending",
    ],
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

_SCHEDULE_SIGNAL_HINTS = {
    "schedule",
    "shedule",
    "recurring",
    "autopay",
    "every month",
    "monthly",
    "due on",
    "remind",
    "add bill",
    "add a bill",
}

_PLANNING_FOLLOW_UP_CONFIRMATIONS = {
    "yes",
    "y",
    "ok",
    "okay",
    "sure",
    "go ahead",
    "proceed",
    "continue",
    "confirm",
    "do it",
}

_ACTIONS_FOLLOW_UP_CONFIRMATIONS = {
    "yes",
    "y",
    "ok",
    "okay",
    "sure",
    "go ahead",
    "proceed",
    "continue",
    "confirm",
    "approve",
    "do it",
}

_ACTIONS_FOLLOW_UP_REJECTIONS = {
    "no",
    "n",
    "cancel",
    "stop",
    "reject",
    "don't",
    "do not",
}


def _looks_like_schedule_request(message: str) -> bool:
    lower = message.lower()
    return any(hint in lower for hint in _SCHEDULE_SIGNAL_HINTS)


_AMOUNT_ONLY_PATTERN = re.compile(
    r"^\s*(?:₹|rs\.?|inr)?\s*\d+(?:\.\d+)?\s*(?:k|thousand|lakh|lakhs|lac|lacs|crore|crores|cr)?\s*$"
)


def _is_amount_only_message(message: str) -> bool:
    normalized = message.replace(",", "").strip().lower()
    if not normalized:
        return False
    return bool(_AMOUNT_ONLY_PATTERN.match(normalized))


def _history_has_schedule_context(history: list[dict]) -> bool:
    # Only consider the most recent turn pair to avoid stale schedule carry-over.
    for msg in reversed(history[-2:]):
        content = str(msg.get("content") or "")
        role = str(msg.get("role") or "").lower()
        lowered = content.lower()

        if role == "user" and _looks_like_schedule_request(content):
            return True

        if role == "assistant" and (
            "schedule" in lowered
            or "recurring" in lowered
            or ("rent" in lowered and "amount" in lowered)
        ):
            return True

    return False


def _contextual_intent_override(
    message: str,
    history: list[dict],
) -> ClassificationResult | None:
    if _looks_like_schedule_request(message):
        return ClassificationResult(
            intent="planning",
            confidence=0.8,
            parameters={},
        )

    if _is_amount_only_message(message) and _history_has_schedule_context(history):
        amount = _extract_amount_from_text(message)
        parameters: dict = {}
        if amount is not None:
            parameters["amount"] = amount
        return ClassificationResult(
            intent="planning",
            confidence=0.78,
            parameters=parameters,
        )

    return None


def _ordered_keyword_intents(message_lower: str) -> list[str]:
    scored: list[tuple[int, str]] = []
    for intent, keywords in _INTENT_KEYWORDS.items():
        hits = [
            message_lower.find(keyword)
            for keyword in keywords
            if keyword in message_lower
        ]
        if hits:
            scored.append((min(hits), intent))

    scored.sort(key=lambda item: item[0])
    return [intent for _, intent in scored]


def _is_pending_planning_follow_up(message: str, history: list[dict]) -> bool:
    normalized = re.sub(r"\s+", " ", message.lower()).strip()
    if not normalized:
        return False

    if _is_amount_only_message(normalized):
        return True

    if _extract_day_of_month_from_text(normalized) is not None:
        return True

    if _looks_like_schedule_request(normalized):
        return True

    if (
        normalized in _PLANNING_FOLLOW_UP_CONFIRMATIONS
        and _history_has_schedule_context(history)
    ):
        return True

    return False


def _should_resume_pending_intent(
    pending_intent: str,
    *,
    message: str,
    history: list[dict],
) -> bool:
    if pending_intent == "planning":
        return _is_pending_planning_follow_up(message, history)
    if pending_intent == "actions":
        return _is_pending_actions_follow_up(message)
    return True


def _is_pending_actions_follow_up(message: str) -> bool:
    normalized = re.sub(r"\s+", " ", message.lower()).strip()
    if not normalized:
        return False

    if _is_amount_only_message(normalized):
        return True

    if normalized in _ACTIONS_FOLLOW_UP_CONFIRMATIONS:
        return True

    if normalized in {"pay now", "later", "not now", "snooze", "remind later"}:
        return True

    if normalized in _ACTIONS_FOLLOW_UP_REJECTIONS:
        return True

    if re.match(r"^(approve|reject|cancel)\b", normalized):
        return True

    if _extract_amount_from_text(normalized) is not None and any(
        token in normalized for token in ("actually", "change", "update", "instead")
    ):
        return True

    return False


def _detect_tool_action_request(message: str) -> dict | None:
    """Deterministic detection for action-engine tool requests (pay/transfer/note).

    This is intentionally conservative: it triggers only for imperative phrasing and
    avoids schedule/recurring language which is handled by the planning flow.
    """

    lower = message.lower().strip()
    if not lower:
        return None

    # Avoid hijacking advisory questions.
    if any(
        token in lower for token in ("can i ", "should i ", "could i ", "how do i ")
    ):
        return None

    imperative = (
        lower.startswith(("pay ", "transfer ", "move ", "send ", "note ", "record "))
        or "please" in lower
        or "can you" in lower
        or "could you" in lower
    )
    if not imperative:
        return None

    # Recurring/scheduled payments belong to the planning flow.
    if _looks_like_schedule_request(message):
        return None
    if _is_recurring_signal(message):
        return None
    if _extract_day_of_month_from_text(message) is not None:
        return None

    action_type: str | None = None
    if "transfer" in lower and (
        "savings" in lower or "to savings" in lower or "save" in lower
    ):
        action_type = "transfer_savings"
    elif "pay" in lower and "rent" in lower:
        action_type = "pay_rent"
    elif "pay" in lower and ("gas" in lower or "lpg" in lower):
        action_type = "pay_gas"
    elif "pay" in lower and (
        "utility" in lower
        or "electric" in lower
        or "electricity" in lower
        or "water" in lower
    ):
        action_type = "pay_utility"
    elif "pay" in lower and "bill" in lower:
        action_type = "pay_bill"
    elif "note" in lower or "remember" in lower or "record" in lower:
        action_type = "record_note"

    if not action_type:
        return None

    payload: dict = {}

    if action_type == "record_note":
        payload["message"] = message.strip()
        return {"action_type": action_type, "action_payload": payload}

    amount = _extract_amount_from_text(message)
    if amount is not None:
        payload["amount"] = float(amount)

    if action_type in {"pay_rent", "pay_bill", "pay_gas", "pay_utility"}:
        payload.setdefault("description", "Payment requested via chat")
    if action_type == "transfer_savings":
        payload.setdefault("description", "Savings transfer requested via chat")

    return {"action_type": action_type, "action_payload": payload}


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


def _extract_day_of_month_from_text(message: str) -> int | None:
    lowered = message.lower()
    ordinal = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", lowered)
    if ordinal:
        day = int(ordinal.group(1))
        if 1 <= day <= 31:
            return day

    on_day = re.search(r"\bon\s+(\d{1,2})\b", lowered)
    if on_day:
        day = int(on_day.group(1))
        if 1 <= day <= 31:
            return day
    return None


def _is_recurring_signal(message: str) -> bool:
    lower = message.lower()
    return any(
        signal in lower
        for signal in (
            "every month",
            "monthly",
            "recurring",
            "autopay",
            "each month",
        )
    )


def _classify_action_request_with_llm(
    message: str,
    history: list[dict],
) -> ActionIntentResult | None:
    llm, provider = get_llm_provider(temperature=0.0)
    if not llm:
        return None

    try:
        structured_llm = llm.with_structured_output(ActionIntentResult)

        conv_summary = "No previous context"
        if history:
            recent = history[-3:]
            conv_summary = " | ".join(
                [f"{msg['role']}: {msg['content'][:50]}" for msg in recent]
            )

        prompt = PromptTemplate.from_template(ACTION_INTENT_PROMPT)
        chain = prompt | structured_llm
        result: ActionIntentResult = chain.invoke(
            {
                "user_message": message,
                "conversation_summary": conv_summary,
            }
        )
        logger.info(
            "⚙️ Action-intent classification (%s): is_action=%s family=%s conf=%.2f",
            provider,
            result.is_action_request,
            result.action_family,
            result.confidence,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("Action-intent LLM classification failed: %s", exc)
        return None


def _classify_action_request_fallback(message: str) -> ActionIntentResult | None:
    lower = message.lower()
    amount = _extract_amount_from_text(message)
    day = _extract_day_of_month_from_text(message)

    action_verbs = (
        "pay",
        "schedule",
        "set up",
        "setup",
        "auto",
        "remind",
        "book",
        "create",
    )
    payment_objects = (
        "bill",
        "bills",
        "electricity",
        "utility",
        "rent",
        "gas",
        "emi",
        "loan",
        "insurance",
        "subscription",
        "fees",
        "fee",
    )

    has_action_verb = any(token in lower for token in action_verbs)
    has_payment_object = any(token in lower for token in payment_objects)
    recurring = _is_recurring_signal(message)

    if (has_action_verb and has_payment_object and amount is not None) or (
        has_action_verb and amount is not None and day is not None
    ):
        return ActionIntentResult(
            is_action_request=True,
            action_family="schedule_payment",
            confidence=0.74,
            amount=amount,
            day_of_month=day,
            recurring=recurring or day is not None,
        )
    return None


def _detect_action_request(
    message: str, history: list[dict]
) -> ActionIntentResult | None:
    llm_result = _classify_action_request_with_llm(message, history)
    if llm_result and llm_result.is_action_request and llm_result.confidence >= 0.65:
        return llm_result

    fallback_result = _classify_action_request_fallback(message)
    if fallback_result:
        return fallback_result

    return llm_result


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

        # Guardrail: schedule/planning phrasing should not be routed as balance.
        heuristic = _classify_intent_keywords(message)
        if heuristic.intent == "planning" and result.intent == "balance":
            logger.info(
                "🛟 Heuristic override: schedule-like query rerouted from balance to planning"
            )
            return ClassificationResult(
                intent="planning",
                confidence=max(heuristic.confidence, 0.75),
                parameters=result.parameters,
                secondary_intent=result.secondary_intent,
            )

        # Secondary intent fallback: if LLM missed a secondary intent, check keywords
        if not result.secondary_intent and heuristic.secondary_intent:
            logger.info(
                "📌 Secondary intent detected by keywords: '%s' (LLM missed it)",
                heuristic.secondary_intent,
            )
            result.secondary_intent = heuristic.secondary_intent

        return result

    except Exception as e:
        logger.warning(
            "❌ Structured LLM classification failed: %s, falling back to keywords", e
        )
        return _classify_intent_keywords(message)


def _classify_intent_keywords(message: str) -> ClassificationResult:
    """Fallback keyword-based classification with regex entity extraction."""
    message_lower = message.lower()

    if _looks_like_schedule_request(message):
        return ClassificationResult(
            intent="planning",
            confidence=0.72,
            parameters={},
        )

    matched_intents = _ordered_keyword_intents(message_lower)
    detected_intent = matched_intents[0] if matched_intents else "general"
    secondary_intent = matched_intents[1] if len(matched_intents) > 1 else None

    if detected_intent == "balance":
        has_savings_signal = any(
            keyword in message_lower for keyword in _INTENT_KEYWORDS["auto_savings"]
        )
        if has_savings_signal:
            secondary_intent = "auto_savings"

    # Extract amount via regex for intents that need it
    parameters: dict = {}
    amount_target_intent = detected_intent
    if amount_target_intent not in (
        "what_if",
        "affordability",
    ) and secondary_intent in (
        "what_if",
        "affordability",
    ):
        amount_target_intent = secondary_intent

    if amount_target_intent in ("what_if", "affordability"):
        amount = _extract_amount_from_text(message)
        if amount is not None:
            param_key = (
                "expense_amount"
                if amount_target_intent == "what_if"
                else "purchase_amount"
            )
            parameters[param_key] = amount

    logger.info(
        "🔑 Keyword matched: intent='%s', secondary='%s', confidence=%.2f, params=%s",
        detected_intent,
        secondary_intent,
        0.62 if secondary_intent else 0.6,
        parameters,
    )
    return ClassificationResult(
        intent=detected_intent,
        confidence=0.62 if secondary_intent else 0.6,
        parameters=parameters,
        secondary_intent=secondary_intent,
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
    conversation_state: dict
    pending_intent_ignored: bool
    response_metadata: dict
    error: str
    db: DBSession
    current_user: User


def _extract_planned_action_metadata(
    agent_results: list[dict],
) -> dict[str, Any] | None:
    for result in reversed(agent_results):
        metadata = result.get("metadata")
        if not isinstance(metadata, dict):
            continue
        action = metadata.get("action")
        if isinstance(action, dict):
            return metadata
    return None


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def classify_intent(state: CoordinatorState) -> CoordinatorState:
    """Classify user intent using structured LLM output, with keyword fallback."""
    message = state["message"]
    history = state.get("conversation_history", [])
    conversation_state = state.get("conversation_state", {})

    pending_intent_ignored = False
    pending_intent = conversation_state.get("pending_intent")
    should_resume_pending = (
        isinstance(pending_intent, str)
        and pending_intent in _INTENT_TO_AGENT
        and _should_resume_pending_intent(
            pending_intent,
            message=message,
            history=history,
        )
    )

    if should_resume_pending:
        parameters: dict = {}
        amount = _extract_amount_from_text(message)
        if amount is not None:
            parameters["amount"] = amount
        result = ClassificationResult(
            intent=pending_intent,
            confidence=0.96,
            parameters=parameters,
        )
    else:
        if isinstance(pending_intent, str) and pending_intent in _INTENT_TO_AGENT:
            pending_intent_ignored = True
            logger.info(
                "Ignoring stale pending intent '%s' for message '%s'",
                pending_intent,
                message,
            )

        tool_action = _detect_tool_action_request(message)
        if tool_action is not None:
            result = ClassificationResult(
                intent="actions",
                confidence=0.86,
                parameters=tool_action,
            )
        else:
            action_signal = _detect_action_request(message, history)
            if (
                action_signal
                and action_signal.is_action_request
                and action_signal.action_family == "schedule_payment"
            ):
                parameters: dict = {"source_text": message}
                if action_signal.amount is not None:
                    parameters["amount"] = float(action_signal.amount)
                if action_signal.day_of_month is not None:
                    parameters["day_of_month"] = int(action_signal.day_of_month)
                result = ClassificationResult(
                    intent="planning",
                    confidence=max(float(action_signal.confidence), 0.78),
                    parameters=parameters,
                )
            else:
                result = _contextual_intent_override(message, history)
                if result is None:
                    result = _classify_intent_with_llm(message, history)

    # Deterministic routing: intent → agent (code decides, not LLM)
    agent_name = _INTENT_TO_AGENT.get(result.intent, "CommunicationAgent")

    # ENHANCED: Check if LLM result doesn't match keyword findings
    # If keywords suggest multiple intents but LLM only found one, trust keywords
    if result.intent != "actions":
        keyword_result = _classify_intent_keywords(message)
        if keyword_result.secondary_intent and not result.secondary_intent:
            # LLM missed the secondary intent, use keyword fallback
            if keyword_result.secondary_intent != result.intent:
                logger.info(
                    "📌 Secondary intent detection (keyword fallback): primary='%s', secondary='%s'",
                    result.intent,
                    keyword_result.secondary_intent,
                )
                result.secondary_intent = keyword_result.secondary_intent

    return {
        **state,
        "intent": result.intent,
        "agent_name": agent_name,
        "classification_confidence": result.confidence,
        "classification_parameters": result.parameters,
        "classification_secondary_intent": result.secondary_intent,
        "pending_intent_ignored": pending_intent_ignored,
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
                "📋 Multi-intent detected: primary='%s' (%s), secondary='%s' (%s)",
                intent,
                agent_name,
                secondary_intent,
                secondary_agent,
            )
    else:
        if secondary_intent:
            logger.info(
                "ℹ️ Secondary intent same as primary, not creating additional task"
            )

    logger.info("📋 Tasks to execute: %d tasks", len(tasks))
    for idx, task in enumerate(tasks):
        logger.info(
            "   Task %d: intent='%s', agent='%s'",
            idx + 1,
            task["intent"],
            task["agent_name"],
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
        conversation_state=state.get("conversation_state", {}),
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

    # If CommunicationAgent already handled a single-turn request, reuse output directly.
    if (
        len(agent_results) == 1
        and agent_results[0].get("agent_name") == "CommunicationAgent"
    ):
        return {
            **state,
            "agent_response": agent_results[0].get("response", ""),
            "agent_used": "CommunicationAgent",
            "response_metadata": agent_results[0].get("metadata", {}),
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
            history=state.get("conversation_history", []),
            agent_results=agent_results,
            task="Summarize the financial data for the user in a helpful way.",
        ),
    )

    comm_output = comm_agent.invoke(comm_input)

    response_metadata = (
        comm_output.metadata if isinstance(comm_output.metadata, dict) else {}
    )
    planned_metadata = _extract_planned_action_metadata(agent_results)
    if planned_metadata:
        if not isinstance(response_metadata.get("action"), dict) and isinstance(
            planned_metadata.get("action"), dict
        ):
            response_metadata = {
                **response_metadata,
                "action": planned_metadata.get("action"),
            }

        if (
            response_metadata.get("pending_state") is None
            and planned_metadata.get("pending_state") is not None
        ):
            response_metadata = {
                **response_metadata,
                "pending_state": planned_metadata.get("pending_state"),
            }

        if (
            "clear_pending" not in response_metadata
            and "clear_pending" in planned_metadata
        ):
            response_metadata = {
                **response_metadata,
                "clear_pending": planned_metadata.get("clear_pending"),
            }

    agent_used = state.get("agent_used") or comm_output.agent_name
    return {
        **state,
        "agent_response": comm_output.response,
        "agent_used": agent_used,
        "response_metadata": response_metadata,
    }


def apply_actions(state: CoordinatorState) -> CoordinatorState:
    """Execute planner-emitted actions within the graph so compliance validates final text."""

    current_user = state.get("current_user")
    db = state.get("db")
    if current_user is None or db is None:
        return state

    metadata = state.get("response_metadata")
    if not isinstance(metadata, dict):
        return state

    try:
        from app.services.chat_action_executor import apply_planned_chat_action

        updated_response, updated_metadata = apply_planned_chat_action(
            agent_response=state.get("agent_response", ""),
            response_metadata=metadata,
            current_user=current_user,
            db=db,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to apply planned chat action")
        return state

    return {
        **state,
        "agent_response": updated_response,
        "response_metadata": updated_metadata,
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
    graph.add_node("apply_actions", apply_actions)
    graph.add_node("validate", validate_response)
    graph.add_node("respond", format_response)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "plan_tasks")
    graph.add_edge("plan_tasks", "execute_task")
    graph.add_conditional_edges("execute_task", check_remaining)
    graph.add_edge("synthesize", "apply_actions")
    graph.add_edge("apply_actions", "validate")
    graph.add_edge("validate", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


# Singleton compiled graph
coordinator_graph = build_coordinator_graph()
