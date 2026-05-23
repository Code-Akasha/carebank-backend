"""LLM Admin Service.

Handles CRUD operations, validation, connectivity testing, and caching
for LLM tunnel and provider configurations.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.crypto import get_encryption_manager
from app.models.admin_action_log import AdminActionLog
from app.models.llm_tunnel_config import LLMTunnelConfig

logger = logging.getLogger(__name__)


class LLMAdminService:
    """Service for managing LLM tunnel configurations."""

    @staticmethod
    def normalize_provider_type(provider_type: str | None) -> str:
        provider = (provider_type or "ollama").strip().lower()
        if provider in {"ngrok", "local", "ollama"}:
            return "ollama"
        if provider in {"gemini", "openai"}:
            return provider
        return "ollama"

    @staticmethod
    async def get_or_create_tunnel_config(
        db: Session, environment: str, user_id: str,
    ) -> LLMTunnelConfig:
        """Get existing tunnel config for environment, or create a default (inactive) one.
        """
        config = (
            db.query(LLMTunnelConfig)
            .filter(LLMTunnelConfig.environment == environment)
            .first()
        )

        if not config:
            config = LLMTunnelConfig(
                environment=environment,
                provider_type="ollama",
                tunnel_url="",
                tunnel_auth_token_encrypted=None,
                ollama_model_default="qwen3:8b",
                request_timeout_sec=30,
                is_active=False,
                created_by=user_id,
                updated_by=user_id,
            )
            db.add(config)
            db.commit()
            db.refresh(config)
            logger.info(
                f"Created default inactive tunnel config for environment: {environment}",
            )

        return config

    @staticmethod
    async def update_tunnel_config(
        db: Session,
        environment: str,
        provider_type: str,
        tunnel_url: str | None,
        tunnel_auth_token: str | None,
        ollama_model_default: str,
        request_timeout_sec: int,
        user_id: str,
    ) -> LLMTunnelConfig:
        """Update tunnel configuration for an environment.
        Encrypts sensitive auth token and logs the action.
        """
        config = await LLMAdminService.get_or_create_tunnel_config(
            db, environment, user_id,
        )

        normalized_provider = LLMAdminService.normalize_provider_type(provider_type)

        # Store previous values for audit
        before_tunnel_url = config.tunnel_url
        before_model = config.ollama_model_default
        before_timeout = config.request_timeout_sec
        before_provider = LLMAdminService.normalize_provider_type(config.provider_type)

        # Encrypt the auth token if provided
        if tunnel_auth_token:
            encryptor = get_encryption_manager()
            config.tunnel_auth_token_encrypted = encryptor.encrypt(tunnel_auth_token)
        elif (
            normalized_provider in {"gemini", "openai"}
            and not config.tunnel_auth_token_encrypted
        ):
            raise ValueError(
                "tunnel_auth_token is required for Gemini/OpenAI providers",
            )

        # Update configuration
        config.provider_type = normalized_provider
        config.tunnel_url = tunnel_url or ""
        config.ollama_model_default = ollama_model_default
        config.request_timeout_sec = request_timeout_sec
        config.is_active = True
        config.updated_by = user_id
        config.updated_at = datetime.now(timezone.utc)

        # Log the action
        audit_log = AdminActionLog(
            admin_user_id=user_id,
            action_type="llm_config_update",
            resource_type="tunnel",
            resource_id=environment,
            environment=environment,
            before_value=(
                f"provider={before_provider}, url={before_tunnel_url}, model={before_model}, "
                f"timeout={before_timeout}"
            ),
            after_value=(
                f"provider={normalized_provider}, url={tunnel_url or ''}, model={ollama_model_default}, "
                f"timeout={request_timeout_sec}"
            ),
            status="success",
        )
        db.add(audit_log)
        db.commit()
        db.refresh(config)
        logger.info(f"Updated tunnel config for environment: {environment}")

        return config

    @staticmethod
    async def activate_tunnel_config(
        db: Session, environment: str, user_id: str,
    ) -> LLMTunnelConfig:
        """Activate tunnel configuration for an environment.
        """
        config = await LLMAdminService.get_or_create_tunnel_config(
            db, environment, user_id,
        )

        if not config.is_active:
            config.is_active = True
            config.updated_by = user_id
            config.updated_at = datetime.now(timezone.utc)

            audit_log = AdminActionLog(
                admin_user_id=user_id,
                action_type="llm_config_update",
                resource_type="tunnel",
                resource_id=environment,
                environment=environment,
                before_value="is_active=False",
                after_value="is_active=True",
                status="success",
            )
            db.add(audit_log)
            db.commit()
            db.refresh(config)
            logger.info(f"Activated tunnel config for environment: {environment}")

        return config

    @staticmethod
    async def deactivate_tunnel_config(
        db: Session, environment: str, user_id: str,
    ) -> LLMTunnelConfig:
        """Deactivate tunnel configuration for an environment.
        """
        config = await LLMAdminService.get_or_create_tunnel_config(
            db, environment, user_id,
        )

        if config.is_active:
            config.is_active = False
            config.updated_by = user_id
            config.updated_at = datetime.now(timezone.utc)

            audit_log = AdminActionLog(
                admin_user_id=user_id,
                action_type="llm_config_update",
                resource_type="tunnel",
                resource_id=environment,
                environment=environment,
                before_value="is_active=True",
                after_value="is_active=False",
                status="success",
            )
            db.add(audit_log)
            db.commit()
            db.refresh(config)
            logger.info(f"Deactivated tunnel config for environment: {environment}")

        return config

    @staticmethod
    def get_tunnel_config_by_environment(
        db: Session, environment: str,
    ) -> LLMTunnelConfig | None:
        """Retrieve active tunnel config for environment, or None if not configured.
        """
        return (
            db.query(LLMTunnelConfig)
            .filter(
                LLMTunnelConfig.environment == environment,
                LLMTunnelConfig.is_active,
            )
            .first()
        )

    @staticmethod
    def get_config_provider_type(config: LLMTunnelConfig) -> str:
        return LLMAdminService.normalize_provider_type(config.provider_type)

    @staticmethod
    def get_decrypted_token(config: LLMTunnelConfig) -> str | None:
        """Decrypt and return the tunnel auth token for this config.
        """
        if not config.tunnel_auth_token_encrypted:
            return None
        try:
            encryptor = get_encryption_manager()
            return encryptor.decrypt(config.tunnel_auth_token_encrypted)
        except Exception as e:
            logger.error(f"Failed to decrypt token for config id {config.id}: {e}")
            return None

    @staticmethod
    def record_connectivity_check(
        db: Session,
        config: LLMTunnelConfig,
        is_success: bool,
        error_message: str | None = None,
    ) -> None:
        """Record the result of a connectivity test.
        """
        config.last_connectivity_check = datetime.now(timezone.utc)
        if is_success:
            config.last_error = None
        else:
            config.last_error = error_message or "Unknown error"
        db.commit()
        logger.info(
            f"Recorded connectivity check for config id {config.id}: "
            f"success={is_success}, error={config.last_error}",
        )
