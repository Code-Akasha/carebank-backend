from __future__ import annotations

import logging
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def get_llm_provider(
    temperature: float = 0.7,
    max_tokens: int = 500,
) -> tuple[Optional[BaseChatModel], str]:
    """
    Factory to retrieve configured LLM.
    Prioritizes Ollama (Local) -> Gemini -> None (Fallback to templates)

    Returns:
        tuple of (LLM Instance or None, Provider Name)
    """
    settings = get_settings()

    # 1. Try Ollama (Local LLM)
    if settings.ollama_base_url:
        try:
            from langchain_ollama import ChatOllama

            # Use llama3.2 as default small fast model, or mistral
            llm = ChatOllama(
                base_url=settings.ollama_base_url,
                model="llama3.2",
                temperature=temperature,
            )
            return llm, "ollama:llama3.2"
        except ImportError:
            logger.warning("langchain-ollama not installed")
        except Exception as e:
            logger.warning(f"Ollama initialization failed: {e}")

    # 2. Try Gemini API
    if settings.gemini_api_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=settings.gemini_api_key,
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            return llm, "gemini:gemini-2.5-flash"
        except ImportError:
            logger.warning("langchain-google-genai not installed")
        except Exception as e:
            logger.warning(f"Gemini initialization failed: {e}")

    # 3. Fallback to Templates
    logger.warning("No LLM provider configured. Falling back to templates.")
    return None, "template_fallback"
