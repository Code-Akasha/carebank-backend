"""
Unified action payload validation service.

Centralizes validation logic before tool execution:
1. Validates payload against tool schema
2. Checks policy constraints (amounts, approvals)
3. Returns detailed validation results
"""

from app.services.action_policy import _FALLBACK_POLICY_MATRIX
from app.tools.registry import get_tool_registry


class PayloadValidationError(ValueError):
    """Raised when payload validation fails."""

    def __init__(self, action_type: str, errors: list[str]):
        self.action_type = action_type
        self.errors = errors
        super().__init__(f"Payload validation failed for {action_type}: {'; '.join(errors)}")


def validate_action_payload(
    action_type: str, payload: dict
) -> tuple[bool, list[str]]:
    """
    Validate action payload against tool schema and policy constraints.

    **Parameters:**
    - action_type: The action identifier
    - payload: Dictionary payload to validate

    **Returns:**
    - is_valid: bool indicating if validation passed
    - errors: List of validation error messages (empty if valid)

    **Validation Steps:**
    1. Check tool exists for action_type
    2. Validate against Pydantic schema
    3. Check policy constraints (amount limits, etc)
    """
    errors: list[str] = []

    registry = get_tool_registry()

    # Step 1: Verify tool exists
    tool = registry.get_tool_for_action(action_type)
    if not tool:
        errors.append(f"No tool registered for action_type: {action_type}")
        return False, errors

    # Step 2: Validate against schema
    schema = tool.get_schema(action_type)
    if schema:
        try:
            schema.model_validate(payload)
        except Exception as exc:
            errors.append(f"Schema validation failed: {str(exc)}")
            return False, errors

    # Step 3: Check policy constraints
    policy = _FALLBACK_POLICY_MATRIX.get(action_type)
    if policy and policy.max_amount is not None:
        amount = payload.get("amount")
        if amount is not None:
            try:
                amount_value = float(amount)
                if amount_value <= 0:
                    errors.append("Amount must be positive")
                elif amount_value > policy.max_amount:
                    errors.append(
                        f"Amount {amount_value} exceeds policy maximum of {policy.max_amount}"
                    )
            except (ValueError, TypeError):
                errors.append(f"Invalid amount format: {amount}")

    return len(errors) == 0, errors


def validate_or_raise(action_type: str, payload: dict) -> None:
    """
    Validate action payload, raising an exception if validation fails.

    Useful for synchronous validation during action execution.

    **Raises:**
    - PayloadValidationError: If validation fails

    **Example:**
    ```python
    validate_or_raise("pay_rent", {"amount": 50000.0})
    ```
    """
    is_valid, errors = validate_action_payload(action_type, payload)
    if not is_valid:
        raise PayloadValidationError(action_type, errors)


def get_validation_warnings(action_type: str, payload: dict) -> list[str]:
    """
    Get validation warnings (non-blocking issues) for a payload.

    Useful for UI hints without blocking action execution.

    **Returns:**
    - List of warning messages (empty if no warnings)

    **Current Warnings:**
    - Amount is near policy limit (>90%)
    """
    warnings: list[str] = []

    policy = _FALLBACK_POLICY_MATRIX.get(action_type)
    if policy and policy.max_amount is not None:
        amount = payload.get("amount")
        if amount:
            try:
                amount_value = float(amount)
                threshold = policy.max_amount * 0.9
                if amount_value > threshold:
                    warnings.append(
                        f"Amount {amount_value} is near the policy limit of {policy.max_amount}"
                    )
            except (ValueError, TypeError):
                pass

    return warnings
