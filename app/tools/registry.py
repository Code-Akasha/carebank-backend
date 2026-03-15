from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from app.core.config import get_settings
from app.services.banking_client import trigger_transaction_sync


class ToolNotFoundError(KeyError):
    """Raised when no tool can execute an action type."""


class ActionTool(Protocol):
    def can_handle(self, action_type: str) -> bool: ...

    def execute(self, user_id: str, action_type: str, payload: dict) -> dict: ...


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


class BankTransactionTool:
    _action_types = {
        "pay_rent",
        "pay_bill",
        "pay_gas",
        "pay_utility",
        "transfer_savings",
    }

    _default_merchant = {
        "pay_rent": "Monthly Rent",
        "pay_bill": "Utility Bill",
        "pay_gas": "Gas Service",
        "pay_utility": "Utility Payment",
        "transfer_savings": "Savings Transfer",
    }

    _default_category = {
        "pay_rent": "rent",
        "pay_bill": "bills",
        "pay_gas": "gas",
        "pay_utility": "utilities",
        "transfer_savings": "savings",
    }

    _default_payment_rail = {
        "pay_rent": "NEFT",
        "pay_bill": "UPI",
        "pay_gas": "UPI",
        "pay_utility": "UPI",
        "transfer_savings": "IMPS",
    }

    def can_handle(self, action_type: str) -> bool:
        return action_type in self._action_types

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

        payment_rail = str(
            payload.get("payment_rail")
            or self._default_payment_rail.get(action_type, "UPI")
        ).upper()

        transaction_payload = {
            "user_id": user_id,
            "amount": -abs(amount),
            "merchant": payload.get("merchant")
            or self._default_merchant.get(action_type, "Action Payment"),
            "category": payload.get("category")
            or self._default_category.get(action_type, "payment"),
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


_registry: ActionToolRegistry | None = None


def get_tool_registry() -> ActionToolRegistry:
    global _registry
    if _registry is None:
        registry = ActionToolRegistry()
        registry.register(NoteTool())
        registry.register(BankTransactionTool())
        _registry = registry
    return _registry
