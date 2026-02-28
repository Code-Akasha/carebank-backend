from __future__ import annotations

import numpy as np

PERSONAS = ["Cautious Saver", "Balanced Manager", "Social Spender", "Impulse Buyer"]

# Pre-computed centroids from mock data analysis
# Features: [food, transport, entertainment, shopping, bills, other]
_CENTROIDS = np.array([
    [0.15, 0.10, 0.10, 0.10, 0.50, 0.05],  # Cautious Saver — bills-heavy, low discretionary
    [0.25, 0.15, 0.15, 0.15, 0.25, 0.05],  # Balanced Manager — evenly spread
    [0.35, 0.10, 0.30, 0.10, 0.10, 0.05],  # Social Spender — food + entertainment heavy
    [0.20, 0.05, 0.15, 0.40, 0.10, 0.10],  # Impulse Buyer — shopping-heavy
])

_CATEGORY_ORDER = ["food", "transport", "entertainment", "shopping", "bills", "other"]


def cluster_persona(spending_profile: dict[str, float]) -> dict:
    """
    Assign a user persona based on spending category percentages.

    Args:
        spending_profile: {category: percentage} e.g. {"food": 0.35, "transport": 0.15, ...}

    Returns:
        dict with persona label, cluster_id, confidence, top_category
    """
    if not spending_profile:
        return {
            "persona": "Balanced Manager",
            "cluster_id": 1,
            "confidence": 0.5,
            "top_category": "unknown",
        }

    feature_vector = np.array([
        spending_profile.get(cat, 0.0) for cat in _CATEGORY_ORDER
    ]).reshape(1, -1)

    distances = np.linalg.norm(_CENTROIDS - feature_vector, axis=1)
    cluster_id = int(np.argmin(distances))
    min_dist = distances[cluster_id]

    # Confidence: inverse of distance, normalized
    max_possible_dist = np.sqrt(len(_CATEGORY_ORDER))
    confidence = round(max(0.0, 1.0 - (min_dist / max_possible_dist)), 2)

    top_category = max(spending_profile, key=spending_profile.get) if spending_profile else "unknown"

    return {
        "persona": PERSONAS[cluster_id],
        "cluster_id": cluster_id,
        "confidence": confidence,
        "top_category": top_category,
    }
