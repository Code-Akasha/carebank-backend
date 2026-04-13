"""Recurring Payment Agent - Handles recurring payment setup via chat."""

import logging
from enum import Enum
from typing import Optional
from datetime import date

from pydantic import BaseModel

from app.core.database import SessionLocal
from app.models.beneficiary import Beneficiary
from app.models.payment_settings import PaymentSettings
from app.schemas.payments import RecurringPaymentCreate
from app.services.recurring_payment_service import create_recurring_payment_rule

logger = logging.getLogger(__name__)


class RecurringSetupState(str, Enum):
    """States in recurring payment setup conversation."""

    START = "start"
    SELECTING_BENEFICIARY = "selecting_beneficiary"
    ENTERING_AMOUNT = "entering_amount"
    SELECTING_FREQUENCY = "selecting_frequency"
    ENTERING_FREQUENCY_CONFIG = "entering_frequency_config"
    ENTERING_START_DATE = "entering_start_date"
    ENTERING_END_DATE = "entering_end_date"
    ASKING_APPROVAL = "asking_approval"
    CONFIRMING = "confirming"
    COMPLETE = "complete"
    FAILED = "failed"


class RecurringSetupContext(BaseModel):
    """Conversation context for recurring payment setup."""

    user_id: str
    state: RecurringSetupState = RecurringSetupState.START
    beneficiary_id: Optional[int] = None
    amount: Optional[float] = None
    description: Optional[str] = None
    frequency: Optional[str] = None  # "daily", "weekly", "monthly", "quarterly"
    day_of_month: Optional[int] = None  # 1-31 for monthly/quarterly
    day_of_week: Optional[str] = None  # "monday"-"sunday" for weekly
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    requires_approval: bool = True
    rule_id: Optional[int] = None
    error_message: Optional[str] = None

    class Config:
        use_enum_values = False


class RecurringSetupResponse(BaseModel):
    """Response from recurring setup agent."""

    message: str
    context: RecurringSetupContext
    options: Optional[list[dict]] = None
    error: Optional[str] = None


