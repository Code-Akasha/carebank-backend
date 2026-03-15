"""
Shared test fixtures and configuration for CareBank backend tests.
"""

import os
import pytest
from fastapi.testclient import TestClient


# ── Environment setup for CI ──────────────────────────────────────────
# Set test-safe defaults so tests don't require real services
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("BANKING_API_URL", "http://localhost:8001")
os.environ["BANKING_API_SECRET"] = "test-banking-secret-0123456789abcdef-long"
os.environ["JWT_SECRET"] = "test-jwt-secret-0123456789abcdef-long"
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Initialize the test database tables."""
    from app.core.database import init_db

    init_db()


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
