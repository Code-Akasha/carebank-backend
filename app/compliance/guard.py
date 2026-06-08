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
    """Compliance Guard validation pipeline using LLM.
    1. Blacklist check and rewrite
    2. Number verification and rewrite
    3. Disclaimer injection
    """
    from langchain_core.prompts import PromptTemplate
    from app.services.llm import get_llm_provider

    metadata: dict[str, Any] = {
        "blacklist_flagged": False,
        "numbers_verified": True,
        "disclaimer_added": False,
    }

    refined_response = response

    # 1. Blacklist Check via LLM
    lower_resp = refined_response.lower()
    flagged_terms = [term for term in BLACKLIST_TERMS if term in lower_resp]
    if flagged_terms:
        metadata["blacklist_flagged"] = True
        logger.warning(f"Compliance flag: Blacklisted terms {flagged_terms} found.")
        try:
            llm, provider = get_llm_provider(temperature=0.2)
            prompt = PromptTemplate.from_template(
                "You are a compliance guard for a bank.\n"
                "The following response contains disallowed concepts: {terms}.\n"
                "Rewrite the response to safely mask these concepts and remove guarantees or advice. Keep the friendly tone.\n"
                "Original Response: {response}\n\n"
                "Rewritten Response:"
            )
            chain = prompt | llm
            rewritten = chain.invoke(
                {"terms": ", ".join(flagged_terms), "response": refined_response}
            )
            refined_response = rewritten.content.strip()
        except Exception as e:
            logger.error(f"LLM rewrite failed: {e}")
            for term in flagged_terms:
                refined_response = re.sub(f"(?i){term}", "[REDACTED]", refined_response)

    # 2. Number Verification via LLM
    if original_data:
        try:
            llm, provider = get_llm_provider(temperature=0.0)
            prompt = PromptTemplate.from_template(
                "You are a compliance guard. Verify if all financial numbers in the 'Response' are accurately based on the 'Original Data'.\n"
                "If the LLM hallucinated numbers not present in the data, rewrite the response to correct or remove them.\n"
                "If the numbers are correct, output the response exactly as is.\n\n"
                "Original Data: {data}\n\n"
                "Response: {response}\n\n"
                "Verified Response:"
            )
            chain = prompt | llm
            verified = chain.invoke(
                {"data": str(original_data), "response": refined_response}
            )
            if verified.content.strip():
                refined_response = verified.content.strip()
        except Exception as e:
            logger.error(f"LLM number verification failed: {e}")

    # 3. Disclaimer Injection
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
