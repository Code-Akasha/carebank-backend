from __future__ import annotations

from typing import Any, Protocol


class ConversationStore(Protocol):
    """Interface for conversation memory backends."""

    def get(self, user_id: str) -> list[dict]: ...

    def add(self, user_id: str, role: str, content: str) -> None: ...

    def clear(self, user_id: str) -> None: ...

    def get_state(self, user_id: str) -> dict[str, Any]: ...

    def set_state(self, user_id: str, state: dict[str, Any]) -> None: ...

    def clear_state(self, user_id: str) -> None: ...


class InMemoryConversationStore:
    """In-memory conversation store (MVP). Swap to Redis by implementing ConversationStore."""

    def __init__(self, max_history: int = 10):
        self._store: dict[str, list[dict]] = {}
        self._state: dict[str, dict[str, Any]] = {}
        self._max_history = max_history

    def get(self, user_id: str) -> list[dict]:
        return list(self._store.get(user_id, []))

    def add(self, user_id: str, role: str, content: str) -> None:
        history = self._store.setdefault(user_id, [])
        history.append({"role": role, "content": content})
        if len(history) > self._max_history:
            self._store[user_id] = history[-self._max_history :]

    def clear(self, user_id: str) -> None:
        self._store.pop(user_id, None)
        self._state.pop(user_id, None)

    def get_state(self, user_id: str) -> dict[str, Any]:
        return dict(self._state.get(user_id, {}))

    def set_state(self, user_id: str, state: dict[str, Any]) -> None:
        self._state[user_id] = dict(state)

    def clear_state(self, user_id: str) -> None:
        self._state.pop(user_id, None)
