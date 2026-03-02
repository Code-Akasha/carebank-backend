from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as redis

from app.agents.base import AgentInput
from app.agents.communication import CommunicationAgent
from app.core.database import SessionLocal
from app.models.transaction import Transaction
from app.services.anomaly import detect_anomaly
from app.services.health_score import compute_health_score
from app.services.banking_client import get_banking_client

logger = logging.getLogger(__name__)
HEALTH_SCORE_CACHE_TTL = 300
HEALTH_SCORE_KEY = "carebank:health_score:{user_id}"


def _recent_history(user_id: str, limit: int = 50) -> list[float]:
    with SessionLocal() as db:
        amounts = (
            db.query(Transaction.amount)
            .filter(Transaction.user_id == user_id)
            .order_by(Transaction.date.desc())
            .limit(limit)
            .all()
        )
    return [abs(row[0]) for row in amounts if row and row[0] is not None]


async def handle_transaction_event(
    transaction: dict[str, Any], redis_client: redis.Redis | None = None
) -> None:
    user_id = transaction.get("user_id")
    if not user_id:
        logger.warning("Received transaction without user_id: %s", transaction)
        return

    history = _recent_history(user_id)
    anomaly = detect_anomaly(abs(transaction.get("amount", 0.0)), history)

    client = get_banking_client()
    transactions = await client.get_transactions(user_id)
    balance = await client.get_balance(user_id)

    score_result = compute_health_score(
        user_id,
        transactions=transactions,
        current_balance=balance.get("current_balance", 0.0),
    )

    previous_score = await _get_cached_score(redis_client, user_id)
    await _cache_health_score(redis_client, user_id, score_result)
    score_dropped = (
        previous_score is not None and score_result["score"] <= previous_score - 5
    )

    if anomaly["is_anomaly"] or score_dropped:
        await _send_nudge(user_id, transaction, anomaly, score_result)


async def _cache_health_score(
    redis_client: redis.Redis | None, user_id: str, score_result: dict
) -> None:
    if not redis_client:
        return
    key = HEALTH_SCORE_KEY.format(user_id=user_id)
    await redis_client.set(
        key,
        json.dumps({"score": score_result.get("score", 0)}),
        ex=HEALTH_SCORE_CACHE_TTL,
    )


async def _get_cached_score(
    redis_client: redis.Redis | None, user_id: str
) -> float | None:
    if not redis_client:
        return None
    key = HEALTH_SCORE_KEY.format(user_id=user_id)
    cached = await redis_client.get(key)
    if not cached:
        return None
    try:
        payload = json.loads(cached)
    except json.JSONDecodeError:
        return None
    return payload.get("score")


async def _send_nudge(
    user_id: str, transaction: dict[str, Any], anomaly: dict, score_result: dict
) -> None:
    agent = CommunicationAgent()
    context = {
        "is_nudge": True,
        "data": {
            "transaction": transaction,
            "anomaly": anomaly,
            "health_score": score_result,
        },
        "task": "Notify the user about an important account event in 2 sentences.",
    }
    agent_input = AgentInput(
        user_id=user_id,
        message="system_nudge",
        intent="opportunity" if not anomaly.get("is_anomaly") else "anomaly_check",
        context=context,
    )
    await asyncio.to_thread(agent.invoke, agent_input)
