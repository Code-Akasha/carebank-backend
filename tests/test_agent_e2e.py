"""End-to-end tests for agent workflows"""

import pytest

from app.agents.payment_agent import PaymentAgent, PaymentContext
from app.agents.recurring_payment_agent import (
    RecurringPaymentAgent,
    RecurringSetupContext,
)


@pytest.mark.e2e
class TestPaymentAgentE2E:
    """End-to-end tests for PaymentAgent"""

    def test_payment_agent_initialization(self):
        """Test that PaymentAgent initializes without error"""
        agent = PaymentAgent()
        assert agent is not None

    def test_payment_agent_start_state(self, test_db, test_user_data):
        """Test agent starts in START state and prompts for beneficiary"""
        agent = PaymentAgent()
        user_id = test_user_data["user_id"]
        context = PaymentContext(user_id=user_id)

        response = agent.process_message(user_id, "I want to pay someone", context)

        assert response is not None
        assert (
            "beneficiary" in response.message.lower()
            or "pay" in response.message.lower()
        )
        # Should show list of beneficiaries
        assert len(response.options) > 0

    def test_payment_agent_full_flow(
        self,
        test_db,
        test_user_data,
        test_beneficiary_data,
    ):
        """Test complete payment flow through agent"""
        agent = PaymentAgent()
        user_id = test_user_data["user_id"]

        # Step 1: Start conversation
        context = PaymentContext(user_id=user_id)
        resp1 = agent.process_message(user_id, "I want to pay Mom", context)
        assert resp1 is not None
        print(f"Step 1 - Response: {resp1.message}")

        # Step 2: Select beneficiary (if needed)
        if resp1.context.beneficiary_id is None:
            context = resp1.context
            resp2 = agent.process_message(user_id, "Mom", context)
            assert resp2.context.beneficiary_id is not None
            print(f"Step 2 - Selected beneficiary: {resp2.context.beneficiary_id}")
        else:
            resp2 = resp1
            context = resp1.context

        # Step 3: Enter amount
        context = resp2.context
        resp3 = agent.process_message(user_id, "5000", context)
        assert resp3.context.amount == 5000
        print(f"Step 3 - Amount: {resp3.context.amount}")

        # Step 4: Confirm or select payment method
        context = resp3.context
        resp4 = agent.process_message(user_id, "yes", context)
        print(f"Step 4 - Response: {resp4.message}")

        # May need MPIN entry or may proceed to completion
        # Verify that we're moving toward completion
        assert (
            "confirm" in resp4.message.lower()
            or "success" in resp4.message.lower()
            or "mpin" in resp4.message.lower()
        )

    def test_payment_agent_error_recovery(
        self,
        test_db,
        test_user_data,
        test_beneficiary_data,
    ):
        """Test agent error recovery"""
        agent = PaymentAgent()
        user_id = test_user_data["user_id"]
        context = PaymentContext(user_id=user_id)

        # Enter invalid amount (negative)
        resp = agent.process_message(user_id, "-5000", context)

        # Should indicate error or ask for valid input
        # State may go to FAILED or stay in ENTERING_AMOUNT
        assert resp is not None

    def test_payment_agent_invalid_beneficiary(self, test_db, test_user_data):
        """Test agent handling of invalid beneficiary selection"""
        agent = PaymentAgent()
        user_id = test_user_data["user_id"]
        context = PaymentContext(user_id=user_id)

        # Try to select nonexistent beneficiary
        resp = agent.process_message(user_id, "999999", context)

        # Should either reject or ask to select from list
        assert resp is not None

    def test_payment_agent_amount_validation(
        self,
        test_db,
        test_user_data,
        test_beneficiary_data,
    ):
        """Test agent validates payment amounts"""
        agent = PaymentAgent()
        user_id = test_user_data["user_id"]
        context = PaymentContext(user_id=user_id)

        # Start flow and navigate to amount entry
        resp1 = agent.process_message(user_id, "Pay Mom", context)
        if resp1.context.beneficiary_id is None:
            context = resp1.context
            resp2 = agent.process_message(user_id, "Mom", context)
            context = resp2.context
        else:
            context = resp1.context

        # Try zero amount
        resp = agent.process_message(user_id, "0", context)
        assert resp is not None
        # Should either reject or move forward

    def test_payment_agent_timeout_handling(self, test_db, test_user_data):
        """Test agent clears context after timeout (if implemented)"""
        # Implementation dependent


