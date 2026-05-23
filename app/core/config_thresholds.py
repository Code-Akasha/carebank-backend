from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings


@dataclass(frozen=True)
class RiskThresholds:
    """Container for risk thresholds used across intelligence flows."""

    what_if_low: float
    what_if_medium: float
    affordability_safe_buffer: float


@lru_cache
def get_risk_thresholds() -> RiskThresholds:
    """Load thresholds from settings once and reuse."""
    settings = get_settings()
    return RiskThresholds(
        what_if_low=settings.whatif_low_threshold,
        what_if_medium=settings.whatif_medium_threshold,
        affordability_safe_buffer=settings.affordability_safe_buffer,
    )
