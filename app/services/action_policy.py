from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Lock

from app.services.banking_client import BankingClientError, get_action_policy_sync

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActionPolicy:
    requires_approval: bool
    max_amount: float | None
    allow_trusted_recurring_bypass: bool = True


_FALLBACK_POLICY_MATRIX: dict[str, ActionPolicy] = {
    "record_note": ActionPolicy(requires_approval=False, max_amount=None),
    "pay_rent": ActionPolicy(requires_approval=True, max_amount=150000.0),
    "pay_bill": ActionPolicy(requires_approval=True, max_amount=50000.0),
    "pay_gas": ActionPolicy(requires_approval=True, max_amount=10000.0),
    "pay_utility": ActionPolicy(requires_approval=True, max_amount=50000.0),
    "transfer_savings": ActionPolicy(requires_approval=True, max_amount=25000.0),
}

_POLICY_CACHE_TTL_SECONDS = 300.0
_policy_cache: dict[str, tuple[float, dict]] = {}
_policy_cache_lock = Lock()


def _get_cached_policy_payload(action_type: str) -> dict | None:
    now = time.monotonic()
    with _policy_cache_lock:
        entry = _policy_cache.get(action_type)
        if not entry:
            return None
        expires_at, payload = entry
        if expires_at < now:
            _policy_cache.pop(action_type, None)
            return None
    return payload


def _set_cached_policy_payload(action_type: str, payload: dict) -> None:
    with _policy_cache_lock:
        _policy_cache[action_type] = (
            time.monotonic() + _POLICY_CACHE_TTL_SECONDS,
            payload,
        )


def _coerce_policy(action_type: str, payload: dict) -> tuple[ActionPolicy, dict]:
    if not isinstance(payload, dict):
        raise ValueError("Invalid policy payload")

    payload_action_type = payload.get("action_type")
    if payload_action_type and payload_action_type != action_type:
        raise ValueError("Policy payload action_type mismatch")

    max_amount_raw = payload.get("max_amount")
    max_amount = None
    if max_amount_raw is not None:
        max_amount = float(max_amount_raw)
        if max_amount <= 0:
            raise ValueError("max_amount must be positive")

    policy = ActionPolicy(
        requires_approval=bool(payload.get("requires_approval", True)),
        max_amount=max_amount,
        allow_trusted_recurring_bypass=bool(
            payload.get("allow_trusted_recurring_bypass", True)
        ),
    )
    metadata = {
        "country": payload.get("country", "IN"),
        "policy_version": payload.get("policy_version"),
        "default_payment_rail": payload.get("default_payment_rail"),
        "regulatory_context": payload.get("regulatory_context") or [],
    }
    return policy, metadata


def _resolve_action_policy(action_type: str) -> tuple[ActionPolicy | None, dict]:
    cached_payload = _get_cached_policy_payload(action_type)
    if cached_payload is not None:
        try:
            policy, metadata = _coerce_policy(action_type, cached_payload)
            metadata["policy_source"] = "mockbank_cache"
            return policy, metadata
        except Exception:  # noqa: BLE001
            pass

    try:
        payload = get_action_policy_sync(action_type)
        _set_cached_policy_payload(action_type, payload)
        policy, metadata = _coerce_policy(action_type, payload)
        metadata["policy_source"] = "mockbank"
        return policy, metadata
    except BankingClientError as exc:
        fallback = _FALLBACK_POLICY_MATRIX.get(action_type)
        if exc.status_code == 404 and fallback is None:
            return None, {
                "policy_source": "mockbank",
                "country": "IN",
                "policy_error": f"Unsupported action_type: {action_type}",
            }
        logger.warning(
            "MockBank action policy lookup failed for %s (status=%s): %s",
            action_type,
            exc.status_code,
            exc,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Unexpected action policy resolution failure for %s: %s",
            action_type,
            exc,
        )

    fallback = _FALLBACK_POLICY_MATRIX.get(action_type)
    if fallback is None:
        return None, {
            "policy_source": "fallback",
            "country": "IN",
            "policy_error": f"Unsupported action_type: {action_type}",
        }
    return fallback, {
        "policy_source": "fallback",
        "country": "IN",
        "policy_version": None,
        "default_payment_rail": None,
        "regulatory_context": [],
    }


def supported_action_types() -> list[str]:
    return sorted(_FALLBACK_POLICY_MATRIX.keys())


def evaluate_action_policy(
    action_type: str,
    payload: dict,
    *,
    trusted_recurring: bool = False,
) -> dict:
    policy, metadata = _resolve_action_policy(action_type)
    if policy is None:
        return {
            "allowed": False,
            "requires_approval": True,
            "reason": metadata.get("policy_error")
            or f"Unsupported action_type: {action_type}",
            "max_amount": None,
            "policy_source": metadata.get("policy_source", "unknown"),
            "country": metadata.get("country", "IN"),
        }

    amount = payload.get("amount")
    if amount is not None:
        try:
            amount_value = float(amount)
        except (TypeError, ValueError):
            return {
                "allowed": False,
                "requires_approval": True,
                "reason": "Invalid amount format",
                "max_amount": policy.max_amount,
                "policy_source": metadata.get("policy_source", "unknown"),
                "country": metadata.get("country", "IN"),
            }
        if amount_value <= 0:
            return {
                "allowed": False,
                "requires_approval": True,
                "reason": "Amount must be positive",
                "max_amount": policy.max_amount,
                "policy_source": metadata.get("policy_source", "unknown"),
                "country": metadata.get("country", "IN"),
            }
        if policy.max_amount is not None and amount_value > policy.max_amount:
            return {
                "allowed": False,
                "requires_approval": True,
                "reason": f"Amount exceeds policy cap of {policy.max_amount}",
                "max_amount": policy.max_amount,
                "policy_source": metadata.get("policy_source", "unknown"),
                "country": metadata.get("country", "IN"),
            }

    requires_approval = policy.requires_approval
    if trusted_recurring and policy.allow_trusted_recurring_bypass:
        requires_approval = False

    return {
        "allowed": True,
        "requires_approval": requires_approval,
        "reason": "allowed",
        "max_amount": policy.max_amount,
        "policy_source": metadata.get("policy_source", "unknown"),
        "policy_version": metadata.get("policy_version"),
        "country": metadata.get("country", "IN"),
        "default_payment_rail": metadata.get("default_payment_rail"),
        "regulatory_context": metadata.get("regulatory_context", []),
        "allow_trusted_recurring_bypass": policy.allow_trusted_recurring_bypass,
        "trusted_recurring": trusted_recurring,
    }
