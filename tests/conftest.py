"""
Shared test fixtures and configuration for CareBank backend tests.
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
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("BANKING_API_URL", "http://localhost:8001")
os.environ["BANKING_API_SECRET"] = "test-banking-secret-0123456789abcdef-long"
os.environ["JWT_SECRET"] = "test-jwt-secret-0123456789abcdef-long"
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Initialize the test database tables."""
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
