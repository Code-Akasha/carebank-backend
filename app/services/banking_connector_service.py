"""Runtime banking connector configuration service."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.crypto import get_encryption_manager
from app.models.admin_action_log import AdminActionLog
from app.models.banking_connector_config import BankingConnectorConfig

logger = logging.getLogger(__name__)


class BankingConnectorService:
    @staticmethod
    def get_active_config(
        db: Session, environment: str,
    ) -> BankingConnectorConfig | None:
        return (
            db.query(BankingConnectorConfig)
            .filter(
                BankingConnectorConfig.environment == environment,
                BankingConnectorConfig.is_active,
            )
            .order_by(BankingConnectorConfig.updated_at.desc())
            .first()
        )

    @staticmethod
    def get_or_create_config(
        db: Session, environment: str, user_id: str,
    ) -> BankingConnectorConfig:
        config = (
            db.query(BankingConnectorConfig)
            .filter(BankingConnectorConfig.environment == environment)
            .first()
        )
        if config:
            return config

        config = BankingConnectorConfig(
            environment=environment,
            provider_type="mockbank",
            base_url="",
            secret_encrypted=None,
            request_timeout_sec=10,
            is_active=False,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        return config

    @staticmethod
    def update_config(
        db: Session,
        environment: str,
        base_url: str,
        secret: str | None,
        request_timeout_sec: int,
        user_id: str,
        is_active: bool = True,
    ) -> BankingConnectorConfig:
        config = BankingConnectorService.get_or_create_config(db, environment, user_id)
        before = {
            "base_url": config.base_url,
            "timeout": config.request_timeout_sec,
            "is_active": config.is_active,
        }

        config.base_url = base_url.rstrip("/")
        config.request_timeout_sec = request_timeout_sec
        config.is_active = is_active
        if secret is not None and secret != "":
            config.secret_encrypted = get_encryption_manager().encrypt(secret)
        config.updated_by = user_id
        config.updated_at = datetime.now(timezone.utc)

        db.add(
            AdminActionLog(
                admin_user_id=user_id,
                action_type="banking_connector_update",
                resource_type="banking_connector",
                resource_id=environment,
                environment=environment,
                before_value=str(before),
                after_value=str(
                    {
                        "base_url": config.base_url,
                        "timeout": config.request_timeout_sec,
                        "is_active": config.is_active,
                    },
                ),
                status="success",
            ),
        )
        db.commit()
        db.refresh(config)
        return config

    @staticmethod
    def decrypt_secret(config: BankingConnectorConfig) -> str | None:
        if not config.secret_encrypted:
            return None
        return get_encryption_manager().decrypt(config.secret_encrypted)

    @staticmethod
    def record_connectivity_check(
        db: Session,
        config: BankingConnectorConfig,
        is_success: bool,
        error_message: str | None = None,
    ) -> None:
        config.last_connectivity_check = datetime.now(timezone.utc)
        config.last_error = None if is_success else error_message
        db.commit()
