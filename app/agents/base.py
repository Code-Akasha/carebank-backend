import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class AgentStatus(str, Enum):
    """Typed status for agent outputs."""

    success = "success"
    error = "error"
    needs_input = "needs_input"


class AgentContext(BaseModel):
    """Typed context passed between agents. Replaces loose dict."""

    model_config = {"extra": "allow"}

    history: list[dict[str, Any]] = Field(default_factory=list)
    persona: str | None = None
    expense_amount: float | None = None
    purchase_amount: float | None = None
    amount: float | None = None
    is_nudge: bool = False
    agent_results: list[dict[str, Any]] = Field(default_factory=list)
    data: str | None = None
    task: str | None = None


class AgentInput(BaseModel):
    user_id: str
    message: str
    intent: str = ""
    context: AgentContext = Field(default_factory=AgentContext)

    @model_validator(mode="before")
    @classmethod
    def _coerce_context(cls, values: dict[str, Any]) -> dict[str, Any]:
        context = values.get("context")
        if context is None:
            values["context"] = AgentContext()
            return values
        if isinstance(context, AgentContext):
            return values
        if isinstance(context, BaseModel):
            values["context"] = AgentContext(**context.model_dump())
        elif isinstance(context, dict):
            values["context"] = AgentContext(**context)
        else:
            raise TypeError("context must be AgentContext or dict-compatible")
        return values


class AgentOutput(BaseModel):
    response: str = ""
    agent_name: str
    confidence: float = 1.0
    metadata: dict = Field(default_factory=dict)
    status: AgentStatus = AgentStatus.success
    required_params: list[str] = Field(default_factory=list)
    latency_ms: float | None = None
    tokens_used: int | None = None


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
        start = time.perf_counter()
        try:
            output = self._invoke(agent_input)
            output.latency_ms = (time.perf_counter() - start) * 1000
            return output
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return AgentOutput(
                response="I'm sorry, I encountered an issue processing your request. Please try again.",
                agent_name=self.name,
                confidence=0.0,
                metadata={"error": str(exc)},
                latency_ms=elapsed,
            )
