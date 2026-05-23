from app.agents.base import (
    AgentContext,
    AgentInput,
    AgentOutput,
    AgentStatus,
    BaseAgent,
)


class DummyAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "DummyAgent"

    @property
    def description(self) -> str:
        return "Test description"

    @property
    def capabilities(self) -> list[str]:
        return ["test"]

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        return AgentOutput(
            agent_name=self.name,
            response="Done",
            status=AgentStatus.success,
        )


def test_agent_status_enum():
    assert AgentStatus.success == "success"
    assert AgentStatus.error == "error"
    assert AgentStatus.needs_input == "needs_input"


def test_agent_context_validation():
    # Test valid fields
    ctx = AgentContext(persona="Teacher", expense_amount=50.0)
    assert ctx.persona == "Teacher"
    assert ctx.expense_amount == 50.0

    # Test unknown fields (extra kwargs allowed)
    ctx = AgentContext(unknown_field="value")
    assert getattr(ctx, "unknown_field", None) is None
    assert ctx.model_extra == {"unknown_field": "value"}


def test_agent_input_coercion():
    # Provide dict
    inp = AgentInput(user_id="u1", message="hello", context={"persona": "Doctor"})
    assert isinstance(inp.context, AgentContext)
    assert inp.context.persona == "Doctor"


def test_invoke_latency_tracking():
    agent = DummyAgent()
    inp = AgentInput(user_id="u1", message="hi")
    out = agent.invoke(inp)

    assert out.status == AgentStatus.success
    assert out.latency_ms is not None
    assert out.latency_ms > 0
