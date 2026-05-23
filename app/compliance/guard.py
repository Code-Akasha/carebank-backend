from __future__ import annotations

import logging
import re
from typing import Any

from app.core.database import SessionLocal
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

# Basic blacklist for MVP.
BLACKLIST_TERMS = [
    "guarantee",
    "promise",
    "risk-free",
    "100% safe",
    "investment advice",
]

DISCLAIMER = "\n\n*Disclaimer: CareBank insights are for informational purposes and do not constitute formal financial advice.*"


def validate_and_refine(
    response: str,
    intent: str,
    original_data: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Compliance Guard validation pipeline.
    1. Blacklist check
    2. Number verification (if original data provided)
    3. Disclaimer injection

    Returns:
        tuple of (refined_response, compliance_metadata)

    """
    metadata: dict[str, Any] = {
        "blacklist_flagged": False,
        "numbers_verified": True,
        "disclaimer_added": False,
    }

    refined_response = response

    # 1. Blacklist Check
    lower_resp = refined_response.lower()
    for term in BLACKLIST_TERMS:
        if term in lower_resp:
            metadata["blacklist_flagged"] = True
            logger.warning(f"Compliance flag: Blacklisted term '{term}' found.")
            # Redact or replace
            refined_response = re.sub(f"(?i){term}", "[REDACTED]", refined_response)

    # 2. Number Verification (Heuristic for MVP)
    # If the LLM generates a number not in the original data context, flag an alert
    if original_data:
        # Extract all numbers from response
        resp_numbers = [
            float(n.replace(",", ""))
            for n in set(re.findall(r"\d+(?:,\d+)*(?:\.\d+)?", refined_response))
        ]

        # Flatten original data to string and extract numbers
        data_str = str(original_data)
        data_numbers = [
            float(n.replace(",", ""))
            for n in set(re.findall(r"\d+(?:,\d+)*(?:\.\d+)?", data_str))
        ]

        # Check if any major number in response (> 100) is NOT in original data
        for num in resp_numbers:
            if num > 100 and num not in data_numbers:
                # Flag hallucination (allow a small float tolerance)
                # (In a real system, we'd do fuzzy matching or use LLM-as-a-judge)
                metadata["numbers_verified"] = False
                logger.warning(f"Compliance flag: Possible number hallucination: {num}")
                break

    # 3. Disclaimer Injection
    # Always append disclaimer if it's related to forecasting or what-if
    if intent in ["health_score", "what_if", "auto_savings"]:
        if "Disclaimer" not in refined_response:
            refined_response += DISCLAIMER
            metadata["disclaimer_added"] = True

    return refined_response, metadata


def log_compliance_decision(
    user_id: str,
    intent: str,
    original_response: str,
    final_response: str,
    metadata: dict[str, Any],
) -> None:
    """Logs the compliance check to the database."""
    # We can reuse the AuditLog table or print to console for MVP
    try:
        with SessionLocal() as db:
            log_entry = AuditLog(
                user_id=user_id,
                user_message="[COMPLIANCE CHECK]",
                intent=intent,
                agent_used="ComplianceGuard",
                agent_response=f"Flags: Blacklist={metadata['blacklist_flagged']}, Verified={metadata['numbers_verified']}, Disclaimer={metadata['disclaimer_added']}",
            )
            db.add(log_entry)
            db.commit()
    except Exception as e:
        logger.error(f"Failed to write compliance log: {e}")
