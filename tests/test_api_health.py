"""Integration tests for the CareBank API health endpoint.
Verifies the FastAPI app starts and responds correctly.
"""


class TestHealthEndpoint:
    """Test the root health check endpoint."""

    def test_health_returns_200(self, client):
        """Should return 200 OK with running status."""
        # Act
        response = client.get("/")

        # Assert
        assert response.status_code == 200

    def test_health_returns_status_message(self, client):
        """Should return JSON with status field."""
        # Act
        response = client.get("/")
        data = response.json()

        # Assert
        assert "status" in data
        assert data["status"] == "CareBank Backend Running"
