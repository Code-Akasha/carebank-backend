from __future__ import annotations

import logging

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.services.nlg import generate_response
from app.services.nudge import can_send_nudge, record_nudge
from app.services.health_score import compute_health_score

logger = logging.getLogger(__name__)


class CommunicationAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "CommunicationAgent"

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        user_id = agent_input.user_id
        message = agent_input.message
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

        # 2. Get Persona (from Intelligence Agent's health score dataset)
        try:
            health_data = compute_health_score(user_id)
            persona = health_data.get("persona", {}).get("persona", "Balanced Manager")
        except Exception as e:
            logger.warning(f"Could not fetch persona for {user_id}: {e}")
            persona = "Balanced Manager"

        # 3. Formulate Data Context
        # Default behavior: generic financial query response formatting
        data_context = context.get("data", f"Financial inquiry: {message}")
        task_description = context.get(
            "task", "Provide a helpful, personalized response summarizing the data."
        )

        # 4. Generate NLG Response
        nlg_result = generate_response(
            persona=persona,
            data_context=data_context,
            task_description=task_description,
        )

        # 5. Record nudge if it was sent successfully
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
