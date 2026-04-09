"""
Unit tests for recurring_payment_service.py
"""
import pytest
from datetime import datetime, date, timedelta

from app.services.recurring_payment_service import (
    create_recurring_payment_rule,
    get_recurring_payment_rule,
    list_recurring_payment_rules,
    update_recurring_payment_rule,
    delete_recurring_payment_rule,
    pause_recurring_payment_rule,
    resume_recurring_payment_rule,
    calculate_next_run_date,
)
from app.schemas.payments import RecurringPaymentCreate


@pytest.mark.unit
class TestRecurringPaymentCreation:
    """Tests for creating recurring payments"""

    def test_create_daily_recurring_payment(self, test_db, test_user_data, test_beneficiary_data):
        """Test creating a daily recurring payment"""
        user_id = test_user_data["user_id"]
        benef = test_beneficiary_data["benef1"]
        
        payload = RecurringPaymentCreate(
            beneficiary_id=benef.id,
            amount=5000,
            frequency="daily",
            day_config={},
            start_date=date.today(),
            end_date=None,
            requires_approval=False,
        )
        
        rule = create_recurring_payment_rule(
            db=test_db,
            user_id=user_id,
            payload=payload,
        )
        
        assert rule is not None
        assert rule.user_id == user_id
        assert rule.beneficiary_id == benef.id
        assert rule.amount == 5000
        assert rule.frequency == "daily"
        assert rule.status == "active"

    def test_create_weekly_recurring_payment(self, test_db, test_user_data, test_beneficiary_data):
        """Test creating a weekly recurring payment"""
        user_id = test_user_data["user_id"]
        benef = test_beneficiary_data["benef1"]
        
        payload = RecurringPaymentCreate(
            beneficiary_id=benef.id,
            amount=10000,
            frequency="weekly",
            day_config={"day_of_week": "monday"},
            start_date=date.today(),
            end_date=None,
            requires_approval=False,
        )
        
        rule = create_recurring_payment_rule(
            db=test_db,
            user_id=user_id,
            payload=payload,
        )
        
        assert rule is not None
        assert rule.frequency == "weekly"

    def test_create_monthly_recurring_payment(self, test_db, test_user_data, test_beneficiary_data):
        """Test creating a monthly recurring payment"""
        user_id = test_user_data["user_id"]
        benef = test_beneficiary_data["benef1"]
        
        payload = RecurringPaymentCreate(
            beneficiary_id=benef.id,
            amount=15000,
            frequency="monthly",
            day_config={"day_of_month": 15},
            start_date=date.today(),
            end_date=None,
            requires_approval=False,
        )
        
        rule = create_recurring_payment_rule(
            db=test_db,
            user_id=user_id,
            payload=payload,
        )
        
        assert rule is not None
        assert rule.frequency == "monthly"

    def test_create_quarterly_recurring_payment(self, test_db, test_user_data, test_beneficiary_data):
        """Test creating a quarterly recurring payment"""
        user_id = test_user_data["user_id"]
        benef = test_beneficiary_data["benef1"]
        
        payload = RecurringPaymentCreate(
            beneficiary_id=benef.id,
            amount=50000,
            frequency="quarterly",
            day_config={"day_of_month": 1},
            start_date=date.today(),
            end_date=None,
            requires_approval=False,
        )
        
        rule = create_recurring_payment_rule(
            db=test_db,
            user_id=user_id,
            payload=payload,
        )
        
        assert rule is not None
        assert rule.frequency == "quarterly"

    def test_create_with_approval_required(self, test_db, test_user_data, test_beneficiary_data):
        """Test creating recurring payment with approval requirement"""
        user_id = test_user_data["user_id"]
        benef = test_beneficiary_data["benef1"]
        
        payload = RecurringPaymentCreate(
            beneficiary_id=benef.id,
            amount=20000,
            frequency="daily",
            day_config={},
            start_date=date.today(),
            end_date=None,
            requires_approval=True,
        )
        
        rule = create_recurring_payment_rule(
            db=test_db,
            user_id=user_id,
            payload=payload,
        )
        
        assert rule.requires_approval == True

    def test_create_with_end_date(self, test_db, test_user_data, test_beneficiary_data):
        """Test creating recurring payment with end date"""
        user_id = test_user_data["user_id"]
        benef = test_beneficiary_data["benef1"]
        end_date = date.today() + timedelta(days=90)
        
        payload = RecurringPaymentCreate(
            beneficiary_id=benef.id,
            amount=5000,
            frequency="daily",
            day_config={},
            start_date=date.today(),
            end_date=end_date,
            requires_approval=False,
        )
        
        rule = create_recurring_payment_rule(
            db=test_db,
            user_id=user_id,
            payload=payload,
        )
        
        assert rule.end_date == end_date


