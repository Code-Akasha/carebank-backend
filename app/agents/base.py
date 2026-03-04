from abc import ABC, abstractmethod
from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    user_id: str
    message: str
    intent: str = ""
    context: dict = Field(default_factory=dict)


class AgentOutput(BaseModel):
    response: str
    agent_name: str
    confidence: float = 1.0
    metadata: dict = Field(default_factory=dict)


class BaseAgent(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this agent does."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> list[str]:
        """List of specific capabilities/intents this agent can handle."""
        ...

    @abstractmethod
    def _invoke(self, agent_input: AgentInput) -> AgentOutput: ...

    def invoke(self, agent_input: AgentInput) -> AgentOutput:
        try:
            return self._invoke(agent_input)
        except Exception as exc:
            return AgentOutput(
                response="I'm sorry, I encountered an issue processing your request. Please try again.",
                agent_name=self.name,
                confidence=0.0,
                metadata={"error": str(exc)},
            )
