from __future__ import annotations

import json
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

You will receive structured data from analysis agents as JSON.
Translate this data into a clear, empathetic response adapted to the user's persona.

IMPORTANT RULES:
1. NEVER make up or hallucinate specific financial numbers
2. ONLY use numbers that appear in the provided data context
3. Keep responses concise (2-3 sentences max)
4. Do NOT add financial disclaimers (the system adds them automatically)
5. Match the tone to the user's persona

Persona: {persona}
Data (JSON): {data_context}
Task: {task_description}

Provide a helpful, persona-adapted response:
"""


def generate_response(
    persona: str,
    data_context: Any,
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
        serialized = _serialize_data_context(data_context)
        return _template_fallback(persona, serialized, task_description)

    prompt = PromptTemplate.from_template(BASE_PROMPT)
    chain = prompt | llm

    try:
        serialized_context = _serialize_data_context(data_context)
        response = chain.invoke(
            {
                "persona": persona,
                "data_context": serialized_context,
                "task_description": task_description,
            }
        )
        model_name, tokens_used = _extract_generation_metadata(provider, response)
        return {
            "text": response.content.strip(),
            "provider": provider,
            "persona": persona,
            "model": model_name,
            "tokens": tokens_used,
        }
    except Exception as e:
        logger.error(f"LLM Generation failed: {e}. Using fallback.")
        serialized = _serialize_data_context(data_context)
        return _template_fallback(persona, serialized, task_description)


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
        "model": "template_fallback",
        "tokens": None,
    }


def _serialize_data_context(data_context: Any) -> str:
    """Serialize arbitrary data into JSON for the prompt."""
    try:
        return json.dumps(data_context, default=str)
    except Exception as exc:
        logger.warning("Data context serialization failed: %s", exc)
        return str(data_context)


def _extract_generation_metadata(
    provider: str, response: Any
) -> tuple[str | None, int | None]:
    """Extract model name and total tokens from the LLM response metadata."""
    metadata = getattr(response, "response_metadata", None)

    model_name: str | None = None
    tokens_used: int | None = None

    if isinstance(metadata, dict):
        model_name = metadata.get("model") or metadata.get("model_name")

        for candidate in (
            metadata.get("token_usage"),
            metadata.get("usage"),
            metadata.get("usage_metadata"),
            metadata,
        ):
            tokens_used = _coerce_token_usage(candidate)
            if tokens_used is not None:
                break

    if not model_name and ":" in provider:
        model_name = provider.split(":", 1)[1]
    if not model_name:
        model_name = provider

    return model_name, tokens_used


def _coerce_token_usage(source: Any) -> int | None:
    if isinstance(source, dict):
        for key in ("total_tokens", "token_count_total", "tokens", "token_count"):
            value = source.get(key)
            if isinstance(value, (int, float)):
                return int(value)
        in_tokens = source.get("input_tokens")
        out_tokens = source.get("output_tokens")
        if isinstance(in_tokens, (int, float)) or isinstance(out_tokens, (int, float)):
            total = 0
            if isinstance(in_tokens, (int, float)):
                total += int(in_tokens)
            if isinstance(out_tokens, (int, float)):
                total += int(out_tokens)
            if total > 0:
                return total
    elif isinstance(source, (int, float)):
        return int(source)
    return None
