"""Redis-backed conversation store implementing ConversationStore protocol."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_PREFIX = "carebank:conv:"
_STATE_PREFIX = "carebank:conv_state:"
_TTL_SECONDS = 3600  # 1 hour


def _get_redis() -> redis.Redis:
    settings = get_settings()
    redis_url = getattr(settings, "redis_url", None) or "redis://localhost:6379"
    return redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
        health_check_interval=30,
    )


class RedisConversationStore:
    """Redis-backed conversation store with TTL-based expiry."""

    def __init__(self, max_history: int = 10):
        self._max_history = max_history
        self._redis: redis.Redis | None = None

    @property
    def _client(self) -> redis.Redis:
        if self._redis is None:
            self._redis = _get_redis()
        return self._redis

    def _conv_key(self, user_id: str) -> str:
        return f"{_PREFIX}{user_id}"

    def _state_key(self, user_id: str) -> str:
        return f"{_STATE_PREFIX}{user_id}"

    def get(self, user_id: str) -> list[dict]:
        try:
            raw = self._client.get(self._conv_key(user_id))
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.warning("Redis conversation get failed: %s", exc)
        return []

    def add(self, user_id: str, role: str, content: str) -> None:
        try:
            key = self._conv_key(user_id)
            history = self.get(user_id)
            history.append({"role": role, "content": content})
            if len(history) > self._max_history:
                history = history[-self._max_history :]
            self._client.set(key, json.dumps(history), ex=_TTL_SECONDS)
        except Exception as exc:
            logger.warning("Redis conversation add failed: %s", exc)

    def clear(self, user_id: str) -> None:
        try:
            self._client.delete(self._conv_key(user_id))
            self._client.delete(self._state_key(user_id))
        except Exception as exc:
            logger.warning("Redis conversation clear failed: %s", exc)

    def get_state(self, user_id: str) -> dict[str, Any]:
        try:
            raw = self._client.get(self._state_key(user_id))
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.warning("Redis state get failed: %s", exc)
        return {}

    def set_state(self, user_id: str, state: dict[str, Any]) -> None:
        try:
            self._client.set(
                self._state_key(user_id), json.dumps(state), ex=_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning("Redis state set failed: %s", exc)

    def clear_state(self, user_id: str) -> None:
        try:
            self._client.delete(self._state_key(user_id))
        except Exception as exc:
            logger.warning("Redis state clear failed: %s", exc)
