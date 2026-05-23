"""Server-Sent Events endpoint for real-time transaction and notification events."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.security import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/events", tags=["events"])

# In-memory event queues for push_event API
_user_queues: dict[str, list[asyncio.Queue]] = {}


def push_event(user_id: str, event_type: str, data: dict) -> None:
    """Push an event to all connected SSE clients for a user (from sync code)."""
    payload = json.dumps({"type": event_type, **data})
    for queue in _user_queues.get(user_id, []):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass


async def _event_stream(user_id: str) -> AsyncGenerator[str, None]:
    """Merge Redis pub/sub + in-memory push events into a single SSE stream."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _user_queues.setdefault(user_id, []).append(queue)

    settings = get_settings()
    redis_client = None
    pubsub = None

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"carebank:transactions:{user_id}")
    except Exception as exc:
        logger.warning("SSE: Redis not available, using push-only mode: %s", exc)
        pubsub = None

    try:
        # Initial connection event
        yield f"data: {json.dumps({'type': 'connected', 'user_id': user_id})}\n\n"

        while True:
            # Check in-memory queue (non-blocking)
            try:
                payload = queue.get_nowait()
                yield f"data: {payload}\n\n"
                continue
            except asyncio.QueueEmpty:
                pass

            # Check Redis pub/sub
            if pubsub:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0,
                    )
                    if message and message.get("type") == "message":
                        raw = message.get("data")
                        data = raw if isinstance(raw, str) else json.dumps(raw)
                        yield f"data: {data}\n\n"
                        continue
                except Exception:
                    pass

            # No events — send keepalive
            yield ": keepalive\n\n"
            await asyncio.sleep(5.0)

    except asyncio.CancelledError:
        pass
    finally:
        queues = _user_queues.get(user_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues:
            _user_queues.pop(user_id, None)
        if pubsub:
            try:
                await pubsub.unsubscribe()
                await pubsub.close()
            except Exception:
                pass
        if redis_client:
            try:
                await redis_client.close()
            except Exception:
                pass


@router.get("/stream")
async def stream_events(
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    """SSE endpoint for real-time events (transactions, notifications, agent updates)."""
    return StreamingResponse(
        _event_stream(current_user.user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
