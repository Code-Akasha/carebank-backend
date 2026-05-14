"""Payment Agent - Handles one-time payment requests via chat."""

import logging
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from app.core.database import SessionLocal
from app.models.beneficiary import Beneficiary
from app.models.user import User
from app.models.payment_settings import PaymentSettings
from app.schemas.payments import ExecutePaymentPayload
from app.services.payment_execution_service import execute_generic_payment

logger = logging.getLogger(__name__)


class PaymentState(str, Enum):
    """States in payment conversation flow."""

    START = "start"
    SELECTING_BENEFICIARY = "selecting_beneficiary"
    ENTERING_AMOUNT = "entering_amount"
    SELECTING_METHOD = "selecting_method"
    CONFIRMING = "confirming"
    ENTERING_MPIN = "entering_mpin"
    COMPLETE = "complete"
    FAILED = "failed"


class PaymentContext(BaseModel):
    """Conversation context for a payment request."""

    user_id: str
    state: PaymentState = PaymentState.START
    beneficiary_id: Optional[int] = None
    amount: Optional[float] = None
    payment_method: Optional[str] = None  # "upi" or "account_transfer"
    description: Optional[str] = None
    requires_mpin: bool = False
    error_message: Optional[str] = None
    execution_id: Optional[str] = None

    class Config:
        use_enum_values = False


class PaymentAgentResponse(BaseModel):
    """Response from payment agent."""

    message: str
    context: PaymentContext
    options: Optional[list[dict]] = None  # For UI buttons/choices
    error: Optional[str] = None


