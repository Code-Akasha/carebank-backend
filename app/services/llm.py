from __future__ import annotations

import logging
from typing import Optional
import httpx
import time

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_OLLAMA_HEALTH_CACHE: dict[str, tuple[float, bool]] = {}
_OLLAMA_HEALTH_TTL_SECONDS = 15.0


def _ollama_is_available(base_url: str) -> bool:
    now = time.monotonic()
    cached = _OLLAMA_HEALTH_CACHE.get(base_url)
    if cached and now - cached[0] < _OLLAMA_HEALTH_TTL_SECONDS:
        return cached[1]

    health_url = f"{base_url.rstrip('/')}/api/tags"
    try:
        response = httpx.get(health_url, timeout=1.5)
        available = response.status_code == 200
        _OLLAMA_HEALTH_CACHE[base_url] = (now, available)
        return available
    except Exception:
        _OLLAMA_HEALTH_CACHE[base_url] = (now, False)
        return False


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
    gemini_model = settings.gemini_model or "gemini-2.5-flash"

    # 1. Try Ollama (Local LLM)
    if settings.ollama_base_url:
        try:
            if _ollama_is_available(settings.ollama_base_url):
                from langchain_ollama import ChatOllama

                llm = ChatOllama(
                    base_url=settings.ollama_base_url,
                    model="llama3.2",
                    temperature=temperature,
                )
                return llm, "ollama:llama3.2"
            logger.info(
                "Ollama is not reachable at %s. Trying Gemini provider.",
                settings.ollama_base_url,
            )
        except ImportError:
            logger.warning("langchain-ollama not installed")
        except Exception as e:
            logger.warning(f"Ollama initialization failed: {e}")

    # 2. Try Gemini API
    if settings.gemini_api_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model=gemini_model,
                google_api_key=settings.gemini_api_key,
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            return llm, f"gemini:{gemini_model}"
        except ImportError:
            logger.warning("langchain-google-genai not installed")
        except Exception as e:
            logger.warning(f"Gemini initialization failed: {e}")

    # 3. Fallback to Templates
    logger.warning("No LLM provider configured. Falling back to templates.")
    return None, "template_fallback"
