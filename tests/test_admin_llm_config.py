from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

from app.core.security import get_current_user, require_admin


class _FakeChatModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _override_admin_dependencies(app):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        user_id="admin-user-001",
    )
    app.dependency_overrides[require_admin] = lambda: None


def _clear_admin_dependencies(app):
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_admin, None)


def test_get_llm_provider_prefers_admin_gemini_config(monkeypatch):
    import app.services.llm as llm_module

    fake_module = ModuleType("langchain_google_genai")
    fake_module.ChatGoogleGenerativeAI = _FakeChatModel
    monkeypatch.setitem(sys.modules, "langchain_google_genai", fake_module)
    monkeypatch.setattr(
        llm_module,
        "_get_llm_config_from_db",
        lambda _environment: {
            "provider_type": "gemini",
            "model": "gemini-1.5-flash",
            "token": "gemini-secret",
            "tunnel_url": "",
        },
    )

    llm, provider = llm_module.get_llm_provider(
        temperature=0.2,
        max_tokens=256,
        environment="development",
    )

    assert provider == "gemini:gemini-1.5-flash"
    assert llm.kwargs["google_api_key"] == "gemini-secret"
    assert llm.kwargs["model"] == "gemini-1.5-flash"


def test_get_llm_provider_prefers_admin_ollama_config(monkeypatch):
    import app.services.llm as llm_module

    fake_module = ModuleType("langchain_ollama")
    fake_module.ChatOllama = _FakeChatModel
    monkeypatch.setitem(sys.modules, "langchain_ollama", fake_module)
    monkeypatch.setattr(llm_module, "_ollama_is_available", lambda _url: True)
    monkeypatch.setattr(llm_module, "_ollama_model_exists", lambda _url, _model: True)
    monkeypatch.setattr(
        llm_module,
        "_get_llm_config_from_db",
        lambda _environment: {
            "provider_type": "ollama",
            "model": "qwen3:8b",
            "token": None,
            "tunnel_url": "http://localhost:11434",
        },
    )

    llm, provider = llm_module.get_llm_provider(
        temperature=0.1,
        max_tokens=128,
        environment="development",
    )

    assert provider == "ollama:qwen3:8b"
    assert llm.kwargs["base_url"] == "http://localhost:11434"
    assert llm.kwargs["model"] == "qwen3:8b"


def test_get_llm_provider_falls_back_to_gemini_when_ollama_unavailable(monkeypatch):
    import app.services.llm as llm_module

    fake_module = ModuleType("langchain_google_genai")
    fake_module.ChatGoogleGenerativeAI = _FakeChatModel
    monkeypatch.setitem(sys.modules, "langchain_google_genai", fake_module)
    monkeypatch.setattr(llm_module, "_ollama_is_available", lambda _url: False)
    monkeypatch.setattr(llm_module, "_ollama_model_exists", lambda _url, _model: False)
    monkeypatch.setattr(
        llm_module,
        "get_settings",
        lambda: SimpleNamespace(
            environment="development",
            ollama_base_url="http://localhost:11434",
            ollama_model="qwen3:8b",
            ollama_auto_pull=False,
            gemini_api_key="gemini-secret",
            gemini_model="gemini-2.5-flash",
            openai_api_key="",
        ),
    )

    llm, provider = llm_module.get_llm_provider(temperature=0.1, max_tokens=128)

    assert provider == "gemini:gemini-2.5-flash"
    assert llm.kwargs["google_api_key"] == "gemini-secret"
    assert llm.kwargs["model"] == "gemini-2.5-flash"


def test_admin_llm_config_supports_gemini_provider(client):
    from app.main import app

    _override_admin_dependencies(app)
    try:
        response = client.put(
            "/api/admin/llm/tunnel/development",
            json={
                "provider_type": "gemini",
                "tunnel_url": "",
                "tunnel_auth_token": "gemini-secret",
                "ollama_model_default": "gemini-1.5-flash",
                "request_timeout_sec": 30,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["provider_type"] == "gemini"
        assert body["tunnel_auth_token_masked"]
        assert body["ollama_model_default"] == "gemini-1.5-flash"

        fetched = client.get("/api/admin/llm/tunnel/development")
        assert fetched.status_code == 200, fetched.text
        fetched_body = fetched.json()
        assert fetched_body["provider_type"] == "gemini"
        assert fetched_body["tunnel_auth_token_masked"]
    finally:
        _clear_admin_dependencies(app)
