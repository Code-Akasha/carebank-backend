from __future__ import annotations

import logging
import time

import httpx
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


def _normalize_provider_type(provider_type: str | None) -> str:
    provider = (provider_type or "ollama").strip().lower()
    if provider in {"ngrok", "local", "ollama"}:
        return "ollama"
    if provider in {"gemini", "openai"}:
        return provider
    return "ollama"


def _build_gemini_llm(
    api_key: str,
    model: str,
    temperature: float,
    max_tokens: int,
):
    """Construct a ChatGoogleGenerativeAI instance."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )


def _get_llm_config_from_db(environment: str) -> dict | None:
    """Retrieve runtime LLM configuration from database for a given environment.
    Returns None if no active config is found.

    This function is called on-demand to check for admin-configured provider settings
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
                )
                .first()
            )

            if config:
                provider_type = LLMAdminService.get_config_provider_type(config)
                token = LLMAdminService.get_decrypted_token(config)
                logger.info(
                    "DB LLM config found: env=%s, provider=%s, model=%s, token_present=%s, url=%s",
                    environment,
                    provider_type,
                    config.ollama_model_default,
                    bool(token),
                    bool(config.tunnel_url),
                )
                if provider_type in {"gemini", "openai"} and not token:
                    logger.warning(
                        "DB config for %s has provider=%s but token decryption returned None! "
                        "Check encryption key consistency (BANKING_API_SECRET / JWT_SECRET). "
                        "Falling through to env-var providers.",
                        environment,
                        provider_type,
                    )
                return {
                    "provider_type": provider_type,
                    "tunnel_url": config.tunnel_url,
                    "model": config.ollama_model_default,
                    "timeout_sec": config.request_timeout_sec,
                    "token": token,
                }
            logger.debug("No active DB LLM config for environment=%s", environment)
            return None
        finally:
            db.close()
    except Exception as e:
        logger.warning("Failed to retrieve LLM config from DB: %s", e)
        return None


def _build_llm_from_admin_config(config: dict, temperature: float, max_tokens: int):
    provider_type = _normalize_provider_type(config.get("provider_type"))
    model = str(config.get("model") or "").strip()
    token = config.get("token")
    tunnel_url = config.get("tunnel_url")

    if provider_type == "ollama":
        if not tunnel_url:
            logger.warning("Admin config: Ollama provider has no tunnel_url, skipping")
            return None, "template_fallback"
        from langchain_ollama import ChatOllama

        llm = ChatOllama(
            base_url=tunnel_url,
            model=model or "qwen3:8b",
            temperature=temperature,
        )
        return llm, f"ollama:{model or 'qwen3:8b'}"

    if provider_type == "gemini":
        if not token:
            logger.warning(
                "Admin config: Gemini provider has no API token (decryption failed or not set). "
                "Cannot initialize Gemini LLM from DB config."
            )
            return None, "template_fallback"
        effective_model = model or "gemini-2.5-flash"
        if effective_model == "gemini-1.5-flash":
            effective_model = "gemini-2.5-flash"
        try:
            llm = _build_gemini_llm(token, effective_model, temperature, max_tokens)
            logger.info(
                "Successfully built Gemini LLM from admin config: model=%s",
                effective_model,
            )
            return llm, f"gemini:{effective_model}"
        except ImportError:
            logger.warning("langchain-google-genai not installed")
            return None, "template_fallback"
        except Exception as e:
            logger.warning("Gemini LLM build from admin config failed: %s", e)
            return None, "template_fallback"

    if provider_type == "openai":
        if not token:
            logger.warning(
                "Admin config: OpenAI provider has no API token (decryption failed or not set)."
            )
            return None, "template_fallback"
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": model or "gpt-4o-mini",
            "api_key": token,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tunnel_url:
            kwargs["base_url"] = tunnel_url
        llm = ChatOpenAI(**kwargs)
        return llm, f"openai:{model or 'gpt-4o-mini'}"

    logger.warning("Admin config: Unknown provider type '%s', skipping", provider_type)
    return None, "template_fallback"


def get_llm_provider(
    temperature: float = 0.7,
    max_tokens: int = 500,
    environment: str | None = None,
) -> tuple[BaseChatModel | None, str]:
    """Factory to retrieve configured LLM.

    Resolution order (first match wins):
    1. Runtime DB config for current environment (admin-managed provider config)
    2. Environment variables: OLLAMA_BASE_URL / GEMINI_API_KEY / OPENAI_API_KEY
    3. Fallback to templates (no LLM)

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
    openai_model = "gpt-4o-mini"

    # 1. Try DB-configured provider first
    db_config = _get_llm_config_from_db(environment)
    if db_config:
        try:
            provider_type = _normalize_provider_type(db_config.get("provider_type"))
            tunnel_url = db_config["tunnel_url"]
            model = db_config["model"]

            if provider_type == "ollama":
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
                        f"Using DB-configured Ollama provider for environment {environment}",
                    )
                    return llm, f"ollama:{model}"
                logger.info(
                    "Ollama endpoint at %s is not reachable for environment %s. Trying env vars.",
                    tunnel_url,
                    environment,
                )
            else:
                llm, provider_name = _build_llm_from_admin_config(
                    db_config,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if llm:
                    logger.info(
                        "✅ Using DB-configured %s provider for environment %s",
                        provider_type,
                        environment,
                    )
                    return llm, provider_name
                logger.warning(
                    "⚠️ DB-configured %s provider for env=%s returned None. "
                    "Falling through to env-var providers.",
                    provider_type,
                    environment,
                )
        except ImportError:
            logger.warning("Required LangChain provider package not installed")
        except Exception as e:
            logger.warning("DB-configured provider initialization failed: %s", e)

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
                                f"Ollama model unavailable: {ollama_model}",
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

    # 3. Try Gemini API (fallback when Ollama is unavailable)
    if settings.gemini_api_key:
        try:
            effective_gemini_model = gemini_model
            if effective_gemini_model == "gemini-1.5-flash":
                effective_gemini_model = "gemini-2.5-flash"

            llm = _build_gemini_llm(
                settings.gemini_api_key,
                effective_gemini_model,
                temperature,
                max_tokens,
            )
            logger.info(
                "🔁 Gemini fallback activated (Ollama unavailable) — using %s",
                effective_gemini_model,
            )
            return llm, f"gemini:{effective_gemini_model}"
        except ImportError:
            logger.warning("langchain-google-genai not installed")
        except Exception as e:
            logger.warning(f"Gemini initialization failed: {e}")

    if settings.openai_api_key:
        try:
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model=openai_model,
                api_key=settings.openai_api_key,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return llm, f"openai:{openai_model}"
        except ImportError:
            logger.warning("langchain-openai not installed")
        except Exception as e:
            logger.warning(f"OpenAI initialization failed: {e}")

    # 3. Fallback to Templates
    logger.warning("No LLM provider configured. Falling back to templates.")
    return None, "template_fallback"