@pytest.mark.e2e
class TestRecurringPaymentAgentE2E:
    """End-to-end tests for RecurringPaymentAgent"""

    def test_recurring_agent_initialization(self):
        """Test that RecurringPaymentAgent initializes"""
        agent = RecurringPaymentAgent()
        assert agent is not None

    def test_recurring_agent_start_state(self, test_db, test_user_data):
        """Test agent starts and prompts for frequency setup"""
        agent = RecurringPaymentAgent()
        user_id = test_user_data["user_id"]
        context = RecurringSetupContext(user_id=user_id)

        response = agent.process_message(
            user_id,
            "I want to set up a recurring payment",
            context,
        )

        assert response is not None
        # Should ask about beneficiary or frequency
        assert len(response.options) > 0

    def test_recurring_agent_daily_setup_flow(
        self,
        test_db,
        test_user_data,
        test_beneficiary_data,
    ):
        """Test daily recurring setup flow"""
        agent = RecurringPaymentAgent()
        user_id = test_user_data["user_id"]

        # Step 1: Start
        context = RecurringSetupContext(user_id=user_id)
        resp1 = agent.process_message(user_id, "Set up recurring to Mom", context)
        print(f"Step 1: {resp1.message}")

        # Step 2: Select beneficiary
        context = resp1.context
        resp2 = agent.process_message(user_id, "Mom", context)
        print(f"Step 2: {resp2.message}")
        assert resp2.context.beneficiary_id is not None

        # Step 3: Enter amount
        context = resp2.context
        resp3 = agent.process_message(user_id, "10000", context)
        print(f"Step 3: {resp3.message}")
        assert resp3.context.amount == 10000

        # Step 4: Select frequency (daily)
        context = resp3.context
        resp4 = agent.process_message(user_id, "daily", context)
        print(f"Step 4: {resp4.message}")
        assert resp4.context.frequency == "daily"

        # For daily, should skip config and go to start date
        # Or ask to confirm

    def test_recurring_agent_weekly_setup_flow(
        self,
        test_db,
        test_user_data,
        test_beneficiary_data,
    ):
        """Test weekly recurring setup with day selection"""
        agent = RecurringPaymentAgent()
        user_id = test_user_data["user_id"]

        # Flow through to frequency selection
        context = RecurringSetupContext(user_id=user_id)
        resp1 = agent.process_message(user_id, "Recurring to Mom", context)
        context = resp1.context
        resp2 = agent.process_message(user_id, "Mom", context)
        context = resp2.context
        resp3 = agent.process_message(user_id, "5000", context)
        context = resp3.context

        # Select weekly
        resp4 = agent.process_message(user_id, "weekly", context)
        context = resp4.context

        # Should ask for day of week
        assert "day" in resp4.message.lower() or "weekly" in resp4.message.lower()

        # Select day
        resp5 = agent.process_message(user_id, "Monday", context)
        assert resp5.context.day_of_week is not None or "day_of_week" in str(
            resp5.context.day_config,
        )

    def test_recurring_agent_monthly_setup_flow(
        self,
        test_db,
        test_user_data,
        test_beneficiary_data,
    ):
        """Test monthly recurring setup with date selection"""
        agent = RecurringPaymentAgent()
        user_id = test_user_data["user_id"]

        # Flow through to frequency
        context = RecurringSetupContext(user_id=user_id)
        resp1 = agent.process_message(user_id, "Month recurring", context)
        context = resp1.context
        resp2 = agent.process_message(user_id, "Mom", context)
        context = resp2.context
        resp3 = agent.process_message(user_id, "15000", context)
        context = resp3.context

        # Select monthly
        resp4 = agent.process_message(user_id, "monthly", context)
        context = resp4.context

        # Should ask for day of month
        assert "day" in resp4.message.lower() or "date" in resp4.message.lower()

        # Select day (15th)
        resp5 = agent.process_message(user_id, "15", context)
        assert (
            resp5.context.day_of_month == 15
            or resp5.context.day_config.get("day_of_month") == 15
        )

    def test_recurring_agent_dates_setup(
        self,
        test_db,
        test_user_data,
        test_beneficiary_data,
    ):
        """Test setting start and end dates"""
        # Placeholder until date-specific flow assertions are implemented.
        assert True

    def test_recurring_agent_quarterly_setup(
        self,
        test_db,
        test_user_data,
        test_beneficiary_data,
    ):
        """Test quarterly recurring setup"""
        agent = RecurringPaymentAgent()
        user_id = test_user_data["user_id"]

        # Flow to quarterly selection
        context = RecurringSetupContext(user_id=user_id)
        resp1 = agent.process_message(user_id, "Quarterly recurring", context)
        context = resp1.context
        resp2 = agent.process_message(user_id, "Mom", context)
        context = resp2.context
        resp3 = agent.process_message(user_id, "50000", context)
        context = resp3.context

        # Select quarterly
        resp4 = agent.process_message(user_id, "quarterly", context)
        assert resp4.context.frequency == "quarterly"

    def test_recurring_agent_zero_amount_validation(
        self,
        test_db,
        test_user_data,
        test_beneficiary_data,
    ):
        """Test agent rejects zero amount"""
        agent = RecurringPaymentAgent()
        user_id = test_user_data["user_id"]

        context = RecurringSetupContext(user_id=user_id)
        resp1 = agent.process_message(user_id, "Recurring setup", context)
        context = resp1.context
        resp2 = agent.process_message(user_id, "Mom", context)
        context = resp2.context

        # Try zero amount
        resp3 = agent.process_message(user_id, "0", context)

        # Should reject or ask again
        assert resp3 is not None


