from __future__ import annotations

from app.core.database import SessionLocal
from app.models.user import User


class _BootstrapBankingClient:
    async def create_profile(self, user_id: str, balance: float = 25000.0) -> dict:
        return {"user_id": user_id, "current_balance": balance}


def _clear_admin_users() -> None:
    db = SessionLocal()
    try:
        db.query(User).filter(User.role == "admin").delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_bootstrap_super_admin_allows_first_admin(client, monkeypatch):
    _clear_admin_users()
    monkeypatch.setattr(
        "app.routes.auth.get_banking_client",
        lambda: _BootstrapBankingClient(),
    )

    response = client.post(
        "/api/auth/bootstrap-super-admin",
        json={
            "email": "superadmin@example.com",
            "password": "Password123!",
            "full_name": "Super Admin",
            "phone_number": "9876543210",
        },
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["role"] == "admin"
    assert data["full_name"] == "Super Admin"

    login_response = client.post(
        "/api/auth/login",
        json={"email": "superadmin@example.com", "password": "Password123!"},
    )
    assert login_response.status_code == 200, login_response.text
    login_data = login_response.json()
    assert login_data["role"] == "admin"

    admin_response = client.get(
        "/api/admin/llm/tunnel/development",
        headers={"Authorization": f"Bearer {login_data['access_token']}"},
    )
    assert admin_response.status_code == 200, admin_response.text


def test_bootstrap_super_admin_is_one_time_only(client, monkeypatch):
    _clear_admin_users()
    monkeypatch.setattr(
        "app.routes.auth.get_banking_client",
        lambda: _BootstrapBankingClient(),
    )

    first_response = client.post(
        "/api/auth/bootstrap-super-admin",
        json={
            "email": "firstadmin@example.com",
            "password": "Password123!",
            "full_name": "First Admin",
        },
    )
    assert first_response.status_code == 201, first_response.text

    second_response = client.post(
        "/api/auth/bootstrap-super-admin",
        json={
            "email": "secondadmin@example.com",
            "password": "Password123!",
            "full_name": "Second Admin",
        },
    )

    assert second_response.status_code == 409, second_response.text
    assert second_response.json()["detail"] == "Super admin already exists"
