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
    "Impulse Buyer": "You are a gentle but firm financial coach. You emphasize taking a moment to pause before spending."
}

DEFAULT_PERSONA = PERSONA_PROMPT_MAP["Balanced Manager"]

BASE_PROMPT = """{persona_instruction}

Context:
You are generating a response for a user regarding their finances.
Data point: {data_context}
Task: {task_description}

Please write a concise, helpful, and personalized response (maximum 3 sentences). Do NOT include any financial disclaimers, the system will add them if needed.

Response:"""


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
    persona_instruction = PERSONA_PROMPT_MAP.get(persona, DEFAULT_PERSONA)
    llm, provider = get_llm_provider(temperature=0.7)

    if not llm:
        return _template_fallback(persona, data_context, task_description)

    prompt = PromptTemplate.from_template(BASE_PROMPT)
    chain = prompt | llm

    try:
        response = chain.invoke({
            "persona_instruction": persona_instruction,
            "data_context": data_context,
            "task_description": task_description,
        })
        return {
            "text": response.content.strip(),
            "provider": provider,
            "persona": persona,
        }
    except Exception as e:
        logger.error(f"LLM Generation failed: {e}. Using fallback.")
        return _template_fallback(persona, data_context, task_description)


def _template_fallback(persona: str, data_context: str, task_description: str) -> dict[str, Any]:
    """Fallback generator when LLMs fail or are misconfigured."""
    text = f"Based on {data_context}, we suggest looking into your options. We currently cannot generate a fully personalized message. "
    
    if "Cautious" in persona:
        text = f"Your safety is priority. {data_context} indicates you should stay the course. "
    elif "Social" in persona:
        text = f"Looks like fun! Just a heads up regarding {data_context}. Enjoy responsibly! "

    text += f"(Action: {task_description})"

    return {
        "text": text,
        "provider": "template_fallback",
        "persona": persona,
    }
