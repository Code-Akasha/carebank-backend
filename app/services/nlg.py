from __future__ import annotations

import logging
from typing import Any

from langchain_core.prompts import PromptTemplate

from app.services.llm import get_llm_provider

logger = logging.getLogger(__name__)

# Basic persona definitions for tone
PERSONA_PROMPT_MAP = {
    "Cautious Saver": "You are a supportive and reassuring financial assistant. You encourage steady growth and safe financial choices.",
    "Balanced Manager": "You are a practical and straightforward financial assistant. You provide clear, actionable advice.",
    "Social Spender": "You are an energetic and engaging financial assistant. You focus on maximizing enjoyment while staying within budget.",
    "Impulse Buyer": "You are a gentle but firm financial coach. You emphasize taking a moment to pause before spending.",
}

DEFAULT_PERSONA = PERSONA_PROMPT_MAP["Balanced Manager"]

BASE_PROMPT = """You are a helpful financial assistant for CareBank.

IMPORTANT RULES:
1. NEVER make up or hallucinate specific financial numbers (balances, amounts, dates, transaction values)
2. If you don't have specific data, say so clearly and suggest the user ask for specific information
3. Keep responses concise (maximum 3 sentences)
4. Do NOT add financial disclaimers (the system adds them automatically)

Context: {data_context}
Task: {task_description}

Provide a helpful response that follows the rules above:
"""


def generate_response(
    persona: str,
    data_context: str,
    task_description: str,
) -> dict[str, Any]:
    """
    Generates a natural language response using the configured LLM.
    Uses a template fallback if LLM is unavailable or fails.

    Returns:
        dict with text, provider, and persona used
    """
    llm, provider = get_llm_provider(
        temperature=0.5
    )  # Lower temperature to reduce hallucination

    if not llm:
        return _template_fallback(persona, data_context, task_description)

    prompt = PromptTemplate.from_template(BASE_PROMPT)
    chain = prompt | llm

    try:
        response = chain.invoke(
            {
                "data_context": data_context,
                "task_description": task_description,
            }
        )
        return {
            "text": response.content.strip(),
            "provider": provider,
            "persona": persona,
        }
    except Exception as e:
        logger.error(f"LLM Generation failed: {e}. Using fallback.")
        return _template_fallback(persona, data_context, task_description)


def _template_fallback(
    persona: str, data_context: str, task_description: str
) -> dict[str, Any]:
    """Fallback generator when LLMs fail or are misconfigured. Avoids hallucinating data."""
    common_tail = (
        "I avoid making assumptions about your financial data to ensure accuracy. "
        "Please ask me directly about your balance, transactions, or forecast for exact numbers."
    )

    if persona == "Cautious Saver":
        text = (
            f"Let's prioritize stability while addressing your {data_context}. "
            f"Suggested focus: {task_description}. "
            f"{common_tail}"
        )
    elif persona == "Social Spender":
        text = (
            f"Let's work on your {data_context} in a way that fits your budget. "
            f"Suggested focus: {task_description}. "
            f"{common_tail}"
        )
    else:
        text = (
            f"I can help with that regarding your {data_context}. "
            f"Suggested focus: {task_description}. "
            f"{common_tail}"
        )

    return {
        "text": text,
        "provider": "template_fallback",
        "persona": persona,
    }
