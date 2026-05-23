"""Agent Prompt Configuration Service.

Manages versioned system prompts for agents with rollback and validation.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.admin_action_log import AdminActionLog
from app.models.agent_prompt_config import AgentPromptConfig

logger = logging.getLogger(__name__)


class AgentPromptService:
    """Service for managing agent system prompts with versioning."""

    @staticmethod
    def _validate_prompt_template(prompt: str) -> tuple[bool, str | None]:
        """Validate that a prompt template has basic valid structure.
        Returns (is_valid, error_message)
        """
        if not prompt or not prompt.strip():
            return False, "Prompt cannot be empty"

        if len(prompt) > 50000:  # Max 50KB prompt
            return False, "Prompt exceeds maximum length (50KB)"

        # Could add more sophisticated validation (e.g., template syntax checks)
        return True, None

    @staticmethod
    async def get_active_prompt(
        db: Session, agent_name: str, environment: str,
    ) -> AgentPromptConfig | None:
        """Retrieve the active (published) prompt for an agent in an environment.
        Returns None if no active prompt is configured.
        """
        return (
            db.query(AgentPromptConfig)
            .filter(
                AgentPromptConfig.agent_name == agent_name,
                AgentPromptConfig.environment == environment,
                AgentPromptConfig.is_active,
            )
            .first()
        )

    @staticmethod
    async def get_prompt_history(
        db: Session, agent_name: str, environment: str,
    ) -> list[AgentPromptConfig]:
        """Retrieve all versions (active and inactive) of a prompt for an agent/env.
        Ordered by version descending (newest first).
        """
        return (
            db.query(AgentPromptConfig)
            .filter(
                AgentPromptConfig.agent_name == agent_name,
                AgentPromptConfig.environment == environment,
            )
            .order_by(AgentPromptConfig.version.desc())
            .all()
        )

    @staticmethod
    async def publish_prompt(
        db: Session,
        agent_name: str,
        environment: str,
        system_prompt: str,
        user_id: str,
        notes: str | None = None,
    ) -> AgentPromptConfig:
        """Publish a new version of a system prompt for an agent.
        - Validates prompt structure
        - Increments version number
        - Deactivates previous version
        - Creates audit log entry
        """
        # Validate prompt
        is_valid, error = AgentPromptService._validate_prompt_template(system_prompt)
        if not is_valid:
            logger.error(
                f"Prompt validation failed for {agent_name}/{environment}: {error}",
            )
            raise ValueError(f"Invalid prompt: {error}")

        # Get current active version to determine next version number
        active_prompt = await AgentPromptService.get_active_prompt(
            db, agent_name, environment,
        )
        next_version = (active_prompt.version + 1) if active_prompt else 1

        # Deactivate previous version
        if active_prompt:
            active_prompt.is_active = False
            db.add(active_prompt)

        # Create new version
        new_prompt = AgentPromptConfig(
            agent_name=agent_name,
            environment=environment,
            system_prompt=system_prompt,
            version=next_version,
            is_active=True,
            created_by=user_id,
            updated_by=user_id,
            notes=notes,
        )
        db.add(new_prompt)

        # Log the action
        audit_log = AdminActionLog(
            admin_user_id=user_id,
            action_type="prompt_publish",
            resource_type="prompt",
            resource_id=agent_name,
            environment=environment,
            before_value=f"version={active_prompt.version if active_prompt else 0}",
            after_value=f"version={next_version}",
            status="success",
        )
        db.add(audit_log)
        db.commit()
        db.refresh(new_prompt)

        logger.info(
            f"Published new version {next_version} of prompt for "
            f"agent {agent_name} in environment {environment}",
        )
        return new_prompt

    @staticmethod
    async def rollback_prompt(
        db: Session,
        agent_name: str,
        environment: str,
        target_version: int,
        user_id: str,
    ) -> AgentPromptConfig:
        """Rollback to a previous version of a prompt.
        - Finds the target version (must exist)
        - Deactivates current active version
        - Activates the target version
        - Creates audit log entry
        """
        # Get current active version
        active_prompt = await AgentPromptService.get_active_prompt(
            db, agent_name, environment,
        )
        if not active_prompt:
            raise ValueError(
                f"No active prompt for agent {agent_name} in environment {environment}",
            )

        # Get target version
        target_prompt = (
            db.query(AgentPromptConfig)
            .filter(
                AgentPromptConfig.agent_name == agent_name,
                AgentPromptConfig.environment == environment,
                AgentPromptConfig.version == target_version,
            )
            .first()
        )

        if not target_prompt:
            raise ValueError(
                f"Target version {target_version} not found for "
                f"agent {agent_name} in environment {environment}",
            )

        if target_prompt.id == active_prompt.id:
            raise ValueError(f"Target version {target_version} is already active")

        # Deactivate current active version
        active_prompt.is_active = False
        db.add(active_prompt)

        # Activate target version
        target_prompt.is_active = True
        target_prompt.updated_by = user_id
        target_prompt.updated_at = datetime.now(timezone.utc)
        db.add(target_prompt)

        # Log the action
        audit_log = AdminActionLog(
            admin_user_id=user_id,
            action_type="prompt_rollback",
            resource_type="prompt",
            resource_id=agent_name,
            environment=environment,
            before_value=f"version={active_prompt.version}",
            after_value=f"version={target_version}",
            status="success",
        )
        db.add(audit_log)
        db.commit()
        db.refresh(target_prompt)

        logger.info(
            f"Rolled back prompt for agent {agent_name} in environment {environment} "
            f"from version {active_prompt.version} to version {target_version}",
        )
        return target_prompt

    @staticmethod
    def get_available_agents(db: Session) -> list[str]:
        """Get list of unique agent names that have prompts configured.
        """
        agents = db.query(AgentPromptConfig.agent_name).distinct().all()
        return [agent[0] for agent in agents]

    @staticmethod
    async def ensure_default_prompts(db: Session, environment: str) -> None:
        """Ensure default prompts exist for all core agents in an environment.
        This is called during initialization to provide fallback prompts.
        """
        default_agents = {
            "coordinator": "You are a coordinator agent. Analyze the user's intent and route to appropriate specialist agents.",
            "payment_agent": "You are a payment agent. Help users initiate and confirm payment transactions.",
            "communication_agent": "You are a communication agent. Provide helpful financial communication.",
            "autosavings_agent": "You are an autosavings agent. Recommend and manage automatic savings plans.",
            "opportunity_agent": "You are an opportunity agent. Identify financial opportunities for the user.",
        }

        for agent_name, default_prompt in default_agents.items():
            existing = await AgentPromptService.get_active_prompt(
                db, agent_name, environment,
            )
            if not existing:
                prompt = AgentPromptConfig(
                    agent_name=agent_name,
                    environment=environment,
                    system_prompt=default_prompt,
                    version=1,
                    is_active=True,
                    created_by="system",
                    updated_by="system",
                    notes="Auto-generated default prompt",
                )
                db.add(prompt)
                logger.info(f"Created default prompt for {agent_name} in {environment}")

        db.commit()
