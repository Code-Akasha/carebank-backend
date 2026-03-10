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
