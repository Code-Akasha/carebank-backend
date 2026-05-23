"""Tool schema definitions and metadata for discovery.

This module provides:
1. Pydantic schemas for tool payload validation
2. Tool metadata (descriptions, capabilities, limits)
3. Tool catalog for fronted discovery
"""

from typing import Any

from pydantic import BaseModel, Field

# ============================================================================
# Action Payload Schemas
# ============================================================================


class RecordNotePayload(BaseModel):
    """Payload for record_note action."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Note message to record",
    )

    class Config:
        example = {"message": "Remember to call the doctor tomorrow"}


class BankTransactionPayload(BaseModel):
    """Base payload schema for bank transaction actions."""

    amount: float = Field(
        ...,
        gt=0,
        description="Transaction amount in rupees (must be positive)",
    )
    description: str | None = Field(
        default=None,
        max_length=200,
        description="Optional transaction description",
    )
    beneficiary_verified: bool = Field(
        default=True,
        description="Whether beneficiary is pre-verified",
    )
    beneficiary_reference: str | None = Field(
        default=None,
        max_length=100,
        description="Reference to existing beneficiary",
    )
    beneficiary_id: str | None = Field(
        default=None,
        max_length=50,
        description="Existing beneficiary ID",
    )
    payment_rail: str | None = Field(
        default=None,
        pattern="^(UPI|NEFT|IMPS|RTGS)$",
        description="Payment method (UPI, NEFT, IMPS, RTGS)",
    )

    class Config:
        example = {
            "amount": 50000.0,
            "description": "Monthly rent payment",
            "beneficiary_verified": True,
        }


class PayRentPayload(BankTransactionPayload):
    """Payload for pay_rent action."""


class PayBillPayload(BankTransactionPayload):
    """Payload for pay_bill action."""


class PayGasPayload(BankTransactionPayload):
    """Payload for pay_gas action."""


class PayUtilityPayload(BankTransactionPayload):
    """Payload for pay_utility action."""


class TransferSavingsPayload(BankTransactionPayload):
    """Payload for transfer_savings action."""


# ============================================================================
# Tool Metadata & Discovery
# ============================================================================


class ToolMetadata(BaseModel):
    """Metadata for a single tool."""

    name: str = Field(description="Human-readable tool name")
    description: str = Field(description="What the tool does")
    action_types: list[str] = Field(
        description="List of action types this tool handles",
    )
    timeout_seconds: int = Field(
        default=15,
        ge=5,
        description="Max execution time per attempt",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        description="Max retry attempts on failure",
    )
    is_deterministic: bool = Field(
        default=True,
        description="Whether tool output is deterministic (no LLM)",
    )
    requires_approval: dict[str, bool] = Field(
        default_factory=dict,
        description="Per-action-type approval requirements",
    )
    max_amount_per_action: dict[str, float | None] = Field(
        default_factory=dict,
        description="Per-action-type amount caps (None = no limit)",
    )


class ActionTypeSchema(BaseModel):
    """Schema definition for a single action type."""

    action_type: str = Field(description="Action type identifier")
    description: str = Field(description="What this action does")
    payload_schema: dict[str, Any] = Field(
        description="JSON Schema for payload validation",
    )
    requires_approval: bool = Field(
        description="Whether approval needed before execution",
    )
    max_amount: float | None = Field(
        default=None,
        description="Max transaction amount (if applicable)",
    )
    default_merchant: str | None = Field(
        default=None,
        description="Default merchant/recipient for action",
    )
    default_category: str | None = Field(
        default=None,
        description="Default transaction category",
    )


class ToolDiscoveryResponse(BaseModel):
    """Complete tool discovery response."""

    tools: list[ToolMetadata] = Field(description="List of available tools")
    action_types: list[ActionTypeSchema] = Field(
        description="Detailed schema for each action type",
    )
    timestamp: str = Field(description="ISO 8601 timestamp of discovery response")


# ============================================================================
# Tool Execution Responses
# ============================================================================


class ToolExecutionResult(BaseModel):
    """Result from tool execution."""

    status: str = Field(description="'ok' or 'error'")
    action_type: str = Field(description="Action type that was executed")
    user_id: str = Field(description="User who performed the action")
    execution_id: int | None = Field(default=None, description="Database execution ID")
    timestamp: str = Field(description="ISO 8601 timestamp of execution")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific metadata",
    )
    error: str | None = Field(
        default=None,
        description="Error message if execution failed",
    )
