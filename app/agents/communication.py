from __future__ import annotations

import logging
import re
from typing import Any

from app.agents.base import BaseAgent, AgentInput, AgentOutput, AgentStatus
from app.services.nlg import generate_response
from app.services.nudge import can_send_nudge, record_nudge
from app.services.health_score import compute_health_score

logger = logging.getLogger(__name__)


class CommunicationAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "CommunicationAgent"

    @property
    def description(self) -> str:
        return (
            "Pure NLG engine that translates structured agent data into empathetic, "
            "persona-adapted natural language responses. Handles nudge fatigue control."
        )

    @property
    def capabilities(self) -> list[str]:
        return [
            "natural_language_generation",
            "persona_adaptation",
            "nudge_management",
            "conversational_response",
            "multi_result_synthesis",
        ]

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        user_id = agent_input.user_id
        ctx = agent_input.context

        # 1. Nudge Fatigue Check
        if ctx.is_nudge:
            allowed, reason = can_send_nudge(user_id)
            if not allowed:
                return AgentOutput(
                    response=f"[Nudge Blocked: {reason}]",
                    agent_name=self.name,
                    confidence=1.0,
                    metadata={"nudge": "blocked", "reason": reason},
                )

        # 2. Get Persona
        persona = ctx.persona
        if not persona:
            persona = self._get_persona(user_id)

        planning_result = self._plan_schedule_action(
            requested_intent=agent_input.intent,
            user_message=agent_input.message,
            history=ctx.history,
            conversation_state=self._conversation_state_from_context(ctx),
            parsed_parameters=self._planning_parameters_from_context(ctx),
        )
        if planning_result:
            if ctx.is_nudge:
                record_nudge(user_id)
            return AgentOutput(
                response=planning_result["response"],
                agent_name=self.name,
                confidence=float(planning_result.get("confidence", 0.93)),
                metadata={
                    "provider": "planning_executor",
                    "model": "deterministic",
                    "persona": persona,
                    "is_nudge": ctx.is_nudge,
                    "pending_state": planning_result.get("pending_state"),
                    "clear_pending": bool(planning_result.get("clear_pending", False)),
                    "action": planning_result.get("action"),
                },
            )

        # 3. Format structured agent results for NLG (no json.dumps)
        agent_results = ctx.agent_results
        if agent_results:
            # Short-circuit to deterministic balance template when possible
            balance_response = self._maybe_render_balance_response(
                persona,
                agent_results,
                requested_intent=agent_input.intent,
                user_message=agent_input.message,
                task=ctx.task,
            )
            if balance_response:
                if ctx.is_nudge:
                    record_nudge(user_id)
                return AgentOutput(
                    response=balance_response,
                    agent_name=self.name,
                    confidence=0.95,
                    metadata={
                        "provider": "balance_template",
                        "model": "deterministic",
                        "persona": persona,
                        "is_nudge": ctx.is_nudge,
                    },
                )
        if agent_results and self._can_use_agent_results_for_intent(
            agent_results,
            agent_input.intent,
        ):
            data_context = agent_results
        else:
            data_context = ctx.data or f"User query: {agent_input.message}"

        task_description = (
            ctx.task or "Provide a helpful, personalized response summarizing the data."
        )

        # 4. Generate NLG Response
        nlg_result = generate_response(
            persona=persona,
            data_context=data_context,
            task_description=task_description,
        )

        # 5. Record nudge if sent successfully
        if ctx.is_nudge:
            record_nudge(user_id)

        return AgentOutput(
            response=nlg_result["text"],
            agent_name=self.name,
            confidence=0.9,
            metadata={
                "provider": nlg_result["provider"],
                "model": nlg_result.get("model"),
                "tokens": nlg_result.get("tokens"),
                "persona": nlg_result["persona"],
                "is_nudge": ctx.is_nudge,
            },
            tokens_used=nlg_result.get("tokens"),
        )

    def _get_persona(self, user_id: str) -> str:
        """Fetch user persona from health score computation."""
        try:
            health_data = compute_health_score(user_id)
            return health_data.get("persona", {}).get("persona", "Balanced Manager")
        except Exception as e:
            logger.warning("Could not fetch persona for %s: %s", user_id, e)
            return "Balanced Manager"

    def _maybe_render_balance_response(
        self,
        persona: str,
        agent_results: list[dict],
        *,
        requested_intent: str,
        user_message: str,
        task: str | None,
    ) -> str | None:
        if not self._is_balance_query(
            requested_intent=requested_intent,
            user_message=user_message,
            task=task,
        ):
            return None

        if self._has_non_balance_success(agent_results):
            return None

        for result in agent_results:
            metadata = result.get("metadata") or {}
            if metadata.get("intent_handled") != "balance":
                continue
            status = result.get("status")
            if status not in (AgentStatus.success, AgentStatus.needs_input):
                continue
            current = self._coerce_float(metadata.get("current_balance"))
            available = self._coerce_float(metadata.get("available_balance"))
            if current is None and available is None:
                continue
            if current is None:
                current = available
            if available is None:
                available = current
            symbol = self._resolve_currency_symbol(metadata.get("currency"))
            total_str = self._format_currency(available, symbol)
            current_str = self._format_currency(current, symbol)
            tone = self._persona_opening(persona)
            spend_line = f"You can comfortably spend around {total_str} without dipping into pending funds."
            return f"{tone}Total balance {total_str}. Current balance {current_str}. {spend_line}"
        return None

    def _maybe_render_schedule_guidance(
        self,
        *,
        requested_intent: str,
        user_message: str,
        history: list[dict] | None = None,
    ) -> str | None:
        if not self._is_schedule_query(requested_intent, user_message):
            return None

        day = self._extract_day_of_month(user_message)
        amount = self._extract_amount(user_message)

        # Continue multi-turn schedule capture (e.g. first turn has day, second has amount).
        if history:
            if day is None:
                day = self._extract_recent_schedule_day(history)
            if amount is None:
                amount = self._extract_recent_schedule_amount(history)

        if amount is None and day is not None:
            return (
                f"I understood you want to schedule rent on day {day} every month. "
                "Please share the rent amount as well (example: 25000), and I will guide the next step."
            )

        if day is None and amount is not None:
            return (
                f"I captured the rent amount as INR {amount:,.2f}. "
                "Please share the day of month (for example: 5th), and I will guide the next step."
            )

        if day is None and amount is None:
            return (
                "I can help with recurring rent scheduling. "
                "Please include both amount and day of month, for example: 'pay rent 25000 every month on 5th'."
            )

        return (
            f"I captured a recurring rent schedule of INR {amount:,.2f} on day {day} each month. "
            "Use Integration Lab > Planning or POST /api/planning/schedule-from-text to create it now."
        )

    @staticmethod
    def _conversation_state_from_context(ctx) -> dict[str, Any]:
        state = (
            ctx.model_extra.get("conversation_state")
            if hasattr(ctx, "model_extra")
            else None
        )
        if isinstance(state, dict):
            return state
        return {}

    @staticmethod
    def _planning_parameters_from_context(ctx) -> dict[str, Any]:
        extras = ctx.model_extra if hasattr(ctx, "model_extra") else {}
        params: dict[str, Any] = {}

        if ctx.amount is not None:
            params["amount"] = ctx.amount

        if isinstance(extras, dict):
            if "amount" in extras and params.get("amount") is None:
                params["amount"] = extras.get("amount")
            if "day_of_month" in extras:
                params["day_of_month"] = extras.get("day_of_month")
            if "source_text" in extras:
                params["source_text"] = extras.get("source_text")
        return params

    def _plan_schedule_action(
        self,
        *,
        requested_intent: str,
        user_message: str,
        history: list[dict],
        conversation_state: dict[str, Any],
        parsed_parameters: dict[str, Any],
    ) -> dict[str, Any] | None:
        pending_intent = str(conversation_state.get("pending_intent") or "").lower()
        if requested_intent != "planning" and pending_intent != "planning":
            return None

        current_message_has_schedule_hints = self._is_schedule_query("", user_message)
        if (
            pending_intent == "planning"
            and requested_intent != "planning"
            and not self._is_schedule_follow_up_message(user_message)
        ):
            return None

        pending = conversation_state.get("planning")
        if not isinstance(pending, dict):
            pending = {}

        current_day = self._extract_day_of_month(user_message)
        current_amount = self._extract_amount(user_message)

        if current_day is None:
            current_day = self._coerce_day(parsed_parameters.get("day_of_month"))
        if current_amount is None:
            current_amount = self._coerce_amount(parsed_parameters.get("amount"))

        day = current_day
        if day is None:
            day = self._coerce_day(pending.get("day_of_month"))
        if day is None:
            day = self._extract_recent_schedule_day(history)

        amount = current_amount
        if amount is None:
            amount = self._coerce_amount(pending.get("amount"))
        if amount is None:
            amount = self._extract_recent_schedule_amount(history)

        source_text_candidate = parsed_parameters.get("source_text")
        if not source_text_candidate and current_message_has_schedule_hints:
            source_text_candidate = user_message

        source_text = str(
            source_text_candidate
            or pending.get("source_text")
            or self._find_recent_schedule_request_text(history)
            or user_message
        ).strip()

        if amount is None:
            return {
                "response": (
                    "Understood. I will set this recurring payment schedule. "
                    "Please share the payment amount."
                ),
                "confidence": 0.93,
                "pending_state": {
                    "pending_intent": "planning",
                    "planning": {
                        "flow": "schedule_from_text",
                        "source_text": source_text,
                        "day_of_month": day,
                        "amount": None,
                        "autopay_enabled": True,
                        "requires_approval": True,
                    },
                },
                "clear_pending": False,
                "action": None,
            }

        if day is None:
            return {
                "response": (
                    f"Got the amount INR {amount:,.2f}. "
                    "Please share the day of month for this recurring payment."
                ),
                "confidence": 0.93,
                "pending_state": {
                    "pending_intent": "planning",
                    "planning": {
                        "flow": "schedule_from_text",
                        "source_text": source_text,
                        "day_of_month": None,
                        "amount": amount,
                        "autopay_enabled": True,
                        "requires_approval": True,
                    },
                },
                "clear_pending": False,
                "action": None,
            }

        schedule_text = source_text
        lower_schedule = schedule_text.lower()
        if (
            "every month" not in lower_schedule
            and "monthly" not in lower_schedule
            and "recurring" not in lower_schedule
        ):
            schedule_text = f"{schedule_text} every month"
        if self._extract_day_of_month(schedule_text) is None:
            schedule_text = f"{schedule_text} on {day}th"
        if self._extract_amount(schedule_text) is None:
            schedule_text = f"{schedule_text} of {amount:.2f}"
        if "remind" not in schedule_text.lower():
            schedule_text = f"{schedule_text} and remind me"

        return {
            "response": (
                f"Got it. Creating recurring payment schedule for INR {amount:,.2f} on day {day} now."
            ),
            "confidence": 0.95,
            "pending_state": None,
            "clear_pending": True,
            "action": {
                "type": "create_schedule_from_text",
                "text": schedule_text,
                "default_amount": amount,
                "autopay_enabled": True,
                "requires_approval": True,
            },
        }

    @staticmethod
    def _coerce_day(value: Any) -> int | None:
        try:
            day = int(value)
        except (TypeError, ValueError):
            return None
        if 1 <= day <= 31:
            return day
        return None

    @staticmethod
    def _coerce_amount(value: Any) -> float | None:
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return None
        if amount <= 0:
            return None
        return amount

    @classmethod
    def _find_recent_schedule_request_text(cls, history: list[dict]) -> str | None:
        for msg in reversed(history[-10:]):
            if str(msg.get("role") or "").lower() != "user":
                continue
            content = str(msg.get("content") or "").strip()
            if not content:
                continue
            if cls._is_schedule_query("", content):
                return content
        return None

    @classmethod
    def _extract_recent_schedule_day(cls, history: list[dict]) -> int | None:
        for msg in reversed(history[-8:]):
            if str(msg.get("role") or "").lower() != "user":
                continue
            content = str(msg.get("content") or "")
            if not cls._is_schedule_query("", content):
                continue
            day = cls._extract_day_of_month(content)
            if day is not None:
                return day
        return None

    @classmethod
    def _extract_recent_schedule_amount(cls, history: list[dict]) -> float | None:
        for msg in reversed(history[-8:]):
            if str(msg.get("role") or "").lower() != "user":
                continue
            content = str(msg.get("content") or "")
            if not cls._is_schedule_query("", content):
                continue
            amount = cls._extract_amount(content)
            if amount is not None:
                return amount
        return None

    @staticmethod
    def _can_use_agent_results_for_intent(
        agent_results: list[dict],
        requested_intent: str,
    ) -> bool:
        normalized = (requested_intent or "").strip().lower()
        if normalized in {"", "general", "planning"}:
            return False

        result_intents = {
            str((result.get("metadata") or {}).get("intent_handled", ""))
            .strip()
            .lower()
            for result in agent_results
            if (result.get("metadata") or {}).get("intent_handled")
        }
        if not result_intents:
            return True
        return normalized in result_intents

    @staticmethod
    def _has_non_balance_success(agent_results: list[dict]) -> bool:
        for result in agent_results:
            status = result.get("status")
            if status not in (AgentStatus.success, AgentStatus.needs_input):
                continue
            metadata = result.get("metadata") or {}
            intent_handled = str(metadata.get("intent_handled") or "").strip().lower()
            if intent_handled and intent_handled != "balance":
                return True
        return False

    @staticmethod
    def _is_balance_query(
        *,
        requested_intent: str,
        user_message: str,
        task: str | None,
    ) -> bool:
        query_text = f"{user_message} {task or ''}".lower()
        balance_hints = (
            "balance",
            "current balance",
            "available balance",
            "account balance",
            "how much do i have",
            "how much money",
        )
        has_balance_hint = any(hint in query_text for hint in balance_hints)
        if has_balance_hint:
            return True

        # Avoid deterministic balance responses when intent was misclassified.
        return False

    @staticmethod
    def _is_schedule_query(requested_intent: str, user_message: str) -> bool:
        if (requested_intent or "").strip().lower() == "planning":
            return True
        lowered = user_message.lower()
        schedule_hints = (
            "schedule",
            "shedule",
            "recurring",
            "autopay",
            "pay rent",
            "every month",
            "monthly",
        )
        return any(hint in lowered for hint in schedule_hints)

    @staticmethod
    def _is_schedule_follow_up_message(user_message: str) -> bool:
        normalized = re.sub(r"\s+", " ", user_message.lower()).strip()
        if not normalized:
            return False

        if re.fullmatch(
            r"(?:₹|rs\.?|inr)?\s*\d+(?:\.\d+)?\s*(?:k|thousand|lakh|lakhs|crore|crores|cr)?",
            normalized,
        ):
            return True

        if re.fullmatch(r"(?:on\s+)?\d{1,2}(?:st|nd|rd|th)?", normalized):
            return True

        if CommunicationAgent._is_schedule_query("", normalized):
            return True

        confirmations = {
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
        return normalized in confirmations

    @staticmethod
    def _extract_day_of_month(text: str) -> int | None:
        lowered = text.lower()
        match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", lowered)
        if not match:
            match = re.search(r"\bon\s+(\d{1,2})\b", lowered)
        if not match:
            return None
        day = int(match.group(1))
        if 1 <= day <= 31:
            return day
        return None

    @staticmethod
    def _extract_amount(text: str) -> float | None:
        match = re.search(
            r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(k|thousand|lakh|lakhs|crore|crores|cr)?\b",
            text.lower(),
        )
        if not match:
            return None
        amount = float(match.group(1))
        unit = (match.group(2) or "").lower()
        multipliers = {
            "k": 1_000,
            "thousand": 1_000,
            "lakh": 100_000,
            "lakhs": 100_000,
            "crore": 10_000_000,
            "crores": 10_000_000,
            "cr": 10_000_000,
        }
        if unit:
            amount *= multipliers.get(unit, 1)
        if amount <= 0:
            return None
        return amount

    @staticmethod
    def _coerce_float(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _resolve_currency_symbol(currency: str | None) -> str:
        if not currency:
            return "₹"
        upper = currency.upper()
        if upper == "INR":
            return "₹"
        if upper == "USD":
            return "$"
        if upper == "EUR":
            return "€"
        return currency

    @staticmethod
    def _format_currency(value: float, symbol: str) -> str:
        if value is None:
            return ""
        return f"{symbol} {value:,.2f}"

    @staticmethod
    def _persona_opening(persona: str) -> str:
        openings = {
            "Cautious Saver": "Let's keep things steady: ",
            "Social Spender": "Good news - ",
            "Impulse Buyer": "Quick heads-up: ",
        }
        return openings.get(persona, "Here's where you stand: ")
