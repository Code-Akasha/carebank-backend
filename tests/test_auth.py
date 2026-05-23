"""Integration tests for the CareBank Auth API."""

import uuid


def test_register_user(client):
    test_id = uuid.uuid4().hex[:8]
    email = f"testauth_{test_id}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Test Auth User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["full_name"] == "Test Auth User"


def test_login_user(client):
    test_id = uuid.uuid4().hex[:8]
    email = f"testauth_{test_id}@example.com"
    # First register
    client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Test Auth User 2",
        },
    )

    # Then login
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "user"


def test_get_me(client):
    test_id = uuid.uuid4().hex[:8]
    email = f"testauth_{test_id}@example.com"
    # First register and get token
    reg_response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Test Auth User 3",
        },
    )
    token = reg_response.json()["access_token"]

    # Then fetch me
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == email
    assert data["full_name"] == "Test Auth User 3"
    assert data["role"] == "user"
