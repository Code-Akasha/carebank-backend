"""LLM Model Discovery Service.

Discovers available models from configured LLM providers:
- Ollama: via tunnel URL (local/ngrok)
- Gemini: via google-genai SDK

Includes caching with short TTL to reduce repeated API calls.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class OllamaModel:
    """Represents an available Ollama model."""

    def __init__(self, name: str, size_bytes: int, available: bool = True):
        self.name = name
        self.size_bytes = size_bytes
        self.size_gb = size_bytes / (1024**3)
        self.available = available

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "size_gb": round(self.size_gb, 2),
            "size_bytes": self.size_bytes,
            "available": self.available,
        }


class ModelDiscoveryCache:
    """In-memory cache for model discovery results."""

    def __init__(self, ttl_seconds: int = 60):
        self.ttl_seconds = ttl_seconds
        self.cache: dict[str, tuple[datetime, list[OllamaModel]]] = {}

    def get(self, key: str) -> list[OllamaModel] | None:
        """Retrieve cached models if still fresh."""
        if key not in self.cache:
            return None

        timestamp, models = self.cache[key]
        if datetime.utcnow() - timestamp > timedelta(seconds=self.ttl_seconds):
            del self.cache[key]
            return None

        return models

    def set(self, key: str, models: list[OllamaModel]) -> None:
        """Cache models with current timestamp."""
        self.cache[key] = (datetime.utcnow(), models)

    def clear(self, key: str | None = None) -> None:
        """Clear cache entry or entire cache."""
        if key:
            self.cache.pop(key, None)
        else:
            self.cache.clear()


# Global discovery cache instance
_discovery_cache = ModelDiscoveryCache(ttl_seconds=60)


class LLMModelDiscoveryService:
    """Service for discovering available LLM models from Ollama."""

    @staticmethod
    async def discover_models(
        tunnel_url: str,
        timeout_sec: int = 10,
        force_refresh: bool = False,
    ) -> list[OllamaModel]:
        """Fetch available models from Ollama endpoint.

        Args:
            tunnel_url: Base URL of Ollama instance (e.g., "https://abc.ngrok.io")
            timeout_sec: Request timeout in seconds
            force_refresh: Skip cache and fetch fresh

        Returns:
            List of OllamaModel objects

        Raises:
            httpx.RequestError: If connection fails
            ValueError: If response format is unexpected

        """
        cache_key = tunnel_url

        # Check cache first (unless force_refresh)
        if not force_refresh:
            cached_models = _discovery_cache.get(cache_key)
            if cached_models is not None:
                logger.debug(f"Returning cached models for {tunnel_url}")
                return cached_models

        try:
            # Fetch models from Ollama tags endpoint
            models_url = f"{tunnel_url}/api/tags"
            logger.debug(f"Fetching models from {models_url}")

            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                response = await client.get(models_url)
                response.raise_for_status()
                data = response.json()

            # Parse response and build model list
            models: list[OllamaModel] = []
            for model_info in data.get("models", []):
                model_name = model_info.get("name")
                size_bytes = model_info.get("size", 0)

                if model_name:
                    models.append(
                        OllamaModel(
                            name=model_name,
                            size_bytes=size_bytes,
                            available=True,
                        ),
                    )

            # Cache and return
            _discovery_cache.set(cache_key, models)
            logger.info(f"Discovered {len(models)} models from {tunnel_url}")
            return models

        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Ollama at {tunnel_url}: {e}")
            raise
        except (KeyError, ValueError) as e:
            logger.error(f"Unexpected response format from Ollama at {tunnel_url}: {e}")
            raise ValueError(f"Invalid Ollama response: {e!s}")

    @staticmethod
    async def test_model_availability(
        tunnel_url: str,
        model_name: str,
        timeout_sec: int = 10,
    ) -> bool:
        """Test if a specific model is available and can be used.

        Args:
            tunnel_url: Base URL of Ollama instance
            model_name: Model name to test
            timeout_sec: Request timeout in seconds

        Returns:
            True if model is available, False otherwise

        """
        try:
            models = await LLMModelDiscoveryService.discover_models(
                tunnel_url,
                timeout_sec=timeout_sec,
            )
            model_names = {m.name for m in models}
            is_available = model_name in model_names
            logger.debug(f"Model {model_name} available: {is_available}")
            return is_available
        except Exception as e:
            logger.error(f"Failed to test model availability: {e}")
            return False

    @staticmethod
    async def test_connectivity(
        tunnel_url: str,
        timeout_sec: int = 5,
    ) -> dict[str, Any]:
        """Test connectivity to Ollama instance.

        Args:
            tunnel_url: Base URL of Ollama instance
            timeout_sec: Request timeout in seconds

        Returns:
            Dict with status, models_count, and error (if any)

        """
        try:
            start = datetime.utcnow()
            models = await LLMModelDiscoveryService.discover_models(
                tunnel_url,
                timeout_sec=timeout_sec,
                force_refresh=True,
            )
            elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000

            return {
                "status": "ok",
                "models_count": len(models),
                "response_time_ms": round(elapsed_ms, 2),
            }
        except Exception as e:
            logger.error(f"Connectivity test failed for {tunnel_url}: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    @staticmethod
    def clear_cache(tunnel_url: str | None = None) -> None:
        """Manually clear discovery cache.

        Args:
            tunnel_url: Specific URL to clear, or None for entire cache

        """
        _discovery_cache.clear(tunnel_url)
        logger.debug(f"Cleared discovery cache for {tunnel_url or 'all'}")


# ---------------------------------------------------------------------------
# Gemini Model Discovery
# ---------------------------------------------------------------------------


class GeminiModel:
    """Represents an available Gemini model."""

    def __init__(self, name: str, display_name: str, supported_actions: list[str]):
        self.name = name
        self.display_name = display_name
        self.supported_actions = supported_actions

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "supported_actions": self.supported_actions,
            "available": True,
        }


# Simple in-memory cache for Gemini model lists (keyed by masked API key prefix)
_GEMINI_MODEL_CACHE: dict[str, tuple[datetime, list[GeminiModel]]] = {}
_GEMINI_MODEL_CACHE_TTL = 120  # seconds


class GeminiModelDiscovery:
    """Discovers available Gemini models via the google-genai SDK."""

    @staticmethod
    def list_models(
        api_key: str,
        *,
        only_generative: bool = True,
        force_refresh: bool = False,
    ) -> list[GeminiModel]:
        """List available Gemini models for the given API key.

        Args:
            api_key: Google AI API key.
            only_generative: If True, filter to models that support generateContent.
            force_refresh: Skip in-memory cache.

        Returns:
            List of GeminiModel objects.

        Raises:
            ImportError: If google-genai is not installed.
            Exception: On API errors.

        """
        cache_key = api_key[:8]  # Use prefix only — never log full key
        now = datetime.utcnow()

        if not force_refresh and cache_key in _GEMINI_MODEL_CACHE:
            ts, cached = _GEMINI_MODEL_CACHE[cache_key]
            if (now - ts).total_seconds() < _GEMINI_MODEL_CACHE_TTL:
                logger.debug("Returning cached Gemini model list")
                return cached

        try:
            from google import genai  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-genai is not installed. Run: pip install google-genai"
            ) from exc

        client = genai.Client(api_key=api_key)
        raw_models = client.models.list()

        models: list[GeminiModel] = []
        for m in raw_models:
            actions: list[str] = list(getattr(m, "supported_actions", []) or [])
            if only_generative and "generateContent" not in actions:
                continue
            name = str(getattr(m, "name", "") or "")
            display_name = str(getattr(m, "display_name", name) or name)
            models.append(GeminiModel(name=name, display_name=display_name, supported_actions=actions))

        _GEMINI_MODEL_CACHE[cache_key] = (now, models)
        logger.info("Discovered %d Gemini models", len(models))
        return models

    @staticmethod
    def test_connectivity(api_key: str) -> dict[str, Any]:
        """Verify the API key is valid and models are reachable.

        Returns a dict compatible with ConnectivityTestResult.

        """
        try:
            start = datetime.utcnow()
            models = GeminiModelDiscovery.list_models(api_key, force_refresh=True)
            elapsed_ms = (datetime.utcnow() - start).total_seconds() * 1000
            return {
                "status": "ok",
                "models_count": len(models),
                "response_time_ms": round(elapsed_ms, 2),
            }
        except Exception as exc:
            logger.error("Gemini connectivity test failed: %s", exc)
            return {"status": "error", "error": str(exc)}