class PaymentAgent:
    """
    Conversational agent for one-time payments.

    Flow:
    1. Ask which beneficiary (show saved contacts)
    2. Ask amount (or "new beneficiary" if not in list)
    3. Confirm payment details
    4. Ask for MPIN if needed
    5. Execute payment

    Example:
        User: "Pay yoga fees"
        Agent: "Which beneficiary? (1) Yoga Planet (2) New beneficiary"
        User: "1"
        Agent: "How much?"
        User: "2000"
        Agent: "Pay ₹2000 to Yoga Planet via UPI? Confirm (yes/no)"
        User: "yes"
        Agent: "Enter MPIN"
        User: "1234"
        Agent: "✅ Payment successful! Transaction ID: MB-xxx"
    """

    def __init__(self, db: Optional[SessionLocal] = None):
        """Initialize agent with optional DB session."""
        self.db = db or SessionLocal()

    def process_message(
        self, user_id: str, message: str, context: PaymentContext
    ) -> PaymentAgentResponse:
        """Process user message and return agent response."""

        try:
            # State machine routing
            if context.state == PaymentState.START:
                return self._handle_start(user_id, message, context)

            elif context.state == PaymentState.SELECTING_BENEFICIARY:
                return self._handle_beneficiary_selection(user_id, message, context)

            elif context.state == PaymentState.ENTERING_AMOUNT:
                return self._handle_amount_entry(user_id, message, context)

            elif context.state == PaymentState.SELECTING_METHOD:
                return self._handle_method_selection(user_id, message, context)

            elif context.state == PaymentState.CONFIRMING:
                return self._handle_confirmation(user_id, message, context)

            elif context.state == PaymentState.ENTERING_MPIN:
                return self._handle_mpin_entry(user_id, message, context)

            elif context.state == PaymentState.COMPLETE:
                return PaymentAgentResponse(
                    message="Payment complete! Start a new payment?",
                    context=PaymentContext(user_id=user_id, state=PaymentState.START),
                    options=[{"label": "New payment", "value": "yes"}],
                )

            else:
                context.error_message = "Unknown state"
                context.state = PaymentState.FAILED
                return PaymentAgentResponse(
                    message="❌ Conversation error. Restarting...",
                    context=context,
                    error="Unknown state",
                )

        except Exception as exc:
            logger.error(f"Payment agent error: {exc}", exc_info=True)
            context.error_message = str(exc)
            context.state = PaymentState.FAILED
            return PaymentAgentResponse(
                message=f"❌ Error: {str(exc)}",
                context=context,
                error=str(exc),
            )

    def _handle_start(
        self, user_id: str, message: str, context: PaymentContext
    ) -> PaymentAgentResponse:
        """Handle initial state - ask which beneficiary."""

        # Get saved beneficiaries
        beneficiaries = (
            self.db.query(Beneficiary).filter(Beneficiary.user_id == user_id).all()
        )

        if not beneficiaries:
            # No saved beneficiaries, start with new
            context.state = PaymentState.ENTERING_AMOUNT
            context.description = message  # Use initial message as description
            return PaymentAgentResponse(
                message="No saved beneficiaries found. Let's add a new one!\n\nWhat's the payment amount?",
                context=context,
                options=[{"label": "Add new beneficiary", "value": "new"}],
            )

        # Build options for saved beneficiaries
        options = [
            {
                "label": f"{b.nickname or b.identifier_value}",
                "value": str(b.id),
                "description": f"{b.identifier_type}: {b.identifier_value}",
            }
            for b in beneficiaries
        ]
        options.append({"label": "New beneficiary", "value": "new"})

        context.state = PaymentState.SELECTING_BENEFICIARY
        return PaymentAgentResponse(
            message="Who would you like to pay?",
            context=context,
            options=options,
        )

    def _handle_beneficiary_selection(
        self, user_id: str, message: str, context: PaymentContext
    ) -> PaymentAgentResponse:
        """Handle beneficiary selection."""

        selection = message.strip().lower()

        if selection == "new":
            # New beneficiary flow
            context.state = PaymentState.ENTERING_AMOUNT
            return PaymentAgentResponse(
                message="Let's add a new beneficiary.\n\nWhat's the payment amount?",
                context=context,
            )

        beneficiaries = (
            self.db.query(Beneficiary).filter(Beneficiary.user_id == user_id).all()
        )

        # Validate existing beneficiary by number, nickname, or identifier
        try:
            beneficiary = None
            beneficiary_id = int(message)
            for item in beneficiaries:
                if item.id == beneficiary_id:
                    beneficiary = item
                    break
        except (ValueError, TypeError):
            for item in beneficiaries:
                alias = (item.nickname or item.identifier_value or "").strip().lower()
                if selection == alias or selection in alias:
                    beneficiary = item
                    break

        if not beneficiary:
            if selection.isdigit():
                return PaymentAgentResponse(
                    message="❌ Beneficiary not found. Please select again.",
                    context=context,
                    error="Beneficiary not found",
                )
            return PaymentAgentResponse(
                message="❌ Invalid selection. Please enter the number or select a beneficiary name.",
                context=context,
                error="Invalid input",
            )

        context.beneficiary_id = beneficiary.id
        context.state = PaymentState.ENTERING_AMOUNT
        return PaymentAgentResponse(
            message=f"Paying {beneficiary.nickname or beneficiary.identifier_value}.\n\nHow much?",
            context=context,
        )

    def _handle_amount_entry(
        self, user_id: str, message: str, context: PaymentContext
    ) -> PaymentAgentResponse:
        """Handle amount input."""

        try:
            amount = float(message)

            if amount <= 0:
                return PaymentAgentResponse(
                    message="❌ Amount must be positive. How much would you like to pay?",
                    context=context,
                    error="Invalid amount",
                )

            if amount > 500000:
                return PaymentAgentResponse(
                    message="❌ Amount exceeds maximum (₹5,00,000). Please enter a lower amount.",
                    context=context,
                    error="Amount exceeds limit",
                )

            context.amount = amount

            # Check if user has payment methods configured
            user = self.db.query(User).filter(User.user_id == user_id).first()
            available_methods = []

            if user.phone_number:
                available_methods.append({"label": "UPI", "value": "upi"})
            if user.account_number:
                available_methods.append(
                    {"label": "Account Transfer", "value": "account_transfer"}
                )

            if not available_methods:
                context.state = PaymentState.FAILED
                return PaymentAgentResponse(
                    message="❌ No payment methods configured. Please add phone or account in settings.",
                    context=context,
                    error="No payment methods",
                )

            if len(available_methods) == 1:
                # Only one method available, use it
                context.payment_method = available_methods[0]["value"]
                context.state = PaymentState.CONFIRMING
                return self._generate_confirmation(context)

            # Multiple methods, ask which one
            context.state = PaymentState.SELECTING_METHOD
            return PaymentAgentResponse(
                message="Which payment method?",
                context=context,
                options=available_methods,
            )

        except (ValueError, TypeError):
            return PaymentAgentResponse(
                message="❌ Invalid amount. Please enter a number.",
                context=context,
                error="Invalid input",
            )

    def _handle_method_selection(
        self, user_id: str, message: str, context: PaymentContext
    ) -> PaymentAgentResponse:
        """Handle payment method selection."""

        if message.lower() not in ["upi", "account_transfer"]:
            return PaymentAgentResponse(
                message="❌ Invalid method. Please select 'UPI' or 'Account Transfer'.",
                context=context,
                error="Invalid method",
            )

        context.payment_method = message.lower()
        context.state = PaymentState.CONFIRMING
        return self._generate_confirmation(context)

    def _generate_confirmation(self, context: PaymentContext) -> PaymentAgentResponse:
        """Generate confirmation message."""

        # Get beneficiary info
        if context.beneficiary_id:
            beneficiary = (
                self.db.query(Beneficiary)
                .filter(Beneficiary.id == context.beneficiary_id)
                .first()
            )
            beneficiary_name = beneficiary.nickname or beneficiary.identifier_value
        else:
            beneficiary_name = "new beneficiary"

        # Get payment settings to check if MPIN required
        settings = (
            self.db.query(PaymentSettings)
            .filter(PaymentSettings.user_id == context.user_id)
            .first()
        )

        requires_mpin = False
        if settings:
            # Check MPIN requirement
            if context.amount > settings.mpin_threshold:
                requires_mpin = True
            # First payment always requires MPIN
            if context.beneficiary_id:
                beneficiary = (
                    self.db.query(Beneficiary)
                    .filter(Beneficiary.id == context.beneficiary_id)
                    .first()
                )
                if beneficiary and beneficiary.payment_count == 0:
                    requires_mpin = True

        context.requires_mpin = requires_mpin

        confirmation = f"Pay ₹{context.amount:,.0f} to {beneficiary_name} via {context.payment_method.upper()}?"
        if requires_mpin:
            confirmation += "\n(MPIN required for this payment)"

        context.state = PaymentState.CONFIRMING
        return PaymentAgentResponse(
            message=confirmation,
            context=context,
            options=[
                {"label": "✅ Yes, confirm", "value": "yes"},
                {"label": "❌ No, cancel", "value": "no"},
            ],
        )

    def _handle_confirmation(
        self, user_id: str, message: str, context: PaymentContext
    ) -> PaymentAgentResponse:
        """Handle confirmation."""

        if message.lower() == "no":
            context.state = PaymentState.FAILED
            return PaymentAgentResponse(
                message="❌ Payment cancelled. Start a new payment?",
                context=context,
            )

        if message.lower() != "yes":
            return PaymentAgentResponse(
                message="Please confirm (yes/no).",
                context=context,
            )

        # Move to MPIN if required, else execute
        if context.requires_mpin:
            context.state = PaymentState.ENTERING_MPIN
            return PaymentAgentResponse(
                message="Enter your MPIN (4-6 digits):",
                context=context,
            )
        else:
            # Execute without MPIN
            return self._execute_payment(user_id, context, mpin=None)

    def _handle_mpin_entry(
        self, user_id: str, message: str, context: PaymentContext
    ) -> PaymentAgentResponse:
        """Handle MPIN entry."""

        if not message or len(message) < 4 or len(message) > 6:
            return PaymentAgentResponse(
                message="❌ MPIN must be 4-6 digits. Please try again:",
                context=context,
            )

        return self._execute_payment(user_id, context, mpin=message)

    def _execute_payment(
        self, user_id: str, context: PaymentContext, mpin: Optional[str]
    ) -> PaymentAgentResponse:
        """Execute the payment."""

        try:
            # Build payment payload
            payload = ExecutePaymentPayload(
                beneficiary_id=context.beneficiary_id,
                amount=context.amount,
                description=context.description or "Payment from chat",
                payment_method=context.payment_method,
                mpin=mpin,
            )

            # Execute payment
            result = execute_generic_payment(self.db, user_id, payload)

            if result.status == "success":
                context.execution_id = result.execution_id
                context.state = PaymentState.COMPLETE

                beneficiary = (
                    self.db.query(Beneficiary)
                    .filter(Beneficiary.id == context.beneficiary_id)
                    .first()
                )
                beneficiary_name = beneficiary.nickname or beneficiary.identifier_value

                return PaymentAgentResponse(
                    message=f"✅ Payment successful!\n\n"
                    f"Amount: ₹{context.amount:,.0f}\n"
                    f"To: {beneficiary_name}\n"
                    f"Transaction ID: {result.transaction_id}",
                    context=context,
                )
            else:
                context.error_message = result.error_reason or "Payment failed"
                context.state = PaymentState.FAILED
                return PaymentAgentResponse(
                    message=f"❌ {result.message}",
                    context=context,
                    error=result.error_reason,
                )

        except Exception as exc:
            logger.error(f"Payment execution failed: {exc}", exc_info=True)
            context.error_message = str(exc)
            context.state = PaymentState.FAILED
            return PaymentAgentResponse(
                message=f"❌ Payment failed: {str(exc)}",
                context=context,
                error=str(exc),
            )

    def close(self) -> None:
        """Close DB session."""
        if self.db:
            self.db.close()


def create_payment_agent() -> PaymentAgent:
    """Factory function to create payment agent."""
    return PaymentAgent()
