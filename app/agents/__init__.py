from __future__ import annotations

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.agents.intelligence import IntelligenceAgent
from app.agents.communication import CommunicationAgent
from app.agents.opportunity import OpportunityAgent
from app.agents.auto_savings import AutoSavingsAgent

__all__ = [
    "BaseAgent",
    "AgentInput",
    "AgentOutput",
    "IntelligenceAgent",
    "CommunicationAgent",
    "OpportunityAgent",
    "AutoSavingsAgent",
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
