from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

import redis.asyncio as redis
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.config import get_settings

router = APIRouter(prefix="/api/events", tags=["events"])


async def _event_stream() -> AsyncGenerator[str, None]:
    settings = get_settings()
    client = redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe("carebank:transactions")
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
        await pubsub.unsubscribe("carebank:transactions")
        await pubsub.close()
        await client.close()


@router.get("/stream")
async def stream_events() -> StreamingResponse:
    return StreamingResponse(_event_stream(), media_type="text/event-stream")
