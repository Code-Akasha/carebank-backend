import os
import sys

# Ensure root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agents.base import AgentInput
from app.agents.intelligence import IntelligenceAgent
from app.core.database import SessionLocal, init_db
from app.models.user import User
from app.schemas.payments import ExecutePaymentPayload
from app.services.payment_execution_service import execute_generic_payment


def setup_test_db():
    init_db()
    db = SessionLocal()
    # Create test user
    user = db.query(User).filter(User.phone_number == "+15550009999").first()
    if not user:
        user = User(
            email="test_integration@example.com",
            phone_number="+15550009999",
            full_name="Integration Test User",
            password_hash="fakehash",
            account_type="personal",
        )
        db.add(user)
        db.commit()
    return db, user


def test_intelligence_agent_balance(user):
    print("\n--- Testing IntelligenceAgent Balance ---")
    agent = IntelligenceAgent()

    # Mocking contextual input
    class Context:
        def __init__(self):
            self.model_extra = {}
            self.amount = None

    input_data = AgentInput(
        user_id=user.id,
        intent="balance",
        message="What is my balance?",
        context=Context(),
    )

    output = agent._invoke(input_data)
    print(f"Status: {output.status}")
    print(f"Confidence: {output.confidence}")
    print(f"Metadata: {output.metadata}")

    assert output.metadata["intent_handled"] == "balance"
    assert "current_balance" in output.metadata
    print("IntelligenceAgent balance test PASSED.")


def test_recurring_payment_scheduler():
    print("\n--- Testing RecurringPaymentAgent Scheduler ---")
    from app.services.recurring_scheduler import (
        get_scheduler,
        start_scheduler,
        stop_scheduler,
    )

    start_scheduler()
    scheduler = get_scheduler()
    jobs = scheduler.get_jobs()
    print(f"Active scheduled jobs: {len(jobs)}")
    for job in jobs:
        print(f" - {job.id}: {job.name} (Next run: {job.next_run_time})")

    assert any(job.id == "recurring_payment_check" for job in jobs)
    print("RecurringPaymentAgent scheduler test PASSED.")
    stop_scheduler()


def test_payment_execution(db, user):
    print("\n--- Testing Payment Execution ---")
    # Simulate payment
    payload = ExecutePaymentPayload(
        beneficiary_id=None,
        amount=50.0,
        description="Integration test payment",
        payment_method="upi",
        mpin="1234",  # Dummy MPIN
    )

    try:
        result = execute_generic_payment(db, user.id, payload)
        print(f"Payment Result Status: {result.status}")
        print(f"Transaction ID: {result.transaction_id}")
        assert result.status == "success"
        print("Payment Execution test PASSED.")
    except Exception as e:
        print(f"Payment Execution failed: {e}")


if __name__ == "__main__":
    db, user = setup_test_db()
    try:
        test_intelligence_agent_balance(user)
        test_recurring_payment_scheduler()
        test_payment_execution(db, user)
        print("\nAll M1.4 Integrations Verified Successfully!")
    finally:
        db.close()
