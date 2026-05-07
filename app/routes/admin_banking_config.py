from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.crypto import get_encryption_manager
from app.core.database import SessionLocal
from app.core.security import get_current_user, require_admin
from app.models.banking_connector_config import BankingConnectorConfig
from app.schemas.banking_connector import (
    BankingConnectorConfigCreate,
    BankingConnectorConfigResponse,
    BankingConnectorTestResponse,
)
from app.services.banking_connector_service import BankingConnectorService
from app.services.banking_client import get_banking_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/banking", tags=["admin-banking-config"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _serialize(config: BankingConnectorConfig) -> BankingConnectorConfigResponse:
    token_masked = None
    if config.secret_encrypted:
        token_masked = get_encryption_manager().mask_sensitive_value(
            config.secret_encrypted
        )
    return BankingConnectorConfigResponse(
        id=config.id,
        environment=config.environment,
        provider_type=config.provider_type,
        base_url=config.base_url,
        secret_masked=token_masked,
        request_timeout_sec=config.request_timeout_sec,
        is_active=config.is_active,
        created_by=config.created_by,
        created_at=config.created_at,
        updated_at=config.updated_at,
        last_connectivity_check=config.last_connectivity_check,
        last_error=config.last_error,
    )


@router.get("/connector/{environment}", response_model=BankingConnectorConfigResponse)
async def get_connector_config(
    environment: str,
    current_user=Depends(get_current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    config = BankingConnectorService.get_or_create_config(
        db, environment, current_user.user_id
    )
    return _serialize(config)


@router.put("/connector/{environment}", response_model=BankingConnectorConfigResponse)
async def update_connector_config(
    environment: str,
    payload: BankingConnectorConfigCreate,
    current_user=Depends(get_current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    config = BankingConnectorService.update_config(
        db,
        environment=environment,
        base_url=payload.base_url,
        secret=payload.secret,
        request_timeout_sec=payload.request_timeout_sec,
        user_id=current_user.user_id,
    )
    return _serialize(config)


@router.post("/connector/{environment}/test", response_model=BankingConnectorTestResponse)
async def test_connector(
    environment: str,
    current_user=Depends(get_current_user),
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    config = BankingConnectorService.get_active_config(db, environment)
    if not config or not config.base_url:
        return BankingConnectorTestResponse(status="error", error="Connector not configured")

    client = get_banking_client()
    client.apply_runtime_config(
        config.base_url,
        secret=BankingConnectorService.decrypt_secret(config),
        timeout_sec=config.request_timeout_sec,
    )

    try:
        providers = await client.get_providers()
        BankingConnectorService.record_connectivity_check(db, config, True)
        return BankingConnectorTestResponse(
            status="ok",
            providers_count=len(providers),
        )
    except Exception as exc:
        BankingConnectorService.record_connectivity_check(db, config, False, str(exc))
        return BankingConnectorTestResponse(status="error", error=str(exc))