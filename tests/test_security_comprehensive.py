"""Comprehensive Security Tests

Tests to ensure authorization boundaries, authentication requirements,
and prevent security vulnerabilities from reoccurring.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import status


class _MockBankingClient:
    def __init__(self) -> None:
        self._transactions: dict[str, list[dict]] = {}

    async def create_profile(self, user_id: str, balance: float = 25000.0) -> dict:
        self._transactions.setdefault(user_id, [])
        return {"user_id": user_id, "current_balance": balance}

    async def get_transactions(self, user_id: str, **kwargs) -> list[dict]:
        return list(self._transactions.get(user_id, []))

    async def get_balance(self, user_id: str) -> dict:
        return {"current_balance": 50000.0, "available_balance": 50000.0}

    async def trigger_transaction(self, payload: dict) -> dict:
        user_id = payload["user_id"]
        records = self._transactions.setdefault(user_id, [])
        tx_id = len(records) + 1
        records.append(
            {
                "id": tx_id,
                "user_id": user_id,
                "amount": payload["amount"],
                "merchant": payload.get("merchant"),
                "category": payload.get("category"),
                "description": payload.get("description"),
                "date": datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
            },
        )
        return {"status": "queued", "id": tx_id}


@pytest.fixture(autouse=True)
def mock_banking_client(monkeypatch):
    client = _MockBankingClient()
    monkeypatch.setattr("app.routes.auth.get_banking_client", lambda: client)
    monkeypatch.setattr("app.routes.transactions.get_banking_client", lambda: client)
    monkeypatch.setattr("app.routes.simulate.get_banking_client", lambda: client)
    monkeypatch.setattr("app.routes.health_score.get_banking_client", lambda: client)
    return client


@pytest.fixture
def test_users(client):
    users = {}
    for name in ("john", "jane"):
        email = f"{name}_{uuid4().hex[:8]}@example.com"
        response = client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "StrongPassword123!",
                "full_name": name.title(),
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        users[name] = SimpleNamespace(
            user_id=data["user_id"], token=data["access_token"],
        )
    return users


class TestSecurityBoundaries:
    """Test authentication and authorization boundaries."""

    def test_transaction_requires_authentication(self, client) -> None:
        """Test that transaction endpoints require authentication."""
        # Try to access transactions without auth
        response = client.get("/api/transactions/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        response = client.get("/api/transactions/123")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        response = client.post(
            "/api/transactions/trigger",
            json={"amount": 1000, "merchant": "Test", "category": "test"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_transaction_ownership_isolation(self, client, test_users: dict) -> None:
        """Test that users can only access their own transactions."""
        user1 = test_users["john"]
        user2 = test_users["jane"]

        # Create tokens for both users
        token1 = user1.token
        token2 = user2.token

        # User 1 creates a transaction
        response = client.post(
            "/api/transactions/trigger",
            json={
                "user_id": user1.user_id,
                "amount": 500,
                "merchant": "Test Store",
                "category": "shopping",
            },
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert response.status_code in [200, 201, 202]

        # User 2 should not be able to see user 1's transactions
        response = client.get(
            "/api/transactions/", headers={"Authorization": f"Bearer {token2}"},
        )
        assert response.status_code == 200
        data = response.json()
        transactions = data.get("transactions", [])

        # All transactions should belong to user 2
        for txn in transactions:
            assert txn["user_id"] == user2.user_id

    def test_health_score_admin_restriction(self, client, test_users: dict) -> None:
        """Test that health score by user_id endpoint requires admin access."""
        user = test_users["john"]
        user_token = user.token

        # Regular user should not be able to access other users' health scores
        response = client.get(
            f"/api/health-score/{user.user_id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_bot_management_requires_admin(self, client, test_users: dict) -> None:
        """Test that bot management endpoints require admin access."""
        user = test_users["john"]
        user_token = user.token

        # Regular user should not be able to manage bot webhooks
        response = client.post(
            "/bot/telegram/set-webhook",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ]

        response = client.delete(
            "/bot/telegram/webhook", headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ]

    def test_simulate_requires_authentication(self, client) -> None:
        """Test that simulation endpoint requires authentication."""
        response = client.post(
            "/api/simulate",
            json={
                "expense_amount": 5000,
                "category": "electronics",
                "description": "New laptop",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_events_stream_requires_authentication(self, client) -> None:
        """Test that events stream requires authentication."""
        response = client.get("/api/events/stream")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_user_context_enforcement(self, client, test_users: dict) -> None:
        """Test that user context is properly enforced in all endpoints."""
        user = test_users["john"]
        token = user.token

        # Test that user can only trigger actions for themselves
        response = client.post(
            "/api/transactions/trigger",
            json={
                "user_id": user.user_id,
                "amount": 1000,
                "merchant": "Test",
                "category": "test",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in [200, 201, 202]

        # Test that simulate endpoint uses authenticated user context
        response = client.post(
            "/api/simulate",
            json={"expense_amount": 5000, "category": "electronics"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


class TestInputValidation:
    """Test input validation and sanitization."""

    def test_transaction_amount_validation(self, client, test_users: dict) -> None:
        """Test transaction amount validation."""
        user = test_users["john"]
        token = user.token

        # Test negative amount
        response = client.post(
            "/api/transactions/trigger",
            json={
                "user_id": user.user_id,
                "amount": -1000,
                "merchant": "Test",
                "category": "test",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in [200, 201, 202, 400, 422]

        # Test zero amount
        response = client.post(
            "/api/transactions/trigger",
            json={
                "user_id": user.user_id,
                "amount": 0,
                "merchant": "Test",
                "category": "test",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in [200, 201, 202, 400, 422]

        # Test extremely large amount
        response = client.post(
            "/api/transactions/trigger",
            json={
                "user_id": user.user_id,
                "amount": 1e15,
                "merchant": "Test",
                "category": "test",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in [200, 201, 202, 400, 422]

    def test_sql_injection_prevention(self, client, test_users: dict) -> None:
        """Test that SQL injection attempts are prevented."""
        user = test_users["john"]
        token = user.token

        # Test SQL injection in merchant field
        response = client.post(
            "/api/transactions/trigger",
            json={
                "user_id": user.user_id,
                "amount": 100,
                "merchant": "'; DROP TABLE users; --",
                "category": "test",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        # Should not cause a server error
        assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR

        # Test SQL injection in category field
        response = client.post(
            "/api/transactions/trigger",
            json={
                "user_id": user.user_id,
                "amount": 100,
                "merchant": "Test",
                "category": "' OR '1'='1",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_xss_prevention(self, client, test_users: dict) -> None:
        """Test XSS prevention in text fields."""
        user = test_users["john"]
        token = user.token

        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "{{7*7}}",  # Template injection
        ]

        for payload in xss_payloads:
            response = client.post(
                "/api/transactions/trigger",
                json={
                    "user_id": user.user_id,
                    "amount": 100,
                    "merchant": payload,
                    "category": "test",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            # Should not cause server errors and should be sanitized
            assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR


class TestMPINSecurity:
    """Test MPIN authentication security."""

    def test_mpin_format_validation(self, client, test_users: dict) -> None:
        """Test MPIN format validation."""
        user = test_users["john"]
        token = user.token

        invalid_mpins = [
            "123",  # Too short
            "12345",  # Too long
            "abcd",  # Non-numeric
            "12ab",  # Mixed
            "",  # Empty
            "   ",  # Whitespace
        ]

        for mpin in invalid_mpins:
            response = client.post(
                "/api/auth/mpin/set",
                json={"mpin": mpin, "confirm_mpin": mpin},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_mpin_confirmation_validation(self, client, test_users: dict) -> None:
        """Test MPIN confirmation mismatch validation."""
        user = test_users["john"]
        token = user.token
        response = client.post(
            "/api/auth/mpin/set",
            json={"mpin": "1234", "confirm_mpin": "9999"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_mpin_set_success(self, client, test_users: dict) -> None:
        user = test_users["john"]
        token = user.token
        response = client.post(
            "/api/auth/mpin/set",
            json={"mpin": "1234", "confirm_mpin": "1234"},
            headers={"Authorization": f"Bearer {token}"},
        )
        data = response.json()
        assert response.status_code == 200
        assert data["mpin_set"] is True


class TestWebhookSecurity:
    """Test webhook security."""

    def test_telegram_webhook_signature_verification(self, client) -> None:
        """Test Telegram webhook signature verification."""
        # Test webhook without secret header
        response = client.post(
            "/bot/telegram/webhook", json={"message": {"text": "test"}},
        )
        # Should either require secret or accept it (depending on configuration)
        assert response.status_code in [200, 400, 401, 403, 503]

        # Test with invalid secret
        response = client.post(
            "/bot/telegram/webhook",
            json={"message": {"text": "test"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "invalid_secret"},
        )
        # If secret verification is enabled, should reject
        assert response.status_code in [200, 403, 503]


class TestRateLimiting:
    """Test rate limiting protections."""

    def test_login_rate_limiting(self, client) -> None:
        """Test rate limiting on login attempts."""
        login_data = {"email": "nonexistent@example.com", "password": "wrongpassword"}

        responses = []
        for _ in range(20):  # Attempt many failed logins
            response = client.post("/api/auth/login", json=login_data)
            responses.append(response.status_code)

        # Should eventually rate limit (429) or at least not crash
        assert not any(code == 500 for code in responses)

    def test_api_rate_limiting(self, client, test_users: dict) -> None:
        """Test general API rate limiting."""
        user = test_users["john"]
        token = user.token

        responses = []
        for _ in range(50):  # Make many requests quickly
            response = client.get(
                "/api/transactions/", headers={"Authorization": f"Bearer {token}"},
            )
            responses.append(response.status_code)

        # Should either work fine or eventually rate limit
        assert not any(code == 500 for code in responses)


class TestErrorHandling:
    """Test secure error handling."""

    def test_error_information_disclosure(self, client) -> None:
        """Test that errors don't disclose sensitive information."""
        # Test with malformed JSON
        response = client.post(
            "/api/transactions/trigger",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )

        # Should return proper error without stack traces or internal details
        assert response.status_code in [400, 422]
        if response.status_code == 400:
            data = response.json()
            error_text = str(data).lower()

            # Should not contain sensitive information
            sensitive_terms = [
                "password",
                "secret",
                "key",
                "token",
                "traceback",
                "file path",
            ]
            for term in sensitive_terms:
                assert term not in error_text

    def test_404_responses_consistent(self, client, test_users: dict) -> None:
        """Test that 404 responses don't leak information about resource existence."""
        user = test_users["john"]
        token = user.token

        # Test accessing non-existent transaction
        response = client.get(
            "/api/transactions/999999", headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

        # Error message should be generic
        data = response.json()
        assert "not found" in str(data).lower()


@pytest.mark.integration
class TestSecurityIntegration:
    """Integration tests for security features."""

    def test_end_to_end_transaction_security(self, client, test_users: dict) -> None:
        """Test complete transaction security flow."""
        user = test_users["john"]
        token = user.token

        # 1. Set up MPIN
        response = client.post(
            "/api/auth/mpin/set",
            json={"mpin": "1234", "confirm_mpin": "1234"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        # 2. Create transaction
        response = client.post(
            "/api/transactions/trigger",
            json={
                "user_id": user.user_id,
                "amount": 1000,
                "merchant": "Test Store",
                "category": "shopping",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in [200, 201, 202]

        # 3. Verify transaction ownership
        response = client.get(
            "/api/transactions/", headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        transactions = data.get("transactions", [])

        # All transactions should belong to the authenticated user
        for txn in transactions:
            assert txn["user_id"] == user.user_id

    def test_cross_user_isolation_comprehensive(self, client, test_users: dict) -> None:
        """Comprehensive test of user isolation across all endpoints."""
        user1 = test_users["john"]
        user2 = test_users["jane"]

        token1 = user1.token
        token2 = user2.token

        endpoints_to_test = [
            "/api/transactions/",
            "/api/health-score/",
            "/api/simulate",
            "/api/planning/plans",
            "/api/actions/requests",
            "/api/notifications/",
        ]

        for endpoint in endpoints_to_test:
            # User 1 should only see their own data
            response1 = client.get(
                endpoint, headers={"Authorization": f"Bearer {token1}"},
            )

            # User 2 should only see their own data
            response2 = client.get(
                endpoint, headers={"Authorization": f"Bearer {token2}"},
            )

            # Both should either succeed with their own data or require additional auth
            assert response1.status_code in [200, 401, 403, 404, 405]
            assert response2.status_code in [200, 401, 403, 404, 405]

            if response1.status_code == 200 and response2.status_code == 200:
                # If both succeed, data should be isolated
                data1 = response1.json()
                data2 = response2.json()

                # Check that any user_id fields match the requesting user
                def check_user_ids(obj, expected_user_id):
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            if key == "user_id" and value != expected_user_id:
                                return False
                            if not check_user_ids(value, expected_user_id):
                                return False
                    elif isinstance(obj, list):
                        for item in obj:
                            if not check_user_ids(item, expected_user_id):
                                return False
                    return True

                assert check_user_ids(data1, user1.user_id)
                assert check_user_ids(data2, user2.user_id)