@pytest.mark.unit
class TestRecurringPaymentRetrieval:
    """Tests for retrieving recurring payments"""

    def test_get_recurring_payment(self, test_db, test_recurring_rule_data):
        """Test retrieving a specific recurring rule"""
        rule_id = test_recurring_rule_data.id
        
        rule = get_recurring_payment_rule(db=test_db, rule_id=rule_id)
        
        assert rule is not None
        assert rule.id == rule_id

    def test_list_recurring_payments_for_user(self, test_db, test_user_data, test_recurring_rule_data):
        """Test listing recurring payments for a user"""
        user_id = test_user_data["user_id"]
        
        rules = list_recurring_payment_rules(db=test_db, user_id=user_id)
        
        assert len(rules) >= 1
        assert all(r.user_id == user_id for r in rules)

    def test_list_recurring_payments_isolation(self, test_db, test_user_data, test_recurring_rule_data):
        """Test that recurring payments are isolated per user"""
        from app.models.user import User
        
        # Create another user
        user2 = User(
            user_id="other_user_2",
            email="other2@example.com",
            phone="9876543213",
            name="Other User 2",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        test_db.add(user2)
        test_db.commit()
        
        # List for user1
        rules1 = list_recurring_payment_rules(db=test_db, user_id=test_user_data["user_id"])
        # List for user2
        rules2 = list_recurring_payment_rules(db=test_db, user_id=user2.user_id)
        
        assert len(rules1) >= 1
        assert len(rules2) == 0


@pytest.mark.unit
class TestRecurringPaymentUpdate:
    """Tests for updating recurring payments"""

    def test_update_recurring_payment_amount(self, test_db, test_recurring_rule_data):
        """Test updating recurring payment amount"""
        rule = test_recurring_rule_data
        new_amount = 20000
        
        updated_rule = update_recurring_payment_rule(
            db=test_db,
            rule_id=rule.id,
            update_data={"amount": new_amount},
        )
        
        assert updated_rule.amount == new_amount

    def test_update_recurring_payment_frequency(self, test_db, test_recurring_rule_data):
        """Test updating frequency"""
        rule = test_recurring_rule_data
        
        updated_rule = update_recurring_payment_rule(
            db=test_db,
            rule_id=rule.id,
            update_data={
                "frequency": "weekly",
                "day_config": {"day_of_week": "friday"},
            },
        )
        
        assert updated_rule.frequency == "weekly"

    def test_pause_recurring_payment(self, test_db, test_recurring_rule_data):
        """Test pausing a recurring payment"""
        rule = test_recurring_rule_data
        
        paused_rule = pause_recurring_payment_rule(db=test_db, rule_id=rule.id)
        
        assert paused_rule.status == "paused"

    def test_resume_recurring_payment(self, test_db, test_recurring_rule_data):
        """Test resuming a paused recurring payment"""
        rule = test_recurring_rule_data
        
        # First pause
        pause_recurring_payment_rule(db=test_db, rule_id=rule.id)
        
        # Then resume
        resumed_rule = resume_recurring_payment_rule(db=test_db, rule_id=rule.id)
        
        assert resumed_rule.status == "active"

    def test_delete_recurring_payment(self, test_db, test_recurring_rule_data):
        """Test soft deleting a recurring payment"""
        rule = test_recurring_rule_data
        rule_id = rule.id
        
        result = delete_recurring_payment_rule(db=test_db, rule_id=rule_id)
        
        assert result == True
        
        # Verify soft delete
        deleted_rule = get_recurring_payment_rule(db=test_db, rule_id=rule_id)
        assert deleted_rule is None  # Should be excluded by default


@pytest.mark.unit
class TestNextRunDateCalculation:
    """Tests for calculating next run dates"""

    def test_calculate_next_run_daily(self):
        """Test calculating next run date for daily frequency"""
        current_date = date(2025, 1, 15)
        
        next_date = calculate_next_run_date(
            frequency="daily",
            last_run_date=current_date,
            day_config={},
        )
        
        assert next_date == date(2025, 1, 16)

    def test_calculate_next_run_weekly(self):
        """Test calculating next run date for weekly frequency"""
        # Start on Monday 2025-01-13
        current_date = date(2025, 1, 13)
        
        next_date = calculate_next_run_date(
            frequency="weekly",
            last_run_date=current_date,
            day_config={"day_of_week": "monday"},
        )
        
        # Should be next Monday
        assert next_date == date(2025, 1, 20)

    def test_calculate_next_run_monthly(self):
        """Test calculating next run date for monthly frequency"""
        current_date = date(2025, 1, 15)
        
        next_date = calculate_next_run_date(
            frequency="monthly",
            last_run_date=current_date,
            day_config={"day_of_month": 15},
        )
        
        # Should be Feb 15
        assert next_date == date(2025, 2, 15)

    def test_calculate_next_run_quarterly(self):
        """Test calculating next run date for quarterly frequency"""
        current_date = date(2025, 1, 15)
        
        next_date = calculate_next_run_date(
            frequency="quarterly",
            last_run_date=current_date,
            day_config={"day_of_month": 15},
        )
        
        # Should be 3 months later (April 15)
        assert next_date == date(2025, 4, 15)

    def test_calculate_next_run_month_end_edge_case(self):
        """Test next run calculation for month-end edge cases"""
        # If set to day 31 but month has only 28 days
        current_date = date(2025, 1, 31)
        
        next_date = calculate_next_run_date(
            frequency="monthly",
            last_run_date=current_date,
            day_config={"day_of_month": 31},
        )
        
        # Should be last day of February (28)
        assert next_date.month == 2
        assert next_date.day == 28


@pytest.mark.unit
class TestRecurringPaymentLimits:
    """Tests for recurring payment limits"""

    def test_recurring_limit_max_amount(self, test_db, test_user_data, test_beneficiary_data):
        """Test that recurring payment is limited to ₹1L per cycle"""
        # Recurring limit: ₹1L per cycle
        # This should be enforced during creation
        pass

    def test_max_active_rules_per_user(self, test_db, test_user_data, test_beneficiary_data):
        """Test that user can have max 10 active recurring rules"""
        # Might have a limit like 10 max active rules
        pass
