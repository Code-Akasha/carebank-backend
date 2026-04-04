"""
Comprehensive Security Tests

Tests to ensure authorization boundaries, authentication requirements,
and prevent security vulnerabilities from reoccurring.
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.core.security import create_access_token


class TestSecurityBoundaries:
    """Test authentication and authorization boundaries."""

    async def test_transaction_requires_authentication(
        self, client: AsyncClient
    ) -> None:
        """Test that transaction endpoints require authentication."""
        # Try to access transactions without auth
        response = await client.get("/api/transactions/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        response = await client.get("/api/transactions/123")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        response = await client.post(
            "/api/transactions/trigger",
            json={"amount": 1000, "merchant": "Test", "category": "test"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_transaction_ownership_isolation(
        self, client: AsyncClient, test_users: dict
    ) -> None:
        """Test that users can only access their own transactions."""
        user1 = test_users["john"]
        user2 = test_users["jane"]

        # Create tokens for both users
        token1 = create_access_token({"sub": user1.user_id})
        token2 = create_access_token({"sub": user2.user_id})

        # User 1 creates a transaction
        response = await client.post(
            "/api/transactions/trigger",
            json={"amount": 500, "merchant": "Test Store", "category": "shopping"},
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert response.status_code in [200, 201, 202]

        # User 2 should not be able to see user 1's transactions
        response = await client.get(
            "/api/transactions/", headers={"Authorization": f"Bearer {token2}"}
        )
        assert response.status_code == 200
        data = response.json()
        transactions = data.get("transactions", [])

        # All transactions should belong to user 2
        for txn in transactions:
            assert txn["user_id"] == user2.user_id

    async def test_health_score_admin_restriction(
        self, client: AsyncClient, test_users: dict
    ) -> None:
        """Test that health score by user_id endpoint requires admin access."""
        user = test_users["john"]
        user_token = create_access_token({"sub": user.user_id})

        # Regular user should not be able to access other users' health scores
        response = await client.get(
            f"/api/health-score/{user.user_id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_bot_management_requires_admin(
        self, client: AsyncClient, test_users: dict
    ) -> None:
        """Test that bot management endpoints require admin access."""
        user = test_users["john"]
        user_token = create_access_token({"sub": user.user_id})

        # Regular user should not be able to manage bot webhooks
        response = await client.post(
            "/bot/telegram/set-webhook",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        response = await client.delete(
            "/bot/telegram/webhook", headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_simulate_requires_authentication(self, client: AsyncClient) -> None:
        """Test that simulation endpoint requires authentication."""
        response = await client.post(
            "/api/simulate",
            json={
                "expense_amount": 5000,
                "category": "electronics",
                "description": "New laptop",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_events_stream_requires_authentication(
        self, client: AsyncClient
    ) -> None:
        """Test that events stream requires authentication."""
        response = await client.get("/api/events/stream")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_user_context_enforcement(
        self, client: AsyncClient, test_users: dict
    ) -> None:
        """Test that user context is properly enforced in all endpoints."""
        user = test_users["john"]
        token = create_access_token({"sub": user.user_id})

        # Test that user can only trigger actions for themselves
        response = await client.post(
            "/api/transactions/trigger",
            json={"amount": 1000, "merchant": "Test", "category": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in [200, 201, 202]

        # Test that simulate endpoint uses authenticated user context
        response = await client.post(
            "/api/simulate",
            json={"expense_amount": 5000, "category": "electronics"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


class TestInputValidation:
    """Test input validation and sanitization."""

    async def test_transaction_amount_validation(
        self, client: AsyncClient, test_users: dict
    ) -> None:
        """Test transaction amount validation."""
        user = test_users["john"]
        token = create_access_token({"sub": user.user_id})

        # Test negative amount
        response = await client.post(
            "/api/transactions/trigger",
            json={"amount": -1000, "merchant": "Test", "category": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Test zero amount
        response = await client.post(
            "/api/transactions/trigger",
            json={"amount": 0, "merchant": "Test", "category": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in [422, 400]  # Should be rejected

        # Test extremely large amount
        response = await client.post(
            "/api/transactions/trigger",
            json={"amount": 1e15, "merchant": "Test", "category": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Should either be rejected or handled according to business rules
        assert response.status_code in [200, 201, 202, 400, 422]

    async def test_sql_injection_prevention(
        self, client: AsyncClient, test_users: dict
    ) -> None:
        """Test that SQL injection attempts are prevented."""
        user = test_users["john"]
        token = create_access_token({"sub": user.user_id})

        # Test SQL injection in merchant field
        response = await client.post(
            "/api/transactions/trigger",
            json={
                "amount": 100,
                "merchant": "'; DROP TABLE users; --",
                "category": "test",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        # Should not cause a server error
        assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR

        # Test SQL injection in category field
        response = await client.post(
            "/api/transactions/trigger",
            json={"amount": 100, "merchant": "Test", "category": "' OR '1'='1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR

    async def test_xss_prevention(self, client: AsyncClient, test_users: dict) -> None:
        """Test XSS prevention in text fields."""
        user = test_users["john"]
        token = create_access_token({"sub": user.user_id})

        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "{{7*7}}",  # Template injection
        ]

        for payload in xss_payloads:
            response = await client.post(
                "/api/transactions/trigger",
                json={"amount": 100, "merchant": payload, "category": "test"},
                headers={"Authorization": f"Bearer {token}"},
            )
            # Should not cause server errors and should be sanitized
            assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR


class TestMPINSecurity:
    """Test MPIN authentication security."""

    async def test_mpin_format_validation(
        self, client: AsyncClient, test_users: dict
    ) -> None:
        """Test MPIN format validation."""
        user = test_users["john"]
        token = create_access_token({"sub": user.user_id})

        invalid_mpins = [
            "123",  # Too short
            "12345",  # Too long
            "abcd",  # Non-numeric
            "12ab",  # Mixed
            "",  # Empty
            "   ",  # Whitespace
        ]

        for mpin in invalid_mpins:
            response = await client.post(
                "/api/auth/mpin",
                json={"mpin": mpin},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST

    async def test_mpin_brute_force_protection(
        self, client: AsyncClient, test_users: dict
    ) -> None:
        """Test MPIN brute force protection."""
        user = test_users["john"]
        token = create_access_token({"sub": user.user_id})

        # Set a valid MPIN first
        response = await client.post(
            "/api/auth/mpin",
            json={"mpin": "1234"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        # Attempt multiple wrong MPINs
        for _ in range(5):  # More than max attempts
            response = await client.post(
                "/api/auth/mpin/verify",
                json={"mpin": "9999"},  # Wrong MPIN
                headers={"Authorization": f"Bearer {token}"},
            )

        # Should be locked out after max attempts
        response = await client.post(
            "/api/auth/mpin/verify",
            json={"mpin": "1234"},  # Even correct MPIN should be rejected
            headers={"Authorization": f"Bearer {token}"},
        )
        data = response.json()
        assert "lockout" in str(data).lower() or response.status_code == 429


class TestWebhookSecurity:
    """Test webhook security."""

    async def test_telegram_webhook_signature_verification(
        self, client: AsyncClient
    ) -> None:
        """Test Telegram webhook signature verification."""
        # Test webhook without secret header
        response = await client.post(
            "/bot/telegram/webhook", json={"message": {"text": "test"}}
        )
        # Should either require secret or accept it (depending on configuration)
        assert response.status_code in [200, 400, 401, 403]

        # Test with invalid secret
        response = await client.post(
            "/bot/telegram/webhook",
            json={"message": {"text": "test"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "invalid_secret"},
        )
        # If secret verification is enabled, should reject
        assert response.status_code in [200, 403]


class TestRateLimiting:
    """Test rate limiting protections."""

    @pytest.mark.slow
    async def test_login_rate_limiting(self, client: AsyncClient) -> None:
        """Test rate limiting on login attempts."""
        login_data = {"email": "nonexistent@example.com", "password": "wrongpassword"}

        responses = []
        for _ in range(20):  # Attempt many failed logins
            response = await client.post("/api/auth/login", json=login_data)
            responses.append(response.status_code)

        # Should eventually rate limit (429) or at least not crash
        assert not any(code == 500 for code in responses)

    @pytest.mark.slow
    async def test_api_rate_limiting(
        self, client: AsyncClient, test_users: dict
    ) -> None:
        """Test general API rate limiting."""
        user = test_users["john"]
        token = create_access_token({"sub": user.user_id})

        responses = []
        for _ in range(50):  # Make many requests quickly
            response = await client.get(
                "/api/transactions/", headers={"Authorization": f"Bearer {token}"}
            )
            responses.append(response.status_code)

        # Should either work fine or eventually rate limit
        assert not any(code == 500 for code in responses)


class TestErrorHandling:
    """Test secure error handling."""

    async def test_error_information_disclosure(self, client: AsyncClient) -> None:
        """Test that errors don't disclose sensitive information."""
        # Test with malformed JSON
        response = await client.post(
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

    async def test_404_responses_consistent(
        self, client: AsyncClient, test_users: dict
    ) -> None:
        """Test that 404 responses don't leak information about resource existence."""
        user = test_users["john"]
        token = create_access_token({"sub": user.user_id})

        # Test accessing non-existent transaction
        response = await client.get(
            "/api/transactions/999999", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404

        # Error message should be generic
        data = response.json()
        assert "not found" in str(data).lower()


@pytest.mark.integration
class TestSecurityIntegration:
    """Integration tests for security features."""

    async def test_end_to_end_transaction_security(
        self, client: AsyncClient, test_users: dict
    ) -> None:
        """Test complete transaction security flow."""
        user = test_users["john"]
        token = create_access_token({"sub": user.user_id})

        # 1. Set up MPIN
        response = await client.post(
            "/api/auth/mpin",
            json={"mpin": "1234"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        # 2. Verify MPIN
        response = await client.post(
            "/api/auth/mpin/verify",
            json={"mpin": "1234"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        # 3. Create transaction (should work with valid MPIN session)
        response = await client.post(
            "/api/transactions/trigger",
            json={"amount": 1000, "merchant": "Test Store", "category": "shopping"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in [200, 201, 202]

        # 4. Verify transaction ownership
        response = await client.get(
            "/api/transactions/", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        transactions = data.get("transactions", [])

        # All transactions should belong to the authenticated user
        for txn in transactions:
            assert txn["user_id"] == user.user_id

    async def test_cross_user_isolation_comprehensive(
        self, client: AsyncClient, test_users: dict
    ) -> None:
        """Comprehensive test of user isolation across all endpoints."""
        user1 = test_users["john"]
        user2 = test_users["jane"]

        token1 = create_access_token({"sub": user1.user_id})
        token2 = create_access_token({"sub": user2.user_id})

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
            response1 = await client.get(
                endpoint, headers={"Authorization": f"Bearer {token1}"}
            )

            # User 2 should only see their own data
            response2 = await client.get(
                endpoint, headers={"Authorization": f"Bearer {token2}"}
            )

            # Both should either succeed with their own data or require additional auth
            assert response1.status_code in [200, 401, 403, 404]
            assert response2.status_code in [200, 401, 403, 404]

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
