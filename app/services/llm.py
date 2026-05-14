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


def _ollama_model_exists(base_url: str, model: str) -> bool:
    tags_url = f"{base_url.rstrip('/')}/api/tags"
    try:
        response = httpx.get(tags_url, timeout=2.5)
        response.raise_for_status()
        payload = response.json()
        models = payload.get("models", []) if isinstance(payload, dict) else []
        names = {str(item.get("name", "")) for item in models if isinstance(item, dict)}
        if model in names:
            return True
        if ":" not in model and f"{model}:latest" in names:
            return True
        return False
    except Exception:
        return False


def _ollama_pull_model(base_url: str, model: str) -> bool:
    pull_url = f"{base_url.rstrip('/')}/api/pull"
    try:
        response = httpx.post(
            pull_url,
            json={"name": model, "stream": False},
            timeout=300.0,
        )
        if response.status_code >= 400:
            logger.warning(
                "Ollama model pull failed for %s (status=%s)",
                model,
                response.status_code,
            )
            return False
        return _ollama_model_exists(base_url, model)
    except Exception as exc:
        logger.warning("Ollama model pull error for %s: %s", model, exc)
        return False


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


def _get_ollama_config_from_db(environment: str) -> Optional[dict]:
    """
    Retrieve runtime Ollama configuration from database for a given environment.
    Returns None if no active config is found.

    This function is called on-demand to check for admin-configured tunnel settings
    before falling back to environment variables.
    """
    try:
        # Lazy import to avoid circular dependency
        from app.core.database import SessionLocal
        from app.models.llm_tunnel_config import LLMTunnelConfig
        from app.services.llm_admin_service import LLMAdminService

        db = SessionLocal()
        try:
            config = (
                db.query(LLMTunnelConfig)
                .filter(
                    LLMTunnelConfig.environment == environment,
                    LLMTunnelConfig.is_active,
                    LLMTunnelConfig.provider_type == "ngrok",
                )
                .first()
            )

            if config:
                # Decrypt the token if present
                token = LLMAdminService.get_decrypted_token(config)
                return {
                    "tunnel_url": config.tunnel_url,
                    "model": config.ollama_model_default,
                    "timeout_sec": config.request_timeout_sec,
                    "token": token,
                }
            return None
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"Failed to retrieve Ollama config from DB: {e}")
        return None


def get_llm_provider(
    temperature: float = 0.7,
    max_tokens: int = 500,
    environment: Optional[str] = None,
) -> tuple[Optional[BaseChatModel], str]:
    """
    Factory to retrieve configured LLM.

    Resolution order (first match wins):
    1. Runtime DB config for current environment (ngrok tunnel to local Ollama)
    2. Environment variables: OLLAMA_BASE_URL
    3. Environment variables: GEMINI_API_KEY
    4. Fallback to templates (no LLM)

    Args:
        temperature: Model temperature (0.0 - 1.0)
        max_tokens: Max output tokens
        environment: Environment name (dev/stage/prod); defaults to current environment from settings

    Returns:
        tuple of (LLM Instance or None, Provider Name)
    """
    settings = get_settings()
    if not environment:
        environment = settings.environment

    gemini_model = settings.gemini_model or "gemini-2.5-flash"
    ollama_model = settings.ollama_model or "llama3.2"

    # 1. Try DB-configured ngrok tunnel to local Ollama
    db_config = _get_ollama_config_from_db(environment)
    if db_config:
        try:
            tunnel_url = db_config["tunnel_url"]
            model = db_config["model"]

            if _ollama_is_available(tunnel_url):
                if not _ollama_model_exists(tunnel_url, model):
                    if settings.ollama_auto_pull:
                        logger.info(
                            "Ollama model %s not found in tunnel. Attempting pull...",
                            model,
                        )
                        if not _ollama_pull_model(tunnel_url, model):
                            logger.warning(
                                "Ollama model %s unavailable after pull attempt in tunnel.",
                                model,
                            )
                            raise RuntimeError(f"Ollama model unavailable: {model}")
                    else:
                        logger.warning(
                            "Ollama model %s not found in tunnel and auto-pull disabled.",
                            model,
                        )
                        raise RuntimeError(f"Ollama model unavailable: {model}")

                from langchain_ollama import ChatOllama

                llm = ChatOllama(
                    base_url=tunnel_url,
                    model=model,
                    temperature=temperature,
                )
                logger.info(
                    f"Using DB-configured ngrok tunnel to Ollama for environment {environment}"
                )
                return llm, f"ollama-tunnel:{model}"
            logger.info(
                "Ollama tunnel at %s is not reachable for environment %s. Trying env-var Ollama.",
                tunnel_url,
                environment,
            )
        except ImportError:
            logger.warning("langchain-ollama not installed")
        except Exception as e:
            logger.warning(f"DB-configured Ollama tunnel initialization failed: {e}")

    # 2. Try Environment Variable Ollama
    if settings.ollama_base_url:
        try:
            if _ollama_is_available(settings.ollama_base_url):
                if not _ollama_model_exists(settings.ollama_base_url, ollama_model):
                    if settings.ollama_auto_pull:
                        logger.info(
                            "Ollama model %s not found. Attempting pull...",
                            ollama_model,
                        )
                        if not _ollama_pull_model(
                            settings.ollama_base_url,
                            ollama_model,
                        ):
                            logger.warning(
                                "Ollama model %s unavailable after pull attempt.",
                                ollama_model,
                            )
                            raise RuntimeError(
                                f"Ollama model unavailable: {ollama_model}"
                            )
                    else:
                        logger.warning(
                            "Ollama model %s not found and auto-pull disabled.",
                            ollama_model,
                        )
                        raise RuntimeError(f"Ollama model unavailable: {ollama_model}")

                from langchain_ollama import ChatOllama

                llm = ChatOllama(
                    base_url=settings.ollama_base_url,
                    model=ollama_model,
                    temperature=temperature,
                )
                return llm, f"ollama:{ollama_model}"
            logger.info(
                "Ollama is not reachable at %s. Trying Gemini provider.",
                settings.ollama_base_url,
            )
        except ImportError:
            logger.warning("langchain-ollama not installed")
        except Exception as e:
            logger.warning(f"Ollama initialization failed: {e}")

    # 3. Try Gemini API
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
