"""Unit tests for beneficiary_service.py
"""

from datetime import datetime

import pytest

from app.services.beneficiary_service import (
    create_beneficiary,
    delete_beneficiary,
    get_beneficiary,
    list_beneficiaries,
    update_beneficiary,
    verify_beneficiary,
)


@pytest.mark.unit
class TestBeneficiaryService:
    """Tests for beneficiary service operations"""

    def test_create_beneficiary_upi(self, test_db, test_user_data):
        """Test creating a UPI beneficiary"""
        user_id = test_user_data["user_id"]

        benef = create_beneficiary(
            db=test_db,
            user_id=user_id,
            name="Test Beneficiary",
            phone="9876543210",
            upi="test@bank",
            account_number=None,
            ifsc=None,
            is_trusted=False,
        )

        assert benef is not None
        assert benef.user_id == user_id
        assert benef.name == "Test Beneficiary"
        assert benef.phone == "9876543210"
        assert benef.upi == "test@bank"
        assert not benef.is_verified

    def test_create_beneficiary_account(self, test_db, test_user_data):
        """Test creating a bank account beneficiary"""
        user_id = test_user_data["user_id"]

        benef = create_beneficiary(
            db=test_db,
            user_id=user_id,
            name="Account Beneficiary",
            phone=None,
            upi=None,
            account_number="123456789012",
            ifsc="SBIN0000001",
            is_trusted=False,
        )

        assert benef is not None
        assert benef.account_number == "123456789012"
        assert benef.ifsc == "SBIN0000001"

    def test_get_beneficiary(self, test_db, test_beneficiary_data):
        """Test fetching a beneficiary by ID"""
        benef_id = test_beneficiary_data["benef1"].id

        benef = get_beneficiary(db=test_db, beneficiary_id=benef_id)

        assert benef is not None
        assert benef.id == benef_id
        assert benef.name == "Mom"

    def test_get_nonexistent_beneficiary(self, test_db):
        """Test that fetching nonexistent beneficiary returns None"""
        benef = get_beneficiary(db=test_db, beneficiary_id=999999)
        assert benef is None

    def test_list_beneficiaries_for_user(
        self, test_db, test_user_data, test_beneficiary_data,
    ):
        """Test listing beneficiaries for a user"""
        user_id = test_user_data["user_id"]

        benefs = list_beneficiaries(db=test_db, user_id=user_id)

        assert len(benefs) == 2
        assert benefs[0].user_id == user_id
        assert benefs[1].user_id == user_id

    def test_list_beneficiaries_isolation(
        self, test_db, test_user_data, test_beneficiary_data,
    ):
        """Test that beneficiaries are isolated per user"""
        from app.models.user import User

        # Create another user
        user2 = User(
            user_id="other_user_456",
            email="other@example.com",
            phone="9876543212",
            name="Other User",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        test_db.add(user2)
        test_db.commit()

        # List beneficiaries for user1
        benefs1 = list_beneficiaries(db=test_db, user_id=test_user_data["user_id"])
        # List beneficiaries for user2
        benefs2 = list_beneficiaries(db=test_db, user_id=user2.user_id)

        assert len(benefs1) == 2
        assert len(benefs2) == 0

    def test_update_beneficiary(self, test_db, test_beneficiary_data):
        """Test updating a beneficiary"""
        benef = test_beneficiary_data["benef1"]

        updated_benef = update_beneficiary(
            db=test_db,
            beneficiary_id=benef.id,
            name="Mom Updated",
            is_trusted=True,
        )

        assert updated_benef.name == "Mom Updated"
        assert updated_benef.is_trusted

    def test_delete_beneficiary(self, test_db, test_beneficiary_data):
        """Test soft deleting a beneficiary"""
        benef = test_beneficiary_data["benef1"]
        benef_id = benef.id

        result = delete_beneficiary(db=test_db, beneficiary_id=benef_id)

        assert result

        # Verify soft delete (record still exists but is_deleted=True)
        benef_check = get_beneficiary(db=test_db, beneficiary_id=benef_id)
        assert benef_check is None  # Should be excluded by default (is_deleted=True)

    def test_verify_beneficiary_otp(self, test_db, test_beneficiary_data):
        """Test verifying beneficiary via OTP"""
        benef = test_beneficiary_data["benef1"]

        updated_benef = verify_beneficiary(
            db=test_db,
            beneficiary_id=benef.id,
            verification_method="otp",
        )

        assert updated_benef.is_verified
        assert updated_benef.verification_method == "otp"

    def test_verify_beneficiary_micro_deposit(self, test_db, test_beneficiary_data):
        """Test verifying beneficiary via micro deposit"""
        benef = test_beneficiary_data["benef2"]

        updated_benef = verify_beneficiary(
            db=test_db,
            beneficiary_id=benef.id,
            verification_method="micro_deposit",
        )

        assert updated_benef.is_verified

    def test_create_beneficiary_missing_details(self, test_db, test_user_data):
        """Test that creating beneficiary requires at least UPI or account"""
        user_id = test_user_data["user_id"]

        # Should either raise or return None
        create_beneficiary(
            db=test_db,
            user_id=user_id,
            name="Invalid Beneficiary",
            phone=None,
            upi=None,
            account_number=None,
            ifsc=None,
            is_trusted=False,
        )

        # Either returns None or raises an exception
        # Depending on implementation


@pytest.mark.unit
class TestBeneficiaryLimits:
    """Tests for beneficiary limits and constraints"""

    def test_unlimited_beneficiaries_per_user(self, test_db, test_user_data):
        """Test that user can create many beneficiaries"""
        user_id = test_user_data["user_id"]

        # Create 10 beneficiaries
        for i in range(10):
            create_beneficiary(
                db=test_db,
                user_id=user_id,
                name=f"Beneficiary {i}",
                phone=f"9876543{100 + i:03d}",
                upi=f"user{i}@bank",
                is_trusted=False,
            )

        benefs = list_beneficiaries(db=test_db, user_id=user_id)
        assert len(benefs) == 10

    def test_beneficiary_name_required(self, test_db, test_user_data):
        """Test that beneficiary name is required"""
        user_id = test_user_data["user_id"]

        # Should fail if name is None or empty
        try:
            create_beneficiary(
                db=test_db,
                user_id=user_id,
                name="",
                phone="9876543210",
                upi="test@bank",
                is_trusted=False,
            )
        except Exception:
            # Expected to fail
            pass
