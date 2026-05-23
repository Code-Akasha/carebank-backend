import uuid

import pytest

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.transaction import Transaction
from app.models.user import User
from app.services.telegram_bot import TelegramBot


def _register_user(client, *, role: str = "user") -> dict[str, str]:
    test_id = uuid.uuid4().hex[:8]
    email = f"security_{test_id}@example.com"
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": f"Security User {test_id}",
        },
    )
    assert response.status_code == 201
    data = response.json()

    if role != "user":
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.user_id == data["user_id"]).first()
            assert user is not None
            user.role = role
            db.commit()
        finally:
            db.close()

        login_response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "Password123!"},
        )
        assert login_response.status_code == 200
        data = login_response.json()

    return data


@pytest.fixture
def normal_user_auth(client) -> tuple[dict[str, str], dict[str, str]]:
    user = _register_user(client)
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    return user, headers


@pytest.fixture
def admin_auth(client) -> tuple[dict[str, str], dict[str, str]]:
    user = _register_user(client, role="admin")
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    return user, headers


def test_transaction_lookup_requires_ownership(client, normal_user_auth):
    owner, owner_headers = normal_user_auth
    other_user = _register_user(client)
    other_headers = {"Authorization": f"Bearer {other_user['access_token']}"}

    db = SessionLocal()
    try:
        txn = Transaction(
            id=900001,
            user_id=owner["user_id"],
            amount=123.45,
            merchant="Private Merchant",
            category="private",
            description="owner-only",
        )
        db.add(txn)
        db.commit()
    finally:
        db.close()

    owner_response = client.get("/api/transactions/900001", headers=owner_headers)
    assert owner_response.status_code == 200
    assert owner_response.json()["user_id"] == owner["user_id"]

    other_response = client.get("/api/transactions/900001", headers=other_headers)
    assert other_response.status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/transactions/123"),
        ("post", "/api/simulate"),
        ("get", "/api/events/stream"),
    ],
)
def test_sensitive_endpoints_require_auth(client, method, path):
    payload = {"expense_amount": 2500, "category": "travel", "description": "trip"}
    kwargs = {"json": payload} if method == "post" else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code in {401, 403}


def test_health_score_legacy_endpoint_requires_admin(client, normal_user_auth):
    _, headers = normal_user_auth
    response = client.get("/api/health-score/another-user", headers=headers)
    assert response.status_code == 403


def test_telegram_webhook_management_requires_admin(
    client, normal_user_auth, monkeypatch,
):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-test-token")
    get_settings.cache_clear()
    try:
        _, headers = normal_user_auth
        response = client.post("/bot/telegram/set-webhook", headers=headers)
        assert response.status_code == 403
    finally:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        get_settings.cache_clear()


def test_admin_can_manage_telegram_webhook(client, admin_auth, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-test-token")
    get_settings.cache_clear()

    async def _fake_set_webhook(self, url, *, secret_token=None):
        return {"ok": True, "url": url, "secret_token": secret_token}

    monkeypatch.setattr(TelegramBot, "set_webhook", _fake_set_webhook)

    try:
        _, headers = admin_auth
        response = client.post("/bot/telegram/set-webhook", headers=headers)
        assert response.status_code == 200
        assert response.json()["telegram_response"]["ok"] is True
    finally:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        get_settings.cache_clear()


def test_telegram_webhook_rejects_invalid_secret(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "expected-secret")
    get_settings.cache_clear()
    try:
        missing = client.post("/bot/telegram/webhook", json={})
        assert missing.status_code == 403

        wrong = client.post(
            "/bot/telegram/webhook",
            json={},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        )
        assert wrong.status_code == 403
    finally:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
        get_settings.cache_clear()


def test_whatsapp_webhook_route_removed(client):
    response = client.post("/bot/whatsapp/webhook", json={})
    assert response.status_code == 404


def test_set_mpin_requires_auth(client):
    response = client.post(
        "/api/auth/mpin/set",
        json={"mpin": "1234", "confirm_mpin": "1234"},
    )
    assert response.status_code in {401, 403}


def test_set_mpin_for_authenticated_user(client, normal_user_auth):
    _, headers = normal_user_auth
    response = client.post(
        "/api/auth/mpin/set",
        json={"mpin": "1234", "confirm_mpin": "1234"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["mpin_set"] is True
