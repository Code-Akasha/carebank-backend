"""Admin LLM Configuration Routes.

All routes are protected by admin role requirement.
Handles tunnel configuration, model discovery, and prompt customization.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.crypto import get_encryption_manager
from app.core.database import SessionLocal
from app.core.security import get_current_user, require_admin
from app.models.agent_prompt_config import AgentPromptConfig
from app.schemas.admin_llm import (
    AgentPromptConfigCreate,
    AgentPromptConfigResponse,
    ConnectivityTestResult,
    LLMTunnelConfigCreate,
    LLMTunnelConfigResponse,
    ModelListResponse,
    PromptListResponse,
)
from app.services.agent_prompt_service import AgentPromptService
from app.services.llm_admin_service import LLMAdminService
from app.services.llm_model_discovery import LLMModelDiscoveryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/llm", tags=["admin-llm-config"])


def _serialize_config(config) -> LLMTunnelConfigResponse:
    token_masked = None
    if config.tunnel_auth_token_encrypted:
        encryptor = get_encryption_manager()
        token_masked = encryptor.mask_sensitive_value(
            config.tunnel_auth_token_encrypted,
        )

    return LLMTunnelConfigResponse(
        id=config.id,
        environment=config.environment,
        provider_type=LLMAdminService.get_config_provider_type(config),
        tunnel_url=config.tunnel_url or "",
        tunnel_auth_token_masked=token_masked,
        ollama_model_default=config.ollama_model_default,
        request_timeout_sec=config.request_timeout_sec,
        is_active=config.is_active,
        last_connectivity_check=config.last_connectivity_check,
        last_error=config.last_error,
        created_by=config.created_by,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# Tunnel Configuration Endpoints
# ============================================================================


@router.get("/tunnel/{environment}", response_model=LLMTunnelConfigResponse)
async def get_tunnel_config(
    environment: str,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LLMTunnelConfigResponse:
    """Retrieve tunnel configuration for an environment.
    Returns config with masked auth token.
    """
    try:
        config = await LLMAdminService.get_or_create_tunnel_config(
            db,
            environment,
            current_user.user_id,
        )
        return _serialize_config(config)
    except Exception as e:
        logger.error(f"Failed to get tunnel config for {environment}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve tunnel configuration",
        )


@router.put("/tunnel/{environment}", response_model=LLMTunnelConfigResponse)
async def update_tunnel_config(
    environment: str,
    config_update: LLMTunnelConfigCreate,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LLMTunnelConfigResponse:
    """Update tunnel configuration for an environment.
    Auth token is encrypted before storage.
    """
    try:
        config = await LLMAdminService.update_tunnel_config(
            db,
            environment=environment,
            provider_type=config_update.provider_type,
            tunnel_url=config_update.tunnel_url,
            tunnel_auth_token=config_update.tunnel_auth_token,
            ollama_model_default=config_update.ollama_model_default,
            request_timeout_sec=config_update.request_timeout_sec,
            user_id=current_user.user_id,
        )
        return _serialize_config(config)
    except ValueError as e:
        logger.error(f"Validation error updating tunnel config: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to update tunnel config for {environment}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update tunnel configuration",
        )


@router.post("/tunnel/{environment}/test", response_model=ConnectivityTestResult)
async def test_tunnel_connectivity(
    environment: str,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ConnectivityTestResult:
    """Test connectivity to configured Ollama tunnel for an environment.
    Records the result and returns status.
    """
    try:
        config = await LLMAdminService.get_or_create_tunnel_config(
            db,
            environment,
            current_user.user_id,
        )

        if not config.is_active or not config.tunnel_url:
            return ConnectivityTestResult(
                status="error",
                error="Tunnel not configured or inactive for this environment",
            )

        if LLMAdminService.get_config_provider_type(config) != "ollama":
            return ConnectivityTestResult(
                status="error",
                error="Connectivity test is only available for local Ollama providers",
            )

        # Perform connectivity test
        test_result = await LLMModelDiscoveryService.test_connectivity(
            config.tunnel_url,
            timeout_sec=config.request_timeout_sec,
        )

        # Record the result
        is_success = test_result.get("status") == "ok"
        error_msg = test_result.get("error")
        LLMAdminService.record_connectivity_check(db, config, is_success, error_msg)

        return ConnectivityTestResult(**test_result)
    except Exception as e:
        logger.error(f"Connectivity test failed for {environment}: {e}")
        return ConnectivityTestResult(
            status="error",
            error=f"Connectivity test failed: {e!s}",
        )


# ============================================================================
# Model Discovery Endpoints
# ============================================================================


@router.get("/models", response_model=ModelListResponse)
async def list_ollama_models(
    environment: str,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ModelListResponse:
    """List available Ollama models from configured tunnel for an environment.
    Results are cached for 60 seconds.
    """
    try:
        config = await LLMAdminService.get_or_create_tunnel_config(
            db,
            environment,
            current_user.user_id,
        )

        if LLMAdminService.get_config_provider_type(config) != "ollama":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Model discovery is only available for local Ollama providers",
            )

        if not config.is_active or not config.tunnel_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tunnel not configured or inactive for this environment",
            )

        # Discover models
        models = await LLMModelDiscoveryService.discover_models(
            config.tunnel_url,
            timeout_sec=config.request_timeout_sec,
        )

        model_list = [model.to_dict() for model in models]
        return ModelListResponse(
            models=model_list,
            model_count=len(model_list),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list models for {environment}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to discover models: {e!s}",
        )


# ============================================================================
# Prompt Configuration Endpoints
# ============================================================================


@router.get("/prompts", response_model=PromptListResponse)
async def list_all_prompts(
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PromptListResponse:
    """List all active agent prompts across all environments."""
    try:
        prompts = db.query(AgentPromptConfig).filter(AgentPromptConfig.is_active).all()

        return PromptListResponse(
            prompts=[AgentPromptConfigResponse.from_orm(p) for p in prompts],
            total_count=len(prompts),
        )
    except Exception as e:
        logger.error(f"Failed to list prompts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list prompts",
        )


@router.get("/prompts/{agent_name}", response_model=PromptListResponse)
async def get_prompt_history(
    agent_name: str,
    environment: str,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PromptListResponse:
    """Get full version history for a specific agent prompt in an environment.
    Includes both active and inactive versions.
    """
    try:
        history = await AgentPromptService.get_prompt_history(
            db,
            agent_name,
            environment,
        )

        return PromptListResponse(
            prompts=[AgentPromptConfigResponse.from_orm(p) for p in history],
            total_count=len(history),
        )
    except Exception as e:
        logger.error(
            f"Failed to get prompt history for {agent_name}/{environment}: {e}",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve prompt history",
        )


@router.put("/prompts/{agent_name}/publish", response_model=AgentPromptConfigResponse)
async def publish_agent_prompt(
    agent_name: str,
    environment: str,
    prompt_data: AgentPromptConfigCreate,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AgentPromptConfigResponse:
    """Publish a new version of an agent prompt for an environment.
    Automatically deactivates the previous version.
    """
    try:
        new_prompt = await AgentPromptService.publish_prompt(
            db,
            agent_name=agent_name,
            environment=environment,
            system_prompt=prompt_data.system_prompt,
            user_id=current_user["user_id"],
            notes=prompt_data.notes,
        )

        return AgentPromptConfigResponse.from_orm(new_prompt)
    except ValueError as e:
        logger.error(f"Validation error publishing prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to publish prompt for {agent_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to publish prompt",
        )


@router.post("/prompts/{agent_name}/rollback", response_model=AgentPromptConfigResponse)
async def rollback_agent_prompt(
    agent_name: str,
    environment: str,
    target_version: int,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AgentPromptConfigResponse:
    """Rollback an agent prompt to a specific previous version in an environment."""
    try:
        rolled_back = await AgentPromptService.rollback_prompt(
            db,
            agent_name=agent_name,
            environment=environment,
            target_version=target_version,
            user_id=current_user["user_id"],
        )

        return AgentPromptConfigResponse.from_orm(rolled_back)
    except ValueError as e:
        logger.error(f"Rollback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to rollback prompt for {agent_name}/{environment}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rollback prompt",
        )
