from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel

from app.core.config import get_settings
from app.services.banking_client import trigger_transaction_sync


class ToolNotFoundError(KeyError):
    """Raised when no tool can execute an action type."""


class ActionTool(Protocol):
    """Protocol for action tools.

    Tools are responsible for executing specific action types.
    All tools must implement:
    - can_handle(action_type) → bool
    - execute(user_id, action_type, payload) → dict
    - get_metadata() → ToolMetadata for discovery
    - get_schema(action_type) → Pydantic model for payload validation
    """

    def can_handle(self, action_type: str) -> bool:
        """Check if this tool can handle the given action type."""
        ...

    def execute(self, user_id: str, action_type: str, payload: dict) -> dict:
        """Execute the action. Returns result dict with 'status' and tool-specific fields."""
        ...

    def get_metadata(self) -> dict[str, Any]:
        """Return tool metadata including name, description, action types, and policy info."""
        ...

    def get_schema(self, action_type: str) -> type[BaseModel] | None:
        """Return Pydantic model for payload validation. Return None if no schema needed."""
        ...


class NoteTool:
    """Local deterministic tool for internal notes and dry-run flows."""

    _action_types = {"record_note"}

    def can_handle(self, action_type: str) -> bool:
        return action_type in self._action_types

    def execute(self, user_id: str, action_type: str, payload: dict) -> dict:
        return {
            "status": "ok",
            "action_type": action_type,
            "user_id": user_id,
            "message": payload.get("message", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_metadata(self) -> dict[str, Any]:
        """Return metadata for note tool."""
        from app.schemas.tools import RecordNotePayload

        return {
            "name": "Note Tool",
            "description": "Record notes and reminders locally (no external dependencies)",
            "action_types": list(self._action_types),
            "timeout_seconds": 5,
            "max_retries": 0,
            "is_deterministic": True,
            "requires_approval": {"record_note": False},
            "max_amount_per_action": {},
            "payload_schema": {
                "record_note": RecordNotePayload.model_json_schema(),
            },
        }

    def get_schema(self, action_type: str) -> type[BaseModel] | None:
        """Return Pydantic model for payload validation."""
        if action_type == "record_note":
            from app.schemas.tools import RecordNotePayload

            return RecordNotePayload
        return None


class BankTransactionTool:
    _action_defaults = {
        "pay_rent": {
            "merchant": "Monthly Rent",
            "category": "rent",
            "payment_rail": "NEFT",
        },
        "pay_bill": {
            "merchant": "Utility Bill",
            "category": "bills",
            "payment_rail": "UPI",
        },
        "pay_gas": {
            "merchant": "Gas Service",
            "category": "gas",
            "payment_rail": "UPI",
        },
        "pay_utility": {
            "merchant": "Utility Payment",
            "category": "utilities",
            "payment_rail": "UPI",
        },
        "transfer_savings": {
            "merchant": "Savings Transfer",
            "category": "savings",
            "payment_rail": "IMPS",
        },
    }
    _action_types = set(_action_defaults)

    def can_handle(self, action_type: str) -> bool:
        return action_type in self._action_types

    def get_metadata(self) -> dict[str, Any]:
        """Return metadata for bank transaction tool."""
        from app.services.action_policy import _FALLBACK_POLICY_MATRIX

        return {
            "name": "Bank Transaction Tool",
            "description": "Execute bank transactions via the banking proxy (payments, transfers)",
            "action_types": list(self._action_types),
            "timeout_seconds": 15,
            "max_retries": 2,
            "is_deterministic": False,  # May depend on proxy state
            "requires_approval": {
                action_type: _FALLBACK_POLICY_MATRIX[action_type].requires_approval
                for action_type in self._action_types
            },
            "max_amount_per_action": {
                action_type: _FALLBACK_POLICY_MATRIX[action_type].max_amount
                for action_type in self._action_types
            },
        }

    def get_schema(self, action_type: str) -> type[BaseModel] | None:
        """Return Pydantic model for payload validation."""
        from app.schemas.tools import (
            PayBillPayload,
            PayGasPayload,
            PayRentPayload,
            PayUtilityPayload,
            TransferSavingsPayload,
        )

        schema_mapping = {
            "pay_rent": PayRentPayload,
            "pay_bill": PayBillPayload,
            "pay_gas": PayGasPayload,
            "pay_utility": PayUtilityPayload,
            "transfer_savings": TransferSavingsPayload,
        }
        return schema_mapping.get(action_type)

    @staticmethod
    def _resolve_webhook_url() -> str | None:
        settings = get_settings()
        base = settings.backend_public_url.strip().rstrip("/")
        if not base:
            return None
        return f"{base}/api/actions/webhooks/mockbank"

    def execute(self, user_id: str, action_type: str, payload: dict) -> dict:
        amount = float(payload.get("amount", 0))
        if amount <= 0:
            raise ValueError("amount must be positive")

        defaults = self._action_defaults.get(action_type, {})

        payment_rail = str(
            payload.get("payment_rail") or defaults.get("payment_rail", "UPI")
        ).upper()

        transaction_payload = {
            "user_id": user_id,
            "amount": -abs(amount),
            "merchant": payload.get("merchant")
            or defaults.get("merchant", "Action Payment"),
            "category": payload.get("category") or defaults.get("category", "payment"),
            "description": payload.get("description")
            or f"Executed by action engine: {action_type}",
            "action_type": action_type,
            "payment_rail": payment_rail,
            "beneficiary_verified": bool(payload.get("beneficiary_verified", True)),
        }

        execution_id = payload.get("_execution_id")
        approval_request_id = payload.get("_approval_request_id")
        idempotency_key = payload.get("_execution_idempotency_key")
        if idempotency_key:
            transaction_payload["idempotency_key"] = str(idempotency_key)

        webhook_url = self._resolve_webhook_url()
        if webhook_url:
            transaction_payload["webhook_url"] = webhook_url

        metadata: dict[str, str | int] = {}
        if execution_id is not None:
            metadata["execution_id"] = int(execution_id)
        if approval_request_id is not None:
            metadata["approval_request_id"] = int(approval_request_id)
        if metadata:
            transaction_payload["metadata"] = metadata

        beneficiary_reference = payload.get("beneficiary_reference")
        if beneficiary_reference:
            transaction_payload["beneficiary_reference"] = beneficiary_reference

        beneficiary_id = payload.get("beneficiary_id")
        if beneficiary_id:
            transaction_payload["beneficiary_id"] = beneficiary_id

        upstream_response = trigger_transaction_sync(transaction_payload)

        return {
            "status": "ok",
            "action_type": action_type,
            "transaction": transaction_payload,
            "upstream_response": upstream_response,
        }


class ActionToolRegistry:
    def __init__(self) -> None:
        self._tools: list[ActionTool] = []

    def register(self, tool: ActionTool) -> None:
        self._tools.append(tool)

    def get(self, action_type: str) -> ActionTool:
        for tool in self._tools:
            if tool.can_handle(action_type):
                return tool
        raise ToolNotFoundError(f"No tool registered for action_type={action_type}")

    def get_all_tools(self) -> list[ActionTool]:
        """Return all registered tools."""
        return self._tools.copy()

    def get_action_types(self) -> set[str]:
        """Return all supported action types across all tools."""
        action_types = set()
        for tool in self._tools:
            metadata = tool.get_metadata()
            action_types.update(metadata.get("action_types", []))
        return action_types

    def get_tool_for_action(self, action_type: str) -> ActionTool | None:
        """Get the tool that handles an action type, or None if not found."""
        for tool in self._tools:
            if tool.can_handle(action_type):
                return tool
        return None

    def validate_payload(
        self, action_type: str, payload: dict
    ) -> tuple[bool, str | None]:
        """Validate payload against tool schema.

        Returns: (is_valid, error_message)
        - is_valid: True if payload matches schema
        - error_message: Validation error if invalid, None if valid
        """
        tool = self.get_tool_for_action(action_type)
        if tool is None:
            return False, f"No tool handles action_type: {action_type}"

        schema = tool.get_schema(action_type)
        if schema is None:
            # No schema defined, allow any dict
            return True, None

        try:
            schema.model_validate(payload)
            return True, None
        except Exception as exc:
            return False, f"Payload validation failed: {str(exc)}"


class GenericPaymentTool:
    """Generic payment tool supporting one-time and recurring payments."""

    _action_types = {"execute_payment", "setup_recurring_payment"}

    def can_handle(self, action_type: str) -> bool:
        return action_type in self._action_types

    def get_metadata(self) -> dict[str, Any]:
        """Return metadata for generic payment tool."""
        from app.schemas.payments import ExecutePaymentPayload, RecurringPaymentCreate

        return {
            "name": "Generic Payment Tool",
            "description": "Execute one-time and recurring payments to any beneficiary",
            "action_types": list(self._action_types),
            "timeout_seconds": 20,
            "max_retries": 2,
            "is_deterministic": False,
            "requires_approval": {
                "execute_payment": True,
                "setup_recurring_payment": False,
            },
            "max_amount_per_action": {
                "execute_payment": 500000.0,  # ₹5 lakh max per payment
                "setup_recurring_payment": 100000.0,  # ₹1 lakh max per recurring cycle
            },
            "payload_schema": {
                "execute_payment": ExecutePaymentPayload.model_json_schema(),
                "setup_recurring_payment": RecurringPaymentCreate.model_json_schema(),
            },
        }

    def get_schema(self, action_type: str) -> type[BaseModel] | None:
        """Return Pydantic model for payload validation."""
        from app.schemas.payments import ExecutePaymentPayload, RecurringPaymentCreate

        schema_mapping = {
            "execute_payment": ExecutePaymentPayload,
            "setup_recurring_payment": RecurringPaymentCreate,
        }
        return schema_mapping.get(action_type)

    def execute(self, user_id: str, action_type: str, payload: dict) -> dict:
        """Execute payment action."""
        from app.core.database import SessionLocal
        from app.schemas.payments import ExecutePaymentPayload, RecurringPaymentCreate
        from app.services.payment_execution_service import execute_generic_payment
        from app.services.recurring_payment_service import create_recurring_payment_rule

        db = SessionLocal()
        try:
            if action_type == "execute_payment":
                # Validate and execute one-time payment
                payload_obj = ExecutePaymentPayload.model_validate(payload)
                result = execute_generic_payment(db, user_id, payload_obj)

                return {
                    "status": "ok",
                    "action_type": action_type,
                    "execution_status": result.status,
                    "message": result.message,
                    "execution_id": result.execution_id,
                    "transaction_id": result.transaction_id,
                    "error_reason": result.error_reason,
                }

            elif action_type == "setup_recurring_payment":
                # Create recurring payment rule
                payload_obj = RecurringPaymentCreate.model_validate(payload)
                rule = create_recurring_payment_rule(db, user_id, payload_obj)

                return {
                    "status": "ok",
                    "action_type": action_type,
                    "recurring_rule_id": str(rule.id),
                    "message": f"Recurring payment '{rule.description}' scheduled for {rule.frequency}",
                    "next_run_date": rule.next_run_date.isoformat(),
                    "frequency": rule.frequency,
                    "amount": rule.amount,
                }

            else:
                return {
                    "status": "error",
                    "action_type": action_type,
                    "message": f"Unknown action type: {action_type}",
                }

        except Exception as exc:
            return {
                "status": "error",
                "action_type": action_type,
                "message": f"Payment execution failed: {str(exc)}",
                "error_reason": str(exc),
            }
        finally:
            db.close()


_registry: ActionToolRegistry | None = None


def get_tool_registry() -> ActionToolRegistry:
    global _registry
    if _registry is None:
        registry = ActionToolRegistry()
        registry.register(NoteTool())
        registry.register(BankTransactionTool())
        registry.register(GenericPaymentTool())
        _registry = registry
    return _registry
