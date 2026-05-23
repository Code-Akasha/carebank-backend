"""Tool discovery and metadata endpoints.

Allows frontend and other clients to:
1. List available tools
2. Get schemas for action type validation
3. Query action policies and limits
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.schemas.tools import ActionTypeSchema, ToolDiscoveryResponse, ToolMetadata
from app.services.action_policy import _FALLBACK_POLICY_MATRIX
from app.tools.registry import get_tool_registry

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("/available", response_model=ToolDiscoveryResponse)
def get_available_tools():
    """Discover all available tools and their supported action types.

    Returns schema information for each action type to enable frontend
    validation and dynamic UI rendering.

    **Response includes:**
    - List of available tools with metadata
    - Detailed schema for each action type (including validation rules)
    - Policy information (approval requirements, amount limits)
    """
    registry = get_tool_registry()

    # Gather all tool metadata
    tools_metadata: list[ToolMetadata] = []
    action_types_schema: list[ActionTypeSchema] = []

    for tool in registry.get_all_tools():
        metadata = tool.get_metadata()

        # Convert dict metadata to ToolMetadata model
        tool_meta = ToolMetadata(
            name=metadata.get("name", "Unknown Tool"),
            description=metadata.get("description", ""),
            action_types=metadata.get("action_types", []),
            timeout_seconds=metadata.get("timeout_seconds", 15),
            max_retries=metadata.get("max_retries", 2),
            is_deterministic=metadata.get("is_deterministic", True),
            requires_approval=metadata.get("requires_approval", {}),
            max_amount_per_action=metadata.get("max_amount_per_action", {}),
        )
        tools_metadata.append(tool_meta)

        # Build schema for each action type this tool handles
        for action_type in metadata.get("action_types", []):
            schema_model = tool.get_schema(action_type)

            # Build default merchant/category from tool metadata
            defaults = {}
            if hasattr(tool, "_action_defaults"):
                defaults = tool._action_defaults.get(action_type, {})

            # Get schema info
            schema_dict = {}
            if schema_model:
                schema_dict = schema_model.model_json_schema()

            action_schema = ActionTypeSchema(
                action_type=action_type,
                description=f"Execute {action_type} action",
                payload_schema=schema_dict,
                requires_approval=metadata.get("requires_approval", {}).get(
                    action_type,
                    False,
                ),
                max_amount=metadata.get("max_amount_per_action", {}).get(action_type),
                default_merchant=defaults.get("merchant"),
                default_category=defaults.get("category"),
            )
            action_types_schema.append(action_schema)

    return ToolDiscoveryResponse(
        tools=tools_metadata,
        action_types=action_types_schema,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/{action_type}/schema")
def get_action_schema(action_type: str):
    """Get the detailed schema for a specific action type.

    **Parameters:**
    - action_type: The action identifier (e.g., 'pay_rent', 'transfer_savings')

    **Returns:**
    - JSON Schema for the action's payload
    - Validation rules and constraints
    - Example payload
    """
    registry = get_tool_registry()

    # Find the tool that handles this action
    tool = registry.get_tool_for_action(action_type)
    if not tool:
        raise HTTPException(
            status_code=404,
            detail=f"No tool registered for action_type: {action_type}. "
            f"Available actions: {', '.join(registry.get_action_types())}",
        )

    # Get schema model
    schema_model = tool.get_schema(action_type)
    if not schema_model:
        raise HTTPException(
            status_code=400,
            detail=f"Action type '{action_type}' does not require payload validation",
        )

    # Get policy
    policy = _FALLBACK_POLICY_MATRIX.get(action_type)

    return {
        "action_type": action_type,
        "schema": schema_model.model_json_schema(),
        "requires_approval": policy.requires_approval if policy else False,
        "max_amount": policy.max_amount if policy else None,
        "example_payload": schema_model.model_json_schema().get("example", {}),
    }


@router.post("/{action_type}/validate")
def validate_action_payload(action_type: str, payload: dict):
    """Dry-run validation of an action payload without executing it.

    Useful for frontend to validate user input before submitting approval request.

    **Parameters:**
    - action_type: The action identifier
    - payload: JSON payload to validate

    **Returns:**
    - is_valid: bool
    - errors: List of validation errors (if invalid)
    - warnings: List of policy warnings (e.g., amount near limit)
    """
    registry = get_tool_registry()

    # Validate payload against tool schema
    is_valid, error_msg = registry.validate_payload(action_type, payload)

    if not is_valid:
        return {
            "is_valid": False,
            "action_type": action_type,
            "errors": [error_msg] if error_msg else [],
            "warnings": [],
        }

    # Check against policy
    policy = _FALLBACK_POLICY_MATRIX.get(action_type)
    warnings = []

    if policy and policy.max_amount is not None:
        amount = payload.get("amount")
        if amount:
            try:
                amount_float = float(amount)
                if amount_float > policy.max_amount:
                    return {
                        "is_valid": False,
                        "action_type": action_type,
                        "errors": [
                            f"Amount {amount_float} exceeds policy maximum of {policy.max_amount}",
                        ],
                        "warnings": [],
                    }
                if amount_float > policy.max_amount * 0.9:  # 90% threshold
                    warnings.append(
                        f"Amount {amount_float} is near the policy limit of {policy.max_amount}",
                    )
            except (ValueError, TypeError):
                pass

    return {
        "is_valid": True,
        "action_type": action_type,
        "requires_approval": policy.requires_approval if policy else False,
        "errors": [],
        "warnings": warnings,
    }


@router.get("/action-types/list")
def list_action_types():
    """Get a simple list of all supported action types.

    Useful for frontend navigation/menu rendering.

    **Returns:**
    - action_types: List of action type identifiers
    - count: Total number of supported actions
    """
    registry = get_tool_registry()
    action_types = sorted(registry.get_action_types())

    return {
        "action_types": action_types,
        "count": len(action_types),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
