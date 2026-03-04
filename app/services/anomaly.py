from __future__ import annotations

import math
import statistics

import numpy as np


def detect_anomaly(amount: float, history: list[float]) -> dict:
    """
    Detect if a transaction amount is anomalous relative to history.

    Args:
        amount: current transaction amount (absolute value)
        history: list of historical transaction amounts (absolute values)

    Returns:
        dict with is_anomaly, anomaly_score, severity
    """
    sanitized_history = [
        abs(float(value)) for value in history if math.isfinite(float(value))
    ]
    if len(sanitized_history) < 5:
        return {"is_anomaly": False, "anomaly_score": 0.0, "severity": "low"}

    baseline = float(abs(amount))
    median = float(statistics.median(sanitized_history))
    q1 = float(np.percentile(sanitized_history, 25))
    q3 = float(np.percentile(sanitized_history, 75))
    iqr = max(q3 - q1, 1e-6)

    mad_raw = [abs(value - median) for value in sanitized_history]
    mad = max(float(statistics.median(mad_raw)), 1e-6)
    robust_z = abs(baseline - median) / (1.4826 * mad)

    lower_bound = q1 - 3.0 * iqr
    upper_bound = q3 + 3.0 * iqr
    out_of_iqr_range = baseline < lower_bound or baseline > upper_bound
    is_anomaly = bool(robust_z >= 3.5 or out_of_iqr_range)

    score = 1.0 - min(robust_z / 10.0, 1.0)

    if robust_z >= 6.0:
        severity = "high"
    elif robust_z >= 3.5:
        severity = "medium"
    else:
        severity = "low"

    return {
        "is_anomaly": is_anomaly,
        "anomaly_score": round(score, 4),
        "severity": severity,
    }
