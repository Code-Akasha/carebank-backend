from app.agents.base import BaseAgent, AgentInput, AgentOutput


class AutoSavingsAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "AutoSavingsAgent"

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        return AgentOutput(
            response=(
                "Good news! Based on your forecast, you can safely save ₹300 this week "
                "without affecting your upcoming bills. This would bring your savings "
                "goal progress to 68%. Would you like to approve this micro-transfer?"
            ),
            agent_name=self.name,
            confidence=0.9,
            metadata={"suggested_amount": 300, "goal_progress": 0.68},
        )
