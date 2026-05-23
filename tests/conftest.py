"""Shared test fixtures and configuration for CareBank backend tests.
"""

import atexit
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

# ── Environment setup for CI ──────────────────────────────────────────
# Set test-safe defaults so tests don't require real services.
# Use a per-run sqlite file to avoid WinError 32 when another process
# keeps a handle to a previous test.db.
_TEST_DB_PATH = Path(f"./test_{os.getpid()}_{uuid4().hex}.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB_PATH.as_posix()}")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ["OPENAI_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["OLLAMA_BASE_URL"] = ""
os.environ.setdefault("BANKING_API_URL", "http://localhost:8001")
os.environ["BANKING_API_SECRET"] = "test-banking-secret-0123456789abcdef-long"
os.environ["JWT_SECRET"] = "test-jwt-secret-0123456789abcdef-long"
os.environ["DB_SCHEMA_MODE"] = "create_all"
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Initialize the test database tables."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "", 1)
        if db_path and os.path.exists(db_path):
            try:
                os.remove(db_path)
            except PermissionError:
                # On Windows, another process may temporarily hold a stale file handle.
                # Continue with the current file; init_db/create_all still works.
                pass

    from app.core.database import engine, init_db

    init_db()
    yield
    engine.dispose()

    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "", 1)
        if db_path and os.path.exists(db_path):
            try:
                os.remove(db_path)
            except PermissionError:
                pass


@atexit.register
def _cleanup_test_db_file() -> None:
    try:
        if _TEST_DB_PATH.exists():
            _TEST_DB_PATH.unlink()
    except Exception:
        pass


@pytest.fixture
def client():
    """FastAPI test client for integration tests."""
    from app.main import app

    return TestClient(app)


@pytest.fixture
def sample_user():
    """Sample user data for testing."""
    return {
        "user_id": "test_user_001",
        "credit_score": 750,
        "balance": 5000,
    }


@pytest.fixture
def sample_transactions():
    """Sample transaction data for testing."""
    return [
        {"date": "2025-01-15", "amount": -50.00, "category": "food"},
        {"date": "2025-01-16", "amount": -120.00, "category": "utilities"},
        {"date": "2025-01-17", "amount": 3000.00, "category": "salary"},
        {"date": "2025-01-18", "amount": -30.00, "category": "transport"},
        {"date": "2025-01-19", "amount": -200.00, "category": "shopping"},
    ]


# ── Payment System Fixtures ──────────────────────────────────────────


@pytest.fixture
def test_db(client):
    """Get database session from app"""
    from app.core.database import SessionLocal

    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def test_user_data(test_db):
    """Create a test user with payment settings"""
    import uuid
    from datetime import datetime

    from app.models.payment_settings import PaymentSettings
    from app.models.user import User

    # Generate unique email to avoid UNIQUE constraint violations
    unique_id = str(uuid.uuid4())[:8]
    user = User(
        user_id=f"test_user_{unique_id}",
        email=f"test_{unique_id}@example.com",
        phone_number="9876543210",
        full_name="Test User",
        password_hash="$2b$12$dummy_hash",
        role="user",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    test_db.add(user)
    test_db.commit()

    # Create payment settings
    settings = PaymentSettings(
        user_id=user.user_id,
        mpin_hash="$2b$12$abcdefghijklmnopqrstuvwxyz",  # Dummy hash for testing
        mpin_threshold=50000,
        daily_limit=1000000,
        recurring_payment_max=100000,
        max_active_recurring_rules=10,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    test_db.add(settings)
    test_db.commit()

    return {"user_id": user.user_id, "user": user, "settings": settings}


@pytest.fixture
def test_user_2(test_db):
    """Create a second test user for isolation testing"""
    import uuid
    from datetime import datetime

    from app.models.payment_settings import PaymentSettings
    from app.models.user import User

    # Generate unique email to avoid UNIQUE constraint violations
    unique_id = str(uuid.uuid4())[:8]
    user = User(
        user_id=f"test_user_2_{unique_id}",
        email=f"test2_{unique_id}@example.com",
        phone_number="9876543212",
        full_name="Test User 2",
        password_hash="$2b$12$dummy_hash",
        role="user",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    test_db.add(user)
    test_db.commit()

    # Create payment settings
    settings = PaymentSettings(
        user_id=user.user_id,
        mpin_hash="$2b$12$abcdefghijklmnopqrstuvwxyz",
        mpin_threshold=50000,
        daily_limit=1000000,
        recurring_payment_max=100000,
        max_active_recurring_rules=10,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    test_db.add(settings)
    test_db.commit()

    return user


@pytest.fixture
def test_beneficiary_data(test_db, test_user_data):
    """Create test beneficiaries"""
    from datetime import datetime

    from app.models.beneficiary import Beneficiary

    benef1 = Beneficiary(
        user_id=test_user_data["user_id"],
        nickname="Mom",
        identifier_type="phone",
        identifier_value="9876543211",
        is_verified=True,
        verification_method="otp",
        is_trusted=True,
        category="family",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    benef2 = Beneficiary(
        user_id=test_user_data["user_id"],
        nickname="Dad",
        identifier_type="account_number",
        identifier_value="123456789012",
        is_verified=False,
        is_trusted=False,
        category="family",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    test_db.add_all([benef1, benef2])
    test_db.commit()

    return {"benef1": benef1, "benef2": benef2}


@pytest.fixture
def test_payment_settings(test_db, test_user_data):
    """Get or return test user's payment settings"""
    return test_user_data["settings"]


@pytest.fixture
def test_recurring_rule_data(test_db, test_user_data, test_beneficiary_data):
    """Create a test recurring payment rule"""
    from datetime import date, datetime

    from app.models.recurring_payment_rule import RecurringPaymentRule

    rule = RecurringPaymentRule(
        user_id=test_user_data["user_id"],
        beneficiary_id=test_beneficiary_data["benef1"].id,
        amount=10000,
        frequency="daily",
        day_config={},
        start_date=date.today(),
        end_date=None,
        requires_approval=False,
        status="active",
        total_executions=0,
        last_executed_at=None,
        last_execution_status=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    test_db.add(rule)
    test_db.commit()

    return rule


# Pytest custom markers
def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line("markers", "unit: unit tests")
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "e2e: end-to-end tests")
    config.addinivalue_line("markers", "slow: slow tests")
