from app.agents.base import BaseAgent, AgentInput, AgentOutput


class OpportunityAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "OpportunityAgent"

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        return AgentOutput(
            response=(
                "Based on your profile, you're eligible for our Premium Savings Account "
                "with 7.5% interest. You also have an unused streaming subscription "
                "(₹499/month) that could be redirected to savings. Would you like to "
                "explore these options?"
            ),
            agent_name=self.name,
            confidence=0.8,
            metadata={"products_found": 1, "subscriptions_flagged": 1},
        )
