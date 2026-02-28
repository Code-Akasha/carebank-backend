from app.agents.base import BaseAgent, AgentInput, AgentOutput


class IntelligenceAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "IntelligenceAgent"

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        intent = agent_input.intent

        if intent == "what_if":
            response = (
                "Based on your current spending patterns, this expense would reduce "
                "your end-of-month balance by approximately ₹2,300. Your Financial "
                "Health Score would drop from 72 to 65. Consider spreading this "
                "expense over 2-3 months."
            )
        else:
            response = (
                "Your Financial Health Score is 72/100. Savings ratio is strong at 18%, "
                "but dining expenses increased 15% this week. Your forecast shows a "
                "comfortable end-of-month balance of ₹12,400."
            )

        return AgentOutput(
            response=response,
            agent_name=self.name,
            confidence=0.85,
            metadata={"intent_handled": intent},
        )
