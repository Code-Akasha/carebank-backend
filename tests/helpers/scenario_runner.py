from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from app.agents.coordinator import (
    clear_conversation_state,
    coordinator_graph,
    get_conversation_history,
    get_conversation_state,
    set_conversation_state,
)


@dataclass
class ScenarioResult:
    intent: str
    response: str
    action: dict[str, Any] | None
    pending_state: dict[str, Any] | None


def run_scenario(
    message: str,
    user_id: str,
    mock_intent: str,
    *,
    amount: float | None = None,
    day_of_month: int | None = None,
    recurring: bool | None = None,
    inject_state: dict[str, Any] | None = None,
    clear_history: bool = True,
) -> ScenarioResult:
    """Run a single conversational turn with a deterministic mocked intent."""
    if clear_history:
        clear_conversation_state(user_id)

    if inject_state:
        set_conversation_state(user_id, inject_state)

    history = get_conversation_history(user_id)
    conversation_state = get_conversation_state(user_id)

    # We patch the classifier in the module so it forces deterministic classification
    from app.agents.coordinator import ClassificationResult

    mock_result = ClassificationResult(
        intent=mock_intent,
        confidence=1.0,
        amount=amount,
        day_of_month=day_of_month,
        recurring=recurring,
    )

    with patch(
        "app.agents.coordinator._classify_intent_with_llm", return_value=mock_result,
    ):
        # Run the graph
        result = coordinator_graph.invoke(
            {
                "user_id": user_id,
                "message": message,
                "audit_log": [],
                "conversation_history": history,
                "conversation_state": conversation_state,
                "db": None,
                "current_user": None,
            },
        )

    response_metadata = result.get("response_metadata") or {}

    # Simulate the router's state updating logic
    if result.get("pending_intent_ignored"):
        clear_conversation_state(user_id)
        conversation_state = {}

    if isinstance(response_metadata, dict):
        if response_metadata.get("clear_pending"):
            clear_conversation_state(user_id)
        else:
            pending_state = response_metadata.get("pending_state")
            if isinstance(pending_state, dict):
                next_state = {
                    **conversation_state,
                    **pending_state,
                }
                set_conversation_state(user_id, next_state)

    current_state = get_conversation_state(user_id)

    return ScenarioResult(
        intent=result.get("intent", mock_intent),
        response=result.get("agent_response", ""),
        action=response_metadata.get("action"),
        pending_state=current_state or None,
    )