class RecurringPaymentAgent:
    """
    Conversational agent for setting up recurring payments.

    Flow:
    1. Ask which beneficiary (show saved contacts)
    2. Ask amount
    3. Ask frequency (daily/weekly/monthly/quarterly)
    4. Ask frequency config (day of week/month)
    5. Ask start date (optional)
    6. Ask end date (optional)
    7. Ask if approval needed
    8. Confirm and create

    Example:
        User: "Setup recurring yoga"
        Agent: "Which beneficiary?"
        User: "Yoga Planet"
        Agent: "How much each time?"
        User: "2000"
        Agent: "How often? (1) Daily (2) Weekly (3) Monthly (4) Quarterly"
        User: "2"
        Agent: "Which day of week? (1) Monday (2) Tuesday ... (7) Sunday"
        User: "1"
        Agent: "Start date? (YYYY-MM-DD or press enter for today)"
        User: "2026-04-13"
        Agent: "End date? (YYYY-MM-DD or leave blank for never)"
        User: ""
        Agent: "Require approval each time? (yes/no)"
        User: "no"
        Agent: "✅ Recurring set up: ₹2000 weekly on Monday to Yoga Planet"
    """

    def __init__(self, db: Optional[SessionLocal] = None):
        """Initialize agent with optional DB session."""
        self.db = db or SessionLocal()

    def process_message(
        self, user_id: str, message: str, context: RecurringSetupContext
    ) -> RecurringSetupResponse:
        """Process user message and return agent response."""

        try:
            # State machine routing
            if context.state == RecurringSetupState.START:
                return self._handle_start(user_id, message, context)

            elif context.state == RecurringSetupState.SELECTING_BENEFICIARY:
                return self._handle_beneficiary_selection(user_id, message, context)

            elif context.state == RecurringSetupState.ENTERING_AMOUNT:
                return self._handle_amount_entry(user_id, message, context)

            elif context.state == RecurringSetupState.SELECTING_FREQUENCY:
                return self._handle_frequency_selection(user_id, message, context)

            elif context.state == RecurringSetupState.ENTERING_FREQUENCY_CONFIG:
                return self._handle_frequency_config(user_id, message, context)

            elif context.state == RecurringSetupState.ENTERING_START_DATE:
                return self._handle_start_date(user_id, message, context)

            elif context.state == RecurringSetupState.ENTERING_END_DATE:
                return self._handle_end_date(user_id, message, context)

            elif context.state == RecurringSetupState.ASKING_APPROVAL:
                return self._handle_approval(user_id, message, context)

            elif context.state == RecurringSetupState.CONFIRMING:
                return self._handle_confirmation(user_id, message, context)

            elif context.state == RecurringSetupState.COMPLETE:
                return RecurringSetupResponse(
                    message="✅ Recurring payment set up successfully! Setup another one?",
                    context=RecurringSetupContext(
                        user_id=user_id, state=RecurringSetupState.START
                    ),
                    options=[{"label": "Yes, setup another", "value": "yes"}],
                )

            else:
                context.error_message = "Unknown state"
                context.state = RecurringSetupState.FAILED
                return RecurringSetupResponse(
                    message="❌ Conversation error. Restarting...",
                    context=context,
                    error="Unknown state",
                )

        except Exception as exc:
            logger.error(f"Recurring agent error: {exc}", exc_info=True)
            context.error_message = str(exc)
            context.state = RecurringSetupState.FAILED
            return RecurringSetupResponse(
                message=f"❌ Error: {str(exc)}",
                context=context,
                error=str(exc),
            )

    def _handle_start(
        self, user_id: str, message: str, context: RecurringSetupContext
    ) -> RecurringSetupResponse:
        """Handle initial state - ask which beneficiary."""

        # Get saved beneficiaries
        beneficiaries = (
            self.db.query(Beneficiary).filter(Beneficiary.user_id == user_id).all()
        )

        if not beneficiaries:
            context.state = RecurringSetupState.FAILED
            return RecurringSetupResponse(
                message="❌ No saved beneficiaries. Please save a beneficiary first.",
                context=context,
                error="No beneficiaries",
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

        context.state = RecurringSetupState.SELECTING_BENEFICIARY
        return RecurringSetupResponse(
            message="Which beneficiary?",
            context=context,
            options=options,
        )

    def _handle_beneficiary_selection(
        self, user_id: str, message: str, context: RecurringSetupContext
    ) -> RecurringSetupResponse:
        """Handle beneficiary selection."""

        try:
            beneficiary_id = int(message)
            beneficiary = (
                self.db.query(Beneficiary)
                .filter(
                    Beneficiary.id == beneficiary_id,
                    Beneficiary.user_id == user_id,
                )
                .first()
            )

            if not beneficiary:
                return RecurringSetupResponse(
                    message="❌ Beneficiary not found. Please select again.",
                    context=context,
                    error="Beneficiary not found",
                )

            context.beneficiary_id = beneficiary_id
            context.description = beneficiary.nickname or beneficiary.identifier_value
            context.state = RecurringSetupState.ENTERING_AMOUNT
            return RecurringSetupResponse(
                message=f"Recurring payment to {context.description}.\n\nHow much each time?",
                context=context,
            )

        except (ValueError, TypeError):
            return RecurringSetupResponse(
                message="❌ Invalid selection. Please enter the number.",
                context=context,
                error="Invalid input",
            )

    def _handle_amount_entry(
        self, user_id: str, message: str, context: RecurringSetupContext
    ) -> RecurringSetupResponse:
        """Handle amount input."""

        try:
            amount = float(message)

            if amount <= 0:
                return RecurringSetupResponse(
                    message="❌ Amount must be positive. Please enter again:",
                    context=context,
                    error="Invalid amount",
                )

            # Check recurring limit
            settings = (
                self.db.query(PaymentSettings)
                .filter(PaymentSettings.user_id == user_id)
                .first()
            )

            if settings and amount > settings.recurring_payment_max:
                return RecurringSetupResponse(
                    message=f"❌ Amount exceeds recurring limit (₹{settings.recurring_payment_max}). Please enter less.",
                    context=context,
                    error="Amount exceeds limit",
                )

            context.amount = amount
            context.state = RecurringSetupState.SELECTING_FREQUENCY

            return RecurringSetupResponse(
                message="How often should this payment repeat?",
                context=context,
                options=[
                    {"label": "Daily", "value": "daily"},
                    {"label": "Weekly (on a specific day)", "value": "weekly"},
                    {"label": "Monthly (on a specific date)", "value": "monthly"},
                    {"label": "Quarterly (every 3 months)", "value": "quarterly"},
                ],
            )

        except (ValueError, TypeError):
            return RecurringSetupResponse(
                message="❌ Invalid amount. Please enter a number.",
                context=context,
                error="Invalid input",
            )

    def _handle_frequency_selection(
        self, user_id: str, message: str, context: RecurringSetupContext
    ) -> RecurringSetupResponse:
        """Handle frequency selection."""

        if message.lower() not in ["daily", "weekly", "monthly", "quarterly"]:
            return RecurringSetupResponse(
                message="❌ Invalid frequency. Please select one.",
                context=context,
                error="Invalid input",
            )

        context.frequency = message.lower()

        if context.frequency == "daily":
            # No config needed for daily
            context.state = RecurringSetupState.ENTERING_START_DATE
            return RecurringSetupResponse(
                message="Great! Daily recurring payments.\n\nStart date? (YYYY-MM-DD or press enter for today)",
                context=context,
            )

        # Need frequency config
        context.state = RecurringSetupState.ENTERING_FREQUENCY_CONFIG

        if context.frequency == "weekly":
            return RecurringSetupResponse(
                message="Which day of week?",
                context=context,
                options=[
                    {"label": "Monday", "value": "monday"},
                    {"label": "Tuesday", "value": "tuesday"},
                    {"label": "Wednesday", "value": "wednesday"},
                    {"label": "Thursday", "value": "thursday"},
                    {"label": "Friday", "value": "friday"},
                    {"label": "Saturday", "value": "saturday"},
                    {"label": "Sunday", "value": "sunday"},
                ],
            )

        elif context.frequency == "monthly" or context.frequency == "quarterly":
            return RecurringSetupResponse(
                message="Which date of the month? (1-31)",
                context=context,
            )

    def _handle_frequency_config(
        self, user_id: str, message: str, context: RecurringSetupContext
    ) -> RecurringSetupResponse:
        """Handle frequency configuration (day of week/month)."""

        if context.frequency == "weekly":
            if message.lower() not in [
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            ]:
                return RecurringSetupResponse(
                    message="❌ Invalid day. Please select one.",
                    context=context,
                    error="Invalid input",
                )
            context.day_of_week = message.lower()

        elif context.frequency in ["monthly", "quarterly"]:
            try:
                day = int(message)
                if day < 1 or day > 31:
                    return RecurringSetupResponse(
                        message="❌ Date must be between 1 and 31. Please enter again:",
                        context=context,
                        error="Invalid input",
                    )
                context.day_of_month = day
            except (ValueError, TypeError):
                return RecurringSetupResponse(
                    message="❌ Invalid date. Please enter a number (1-31).",
                    context=context,
                    error="Invalid input",
                )

        context.state = RecurringSetupState.ENTERING_START_DATE
        return RecurringSetupResponse(
            message="Start date? (YYYY-MM-DD or press enter for today)",
            context=context,
        )

    def _handle_start_date(
        self, user_id: str, message: str, context: RecurringSetupContext
    ) -> RecurringSetupResponse:
        """Handle start date input."""

        if message.strip() == "":
            context.start_date = None  # Will default to today
        else:
            try:
                context.start_date = date.fromisoformat(message.strip())
            except ValueError:
                return RecurringSetupResponse(
                    message="❌ Invalid date format. Please use YYYY-MM-DD.",
                    context=context,
                    error="Invalid input",
                )

        context.state = RecurringSetupState.ENTERING_END_DATE
        return RecurringSetupResponse(
            message="End date? (YYYY-MM-DD or leave blank for never-ending)",
            context=context,
        )

    def _handle_end_date(
        self, user_id: str, message: str, context: RecurringSetupContext
    ) -> RecurringSetupResponse:
        """Handle end date input."""

        if message.strip() == "":
            context.end_date = None  # Never-ending
        else:
            try:
                context.end_date = date.fromisoformat(message.strip())
            except ValueError:
                return RecurringSetupResponse(
                    message="❌ Invalid date format. Please use YYYY-MM-DD.",
                    context=context,
                    error="Invalid input",
                )

        context.state = RecurringSetupState.ASKING_APPROVAL
        return RecurringSetupResponse(
            message="Require approval/confirmation for each payment? (yes/no)",
            context=context,
            options=[
                {"label": "Yes, require approval", "value": "yes"},
                {"label": "No, auto-execute", "value": "no"},
            ],
        )

    def _handle_approval(
        self, user_id: str, message: str, context: RecurringSetupContext
    ) -> RecurringSetupResponse:
        """Handle approval requirement."""

        if message.lower() in ["yes", "y"]:
            context.requires_approval = True
        elif message.lower() in ["no", "n"]:
            context.requires_approval = False
        else:
            return RecurringSetupResponse(
                message="❌ Please answer yes or no.",
                context=context,
                error="Invalid input",
            )

        context.state = RecurringSetupState.CONFIRMING
        return self._generate_confirmation(context)

    def _generate_confirmation(
        self, context: RecurringSetupContext
    ) -> RecurringSetupResponse:
        """Generate confirmation message."""

        # Format frequency display
        if context.frequency == "daily":
            freq_str = "Daily"
        elif context.frequency == "weekly":
            freq_str = f"Weekly on {context.day_of_week.capitalize()}"
        elif context.frequency == "monthly":
            freq_str = f"Monthly on the {context.day_of_month}th"
        elif context.frequency == "quarterly":
            freq_str = f"Quarterly on the {context.day_of_month}th"
        else:
            freq_str = context.frequency

        # Format dates
        start_str = str(context.start_date) if context.start_date else "Today"
        end_str = str(context.end_date) if context.end_date else "Never-ending"

        # Format approval
        approval_str = "Required" if context.requires_approval else "Auto-execute"

        confirmation = (
            f"Please confirm:\n"
            f"Beneficiary: {context.description}\n"
            f"Amount: ₹{context.amount:,.0f}\n"
            f"Frequency: {freq_str}\n"
            f"Starts: {start_str}\n"
            f"Ends: {end_str}\n"
            f"Approval: {approval_str}"
        )

        return RecurringSetupResponse(
            message=confirmation,
            context=context,
            options=[
                {"label": "✅ Confirm setup", "value": "yes"},
                {"label": "❌ Cancel", "value": "no"},
            ],
        )

    def _handle_confirmation(
        self, user_id: str, message: str, context: RecurringSetupContext
    ) -> RecurringSetupResponse:
        """Handle final confirmation."""

        if message.lower() == "no":
            context.state = RecurringSetupState.FAILED
            return RecurringSetupResponse(
                message="❌ Setup cancelled. Start over?",
                context=context,
            )

        if message.lower() != "yes":
            return RecurringSetupResponse(
                message="Please confirm (yes/no).",
                context=context,
            )

        # Create recurring payment rule
        try:
            payload = RecurringPaymentCreate(
                beneficiary_id=context.beneficiary_id,
                amount=context.amount,
                description=context.description or "Recurring payment",
                frequency=context.frequency,
                day_config={
                    "day_of_month": context.day_of_month,
                    "day_of_week": context.day_of_week,
                },
                start_date=context.start_date,
                end_date=context.end_date,
                requires_approval=context.requires_approval,
            )

            rule = create_recurring_payment_rule(self.db, user_id, payload)

            context.rule_id = rule.id
            context.state = RecurringSetupState.COMPLETE

            return RecurringSetupResponse(
                message=f"✅ Recurring payment set up successfully!\n\n"
                f"Rule ID: {rule.id}\n"
                f"First payment: {rule.next_run_date}\n"
                f"Frequency: {context.frequency}",
                context=context,
            )

        except Exception as exc:
            logger.error(f"Failed to create recurring rule: {exc}", exc_info=True)
            context.error_message = str(exc)
            context.state = RecurringSetupState.FAILED
            return RecurringSetupResponse(
                message=f"❌ Failed to set up: {str(exc)}",
                context=context,
                error=str(exc),
            )

    def close(self) -> None:
        """Close DB session."""
        if self.db:
            self.db.close()


def create_recurring_setup_agent() -> RecurringPaymentAgent:
    """Factory function to create recurring setup agent."""
    return RecurringPaymentAgent()
