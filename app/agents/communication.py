from app.agents.base import BaseAgent, AgentInput, AgentOutput


class CommunicationAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "CommunicationAgent"

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        return AgentOutput(
            response=(
                f"I understand you're asking about: \"{agent_input.message}\". "
                "I'm here to help with your financial wellness. You can ask me about "
                "your health score, simulate what-if scenarios, explore savings options, "
                "or check product recommendations."
            ),
            agent_name=self.name,
            confidence=0.7,
            metadata={"fallback": True},
        )
