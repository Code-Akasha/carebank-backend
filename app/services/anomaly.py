from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest


def detect_anomaly(amount: float, history: list[float]) -> dict:
    """
    Detect if a transaction amount is anomalous relative to history.

    Args:
        amount: current transaction amount (absolute value)
        history: list of historical transaction amounts (absolute values)

    Returns:
        dict with is_anomaly, anomaly_score, severity
    """
    if len(history) < 5:
        return {"is_anomaly": False, "anomaly_score": 0.0, "severity": "low"}

    model = IsolationForest(contamination=0.1, random_state=42)
    history_array = np.array(history).reshape(-1, 1)
    model.fit(history_array)

    score = float(model.decision_function(np.array([[amount]]))[0])
    is_anomaly = bool(model.predict(np.array([[amount]]))[0] == -1)

    if score < -0.3:
        severity = "high"
    elif score < -0.1:
        severity = "medium"
    else:
        severity = "low"

    return {
        "is_anomaly": is_anomaly,
        "anomaly_score": round(score, 4),
        "severity": severity,
    }
