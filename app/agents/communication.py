from __future__ import annotations

import logging
import re

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.services.nlg import generate_response
from app.services.nudge import can_send_nudge, record_nudge
from app.services.health_score import compute_health_score
from app.services.banking_client import get_balance_sync, BankingClientError

logger = logging.getLogger(__name__)


class CommunicationAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "CommunicationAgent"

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        user_id = agent_input.user_id
        message = agent_input.message
        lowered_message = message.lower()
        context = agent_input.context

        # 1. Nudge Fatigue Check (if system-initiated nudge)
        is_nudge = context.get("is_nudge", False)
        if is_nudge:
            allowed, reason = can_send_nudge(user_id)
            if not allowed:
                return AgentOutput(
                    response=f"[Nudge Blocked: {reason}]",
                    agent_name=self.name,
                    confidence=1.0,
                    metadata={"nudge": "blocked", "reason": reason},
                )

        # 2. Fast deterministic replies for direct account questions
        if self._is_balance_question(lowered_message):
            return self._handle_balance_question(user_id)

        purchase_amount = self._extract_purchase_amount(lowered_message)
        if purchase_amount is not None and self._is_purchase_question(lowered_message):
            return self._handle_affordability_question(user_id, purchase_amount)

        # 3. Get Persona (from Intelligence Agent's health score dataset)
        try:
            health_data = compute_health_score(user_id)
            persona = health_data.get("persona", {}).get("persona", "Balanced Manager")
        except Exception as e:
            logger.warning(f"Could not fetch persona for {user_id}: {e}")
            persona = "Balanced Manager"

        # 4. Formulate Data Context
        # Default behavior: generic financial query response formatting
        data_context = context.get("data", f"Financial inquiry: {message}")
        task_description = context.get(
            "task", "Provide a helpful, personalized response summarizing the data."
        )

        # 5. Generate NLG Response
        nlg_result = generate_response(
            persona=persona,
            data_context=data_context,
            task_description=task_description,
        )

        # 6. Record nudge if it was sent successfully
        if is_nudge:
            record_nudge(user_id)

        return AgentOutput(
            response=nlg_result["text"],
            agent_name=self.name,
            confidence=0.9,
            metadata={
                "provider": nlg_result["provider"],
                "persona": nlg_result["persona"],
                "is_nudge": is_nudge,
            },
        )

    @staticmethod
    def _is_balance_question(message: str) -> bool:
        return any(
            phrase in message
            for phrase in [
                "what is my balance",
                "what's my balance",
                "show my balance",
                "check my balance",
                "my balance",
                "available balance",
            ]
        )

    @staticmethod
    def _is_purchase_question(message: str) -> bool:
        return any(
            phrase in message
            for phrase in ["can i buy", "should i buy", "afford", "purchase", "buy"]
        )

    @staticmethod
    def _extract_purchase_amount(message: str) -> float | None:
        normalized = message.replace(",", "")
        match = re.search(r"(?:rs\.?|₹)?\s*(\d{3,7})(?:\s|$)", normalized)
        if not match:
            return None
        try:
            amount = float(match.group(1))
        except ValueError:
            return None
        return amount if amount > 0 else None

    def _handle_balance_question(self, user_id: str) -> AgentOutput:
        try:
            balance = get_balance_sync(user_id)
            current_balance = float(balance.get("current_balance", 0.0))
            available_balance = float(balance.get("available_balance", current_balance))
            response = (
                f"Your current balance is ₹{current_balance:,.0f} and available balance is ₹{available_balance:,.0f}. "
                "Would you like me to break this down with your recent spending trend?"
            )
            confidence = 0.98
        except BankingClientError as exc:
            logger.warning("Could not fetch balance for %s: %s", user_id, exc)
            response = "I couldn’t fetch your live balance right now. Please try again in a moment."
            confidence = 0.6

        return AgentOutput(
            response=response,
            agent_name=self.name,
            confidence=confidence,
            metadata={"intent_handled": "balance_check", "is_nudge": False},
        )

    def _handle_affordability_question(
        self, user_id: str, amount: float
    ) -> AgentOutput:
        try:
            balance = get_balance_sync(user_id)
            available_balance = float(balance.get("available_balance", 0.0))
            post_purchase_balance = available_balance - amount
            if post_purchase_balance >= 10000:
                verdict = "Yes — this looks affordable right now"
            elif post_purchase_balance >= 0:
                verdict = "You can buy it, but it will leave a tight buffer"
            else:
                verdict = "Not recommended right now"

            response = (
                f"{verdict}. Purchase amount: ₹{amount:,.0f}, available balance: ₹{available_balance:,.0f}, "
                f"remaining after purchase: ₹{post_purchase_balance:,.0f}. "
                "If you want, I can suggest a safer target budget."
            )
            confidence = 0.97
        except BankingClientError as exc:
            logger.warning(
                "Could not fetch affordability data for %s: %s", user_id, exc
            )
            response = (
                f"I couldn’t fetch your live balance to evaluate ₹{amount:,.0f} right now. "
                "Please retry in a moment."
            )
            confidence = 0.6

        return AgentOutput(
            response=response,
            agent_name=self.name,
            confidence=confidence,
            metadata={
                "intent_handled": "affordability_check",
                "purchase_amount": amount,
                "is_nudge": False,
            },
        )