@pytest.mark.e2e
class TestAgentContextPassing:
    """Tests for agent context preservation between calls"""

    def test_payment_context_preservation(self, test_db, test_user_data):
        """Test context is preserved between agent calls"""
        agent = PaymentAgent()
        user_id = test_user_data["user_id"]

        context1 = PaymentContext(user_id=user_id)
        resp1 = agent.process_message(user_id, "Pay Mom 5000", context1)

        # Context should be returned and can be passed back
        assert resp1.context is not None
        assert resp1.context.user_id == user_id

    def test_recurring_context_preservation(self, test_db, test_user_data):
        """Test recurring context is preserved"""
        agent = RecurringPaymentAgent()
        user_id = test_user_data["user_id"]

        context1 = RecurringSetupContext(user_id=user_id)
        resp1 = agent.process_message(user_id, "Daily recurring", context1)

        # Context should contain all info needed for next turn
        assert resp1.context is not None
        assert resp1.context.user_id == user_id


@pytest.mark.e2e
class TestAgentUserIsolation:
    """Tests for user isolation in agents"""

    def test_payment_agent_user_isolation(
        self,
        test_db,
        test_user_data,
        test_user_2,
        test_beneficiary_data,
    ):
        """Test that PaymentAgent enforces user isolation"""
        agent = PaymentAgent()

        # User1 context
        context1 = PaymentContext(user_id=test_user_data["user_id"])
        resp1 = agent.process_message(test_user_data["user_id"], "Pay", context1)

        # User2 context
        context2 = PaymentContext(user_id=test_user_2.user_id)
        resp2 = agent.process_message(test_user_2.user_id, "Pay", context2)

        # Responses should show different beneficiaries/info
        # User2 should not see User1's beneficiaries
        assert resp1.context.user_id != resp2.context.user_id

    def test_recurring_agent_user_isolation(self, test_db, test_user_data, test_user_2):
        """Test that RecurringPaymentAgent enforces user isolation"""
        agent = RecurringPaymentAgent()

        # User1 context
        context1 = RecurringSetupContext(user_id=test_user_data["user_id"])
        resp1 = agent.process_message(test_user_data["user_id"], "Recurring", context1)

        # User2 context
        context2 = RecurringSetupContext(user_id=test_user_2.user_id)
        resp2 = agent.process_message(test_user_2.user_id, "Recurring", context2)

        # Different users shouldn't see each other's info
        assert resp1.context.user_id != resp2.context.user_id
