from __future__ import annotations

import logging

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

        # 3. Format structured agent results for NLG (no json.dumps)
        agent_results = ctx.agent_results
        if agent_results:
            # Short-circuit to deterministic balance template when possible
            balance_response = self._maybe_render_balance_response(
                persona, agent_results
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
        if agent_results:
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
        self, persona: str, agent_results: list[dict]
    ) -> str | None:
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
