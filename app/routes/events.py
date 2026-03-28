from __future__ import annotations

import asyncio
import json
from typing import Annotated, AsyncGenerator

import redis.asyncio as redis
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/events", tags=["events"])


async def _event_stream(user_id: str) -> AsyncGenerator[str, None]:
    settings = get_settings()
    client = redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = client.pubsub()
    channel = f"carebank:transactions:{user_id}"
    await pubsub.subscribe(channel)
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=5.0
            )
            if message and message.get("type") == "message":
                payload = message.get("data")
                data = payload if isinstance(payload, str) else json.dumps(payload)
                yield f"data: {data}\n\n"
            await asyncio.sleep(0)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await client.close()


@router.get("/stream")
async def stream_events(
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(current_user.user_id),
        media_type="text/event-stream",
    )
