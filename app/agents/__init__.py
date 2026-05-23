from __future__ import annotations

from app.agents.auto_savings import AutoSavingsAgent
from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.communication import CommunicationAgent
from app.agents.intelligence import IntelligenceAgent
from app.agents.opportunity import OpportunityAgent

__all__ = [
    "AgentInput",
    "AgentOutput",
    "AutoSavingsAgent",
    "BaseAgent",
    "CommunicationAgent",
    "IntelligenceAgent",
    "OpportunityAgent",
    "build_coordinator_graph",
    "coordinator_graph",
]


def __getattr__(name: str):
    if name in {"build_coordinator_graph", "coordinator_graph"}:
        from app.agents.coordinator import build_coordinator_graph, coordinator_graph

        exports = {
            "build_coordinator_graph": build_coordinator_graph,
            "coordinator_graph": coordinator_graph,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
