"""Error handling utilities for execution errors.

Converts internal exception types into user-friendly messages
while preserving technical details in logs.
"""

from app.services.payload_validator import PayloadValidationError
from app.tools.registry import ToolNotFoundError


class ExecutionErrorMessage:
    """User-friendly error message with suggestions."""

    def __init__(
        self,
        message: str,
        error_type: str,
        suggestion: str | None = None,
        is_retryable: bool = False,
    ):
        self.message = message
        self.error_type = error_type
        self.suggestion = suggestion
        self.is_retryable = is_retryable

    def to_dict(self) -> dict:
        result = {
            "error": self.message,
            "error_type": self.error_type,
            "is_retryable": self.is_retryable,
        }
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result


def format_execution_error(
    exc: Exception,
    action_type: str | None = None,
) -> ExecutionErrorMessage:
    """Convert an exception into a user-friendly error message.

    **Parameters:**
    - exc: The exception that occurred
    - action_type: The action type being executed (for context)

    **Returns:**
    - ExecutionErrorMessage with user-readable text and suggestions
    """
    # Tool not found
    if isinstance(exc, ToolNotFoundError):
        return ExecutionErrorMessage(
            message=f"Action type '{action_type}' is not currently supported.",
            error_type="tool_not_found",
            suggestion="Contact support if you need this action enabled.",
            is_retryable=False,
        )

    # Payload validation failed
    if isinstance(exc, PayloadValidationError):
        return ExecutionErrorMessage(
            message=f"Invalid action parameters: {'; '.join(exc.errors)}",
            error_type="validation_error",
            suggestion="Please check the payment amount and try again.",
            is_retryable=False,
        )

    # Amount validation
    if isinstance(exc, ValueError) and "amount" in str(exc).lower():
        return ExecutionErrorMessage(
            message=f"Invalid amount: {exc!s}",
            error_type="amount_error",
            suggestion="Amount must be positive and within policy limits.",
            is_retryable=False,
        )

    # Timeout or bank unavailable (generic exception messages)
    error_str = str(exc).lower()
    if "timeout" in error_str or "deadline" in error_str:
        return ExecutionErrorMessage(
            message="The bank is taking longer than expected to process your request.",
            error_type="timeout_error",
            suggestion="Please wait a moment and check your transaction history in a few minutes.",
            is_retryable=True,
        )

    if "connection" in error_str or "refused" in error_str:
        return ExecutionErrorMessage(
            message="Unable to connect to the bank. Our system may be temporarily unavailable.",
            error_type="connection_error",
            suggestion="Please try again in a moment. If the problem persists, contact support.",
            is_retryable=True,
        )

    if "502" in error_str or "503" in error_str or "504" in error_str:
        return ExecutionErrorMessage(
            message="The bank service is temporarily unavailable.",
            error_type="service_unavailable",
            suggestion="This is temporary. Please try again shortly.",
            is_retryable=True,
        )

    # Generic execution error
    return ExecutionErrorMessage(
        message="An unexpected error occurred while processing your request.",
        error_type="execution_error",
        suggestion="Please try again or contact support if the problem continues.",
        is_retryable=True,
    )


def get_friendly_action_error_response(
    exc: Exception,
    action_type: str | None = None,
) -> dict:
    """Get a normalized error response dict for action execution failures.

    **Returns:**
    ```python
    {
        "status": "error",
        "error": "User-friendly message",
        "error_type": "tool_not_found|validation_error|...",
        "suggestion": "Optional: what to do next",
        "is_retryable": bool,
    }
    ```
    """
    msg = format_execution_error(exc, action_type)
    return {
        "status": "error",
        **msg.to_dict(),
    }
