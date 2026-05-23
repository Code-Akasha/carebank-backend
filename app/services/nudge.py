from __future__ import annotations

from datetime import datetime, timedelta, timezone

# In-memory store for MVP. In Phase 5, this moves to Redis/Postgres.
# Format: { user_id: [datetime1, datetime2] }
_user_nudge_history: dict[str, list[datetime]] = {}

DAILY_LIMIT = 2
COOLDOWN_HOURS = 4


def can_send_nudge(user_id: str) -> tuple[bool, str]:
    """Checks if a nudge can be sent to the user based on fatigue rules.
    - Max DAILY_LIMIT nudges per 24 hours.
    - Minimum COOLDOWN_HOURS between nudges.

    Returns:
        (allowed: bool, reason: str)

    """
    now = datetime.now(timezone.utc)
    history = _user_nudge_history.get(user_id, [])

    # Clean up old history (> 24h)
    cutoff_24h = now - timedelta(hours=24)
    history = [t for t in history if t > cutoff_24h]
    _user_nudge_history[user_id] = history

    if not history:
        return True, "No recent nudges."

    # Check daily limit
    if len(history) >= DAILY_LIMIT:
        return False, f"Daily limit of {DAILY_LIMIT} nudges reached."

    # Check cooldown
    last_nudge = max(history)
    if now - last_nudge < timedelta(hours=COOLDOWN_HOURS):
        return False, f"In cooldown. Last nudge was at {last_nudge.strftime('%H:%M')}."

    return True, "Allowed."


def record_nudge(user_id: str) -> None:
    """Records that a nudge was successfully sent."""
    now = datetime.now(timezone.utc)
    if user_id not in _user_nudge_history:
        _user_nudge_history[user_id] = []
    _user_nudge_history[user_id].append(now)
