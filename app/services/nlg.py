from __future__ import annotations

import json
import logging
import re
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

_GREETING_QUERIES = {
    "hi",
    "hello",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "thanks",
    "thank you",
}

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
    """Generates a natural language response using the configured LLM.
    Uses a template fallback if LLM is unavailable or fails.

    Returns:
        dict with text, provider, and persona used

    """
    llm, provider = get_llm_provider(
        temperature=0.5,
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
            },
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
    persona: str,
    data_context: str,
    task_description: str,
) -> dict[str, Any]:
    """Fallback generator when LLMs fail or are misconfigured. Avoids hallucinating data."""
    structured = _structured_fallback_text(persona, data_context)
    if structured:
        return {
            "text": structured,
            "provider": "template_fallback",
            "persona": persona,
            "model": "template_fallback",
            "tokens": None,
        }

    payload = _parse_json_like_context(data_context)
    if isinstance(payload, list) and payload:
        # Find the first non-empty response from the end
        for item in reversed(payload):
            if isinstance(item, dict) and item.get("response"):
                return {
                    "text": item["response"],
                    "provider": "template_fallback",
                    "persona": persona,
                    "model": "template_fallback",
                    "tokens": None,
                }
    elif isinstance(payload, dict) and payload.get("response"):
        return {
            "text": payload["response"],
            "provider": "template_fallback",
            "persona": persona,
            "model": "template_fallback",
            "tokens": None,
        }

    # Clean up data_context for string interpolation
    clean_context = data_context
    if isinstance(payload, str):
        clean_context = payload
    if clean_context.startswith("User query: "):
        clean_context = clean_context.replace("User query: ", "", 1)

    # Capitalize appropriately or make it fit the sentence if it's just a word
    clean_context = str(clean_context).strip(' "')

    common_tail = (
        "I avoid making assumptions about your financial data to ensure accuracy. "
        "Please ask me directly about your balance, transactions, or forecast for exact numbers."
    )

    if persona == "Cautious Saver":
        text = (
            f"Let's prioritize stability while addressing your {clean_context}. "
            f"Suggested focus: {task_description}. "
            f"{common_tail}"
        )
    elif persona == "Social Spender":
        text = (
            f"Let's work on your {clean_context} in a way that fits your budget. "
            f"Suggested focus: {task_description}. "
            f"{common_tail}"
        )
    else:
        text = (
            f"I can help with that regarding your {clean_context}. "
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


def _generate_conversational_reply(
    persona: str,
    user_query: str,
) -> dict[str, Any] | None:
    llm, provider = get_llm_provider(
        temperature=0.4,
        max_tokens=160,
    )
    if not llm:
        return None

    prompt = PromptTemplate.from_template(
        """You are a helpful financial assistant for CareBank.

Persona: {persona}
User message: {user_query}

Reply with a short, friendly, natural answer. Do not mention policies or internal systems. Keep it to 1-2 sentences.
""",
    )
    chain = prompt | llm

    try:
        response = chain.invoke({"persona": persona, "user_query": user_query})
        model_name, tokens_used = _extract_generation_metadata(provider, response)
        return {
            "text": response.content.strip(),
            "provider": provider,
            "persona": persona,
            "model": model_name,
            "tokens": tokens_used,
        }
    except Exception as exc:
        logger.warning("Conversational LLM fallback failed: %s", exc)
        return None


def _structured_fallback_text(persona: str, data_context: str) -> str | None:
    payload = _parse_json_like_context(data_context)
    if payload is None:
        if isinstance(data_context, str):
            normalized_context = data_context.strip()
            if (
                len(normalized_context) >= 2
                and normalized_context[0] == '"'
                and normalized_context[-1] == '"'
            ):
                normalized_context = normalized_context[1:-1]

            if normalized_context.startswith("User query:"):
                query = (
                    normalized_context.split("User query:", 1)[1].strip().rstrip('"')
                )
                normalized_query = re.sub(r"\s+", " ", query.lower()).strip(" .!?,")
                if normalized_query in _GREETING_QUERIES:
                    reply = _generate_conversational_reply(persona, query)
                    if reply:
                        return reply["text"]
                return (
                    "Hi! I can help with balances, transactions, spending, savings, or payments. "
                    "What would you like to check?"
                )
                reply = _generate_conversational_reply(persona, query)
                if reply:
                    return reply["text"]
                return (
                    "I can help with balances, upcoming bills, transactions, or whether you can afford a purchase. "
                    f"If you meant '{query}', please ask a bit more specifically."
                )
        return None

    metadata = _extract_primary_metadata(payload)
    if not isinstance(metadata, dict):
        return None

    intent = str(metadata.get("intent_handled") or "").strip().lower()
    if intent == "affordability":
        purchase_amount = _coerce_float(metadata.get("purchase_amount"))
        available_balance = _coerce_float(metadata.get("available_balance"))
        post_purchase_balance = _coerce_float(metadata.get("post_purchase_balance"))
        verdict = str(metadata.get("verdict") or "").strip().lower()
        if purchase_amount is None or available_balance is None:
            return None
        amount_str = _format_currency(purchase_amount)
        balance_str = _format_currency(available_balance)
        if verdict == "affordable":
            remaining = _format_currency(post_purchase_balance or 0.0)
            return f"Yes, this looks affordable. You have {balance_str} available, and after a purchase of {amount_str}, you'd still have about {remaining} left."
        if verdict == "tight_buffer":
            remaining = _format_currency(post_purchase_balance or 0.0)
            return f"You can make this purchase, but it would leave a tight buffer. You have {balance_str} available, and after spending {amount_str}, you'd be left with about {remaining}."
        shortfall = _format_currency(abs(post_purchase_balance or 0.0))
        return f"I wouldn't recommend this purchase right now. You have {balance_str} available, so after spending {amount_str}, you'd be short by about {shortfall}."

    if intent == "balance":
        current_balance = _coerce_float(metadata.get("current_balance"))
        available_balance = _coerce_float(metadata.get("available_balance"))
        if current_balance is None and available_balance is None:
            return None
        current_str = _format_currency(current_balance or available_balance or 0.0)
        available_str = _format_currency(available_balance or current_balance or 0.0)
        return f"Your available balance is {available_str}, and your current balance is {current_str}."

    if intent == "what_if":
        expense_amount = _coerce_float(metadata.get("expense_amount"))
        simulated_balance = _coerce_float(metadata.get("simulated_balance"))
        risk_level = str(metadata.get("risk_level") or "").strip().lower()
        if expense_amount is None or simulated_balance is None:
            return None
        return (
            f"If you spend {_format_currency(expense_amount)}, your projected balance would be about {_format_currency(simulated_balance)}. "
            f"That looks like a {risk_level or 'moderate'}-risk move."
        )

    if intent == "health_score":
        score = metadata.get("score")
        top_factor = metadata.get("top_factor")
        weak_factor = metadata.get("weak_factor")
        if score is None:
            return None
        return (
            f"Your financial health score is {score}/100. "
            f"Your strongest area is {top_factor or 'savings'}, and your biggest improvement area is {weak_factor or 'liquidity'}."
        )

    return None


def _parse_json_like_context(data_context: str) -> Any:
    if not isinstance(data_context, str):
        return data_context
    stripped = data_context.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def _extract_primary_metadata(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            return metadata
        return payload
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata")
            if isinstance(metadata, dict):
                return metadata
    return None


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_currency(value: float) -> str:
    return f"₹ {value:,.2f}"


def _serialize_data_context(data_context: Any) -> str:
    """Serialize arbitrary data into JSON for the prompt."""
    try:
        return json.dumps(data_context, default=str)
    except Exception as exc:
        logger.warning("Data context serialization failed: %s", exc)
        return str(data_context)


def _extract_generation_metadata(
    provider: str,
    response: Any,
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
