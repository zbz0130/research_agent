from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings, get_settings
from app.main import app


client = TestClient(app)


def test_arxiv_paper_search_is_ready_without_a_credential() -> None:
    settings = Settings(paper_provider="arxiv", paper_api_key=None, _env_file=None)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = client.get("/api/v1/settings/api-keys")
        assert response.status_code == 200
        slots = {slot["id"]: slot for slot in response.json()["slots"]}
        assert slots["paper_search"]["provider"] == "arxiv"
        assert slots["paper_search"]["configured"] is False
        assert slots["paper_search"]["credential_required"] is False
    finally:
        app.dependency_overrides.clear()


def test_multi_source_paper_search_is_ready_without_a_credential() -> None:
    settings = Settings(paper_provider="multi_source", paper_api_key=None, _env_file=None)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = client.post("/api/v1/settings/providers/paper_search/test", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["provider"] == "multi_source"
        assert body["ok"] is True
        assert "OpenAlex" in body["message"]
    finally:
        app.dependency_overrides.clear()


def test_runtime_api_key_update_is_masked_and_separated() -> None:
    settings = Settings(
        paper_provider="semantic_scholar",
        explanation_provider="openai",
        experiment_provider="remote_runner",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = client.patch(
            "/api/v1/settings/api-keys",
            json={
                "paper_search": "paper-secret-1234",
                "explanation_model": "explanation-secret-5678",
                "experiment_runner": "runner-secret-9012",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["storage"] == "runtime_memory"
        slots = {slot["id"]: slot for slot in body["slots"]}
        assert slots["paper_search"]["configured"] is True
        assert slots["paper_search"]["masked"] == "••••••••1234"
        assert slots["explanation_model"]["masked"] == "••••••••5678"
        assert slots["experiment_runner"]["masked"] == "••••••••9012"
        assert "paper-secret-1234" not in response.text
        assert "explanation-secret-5678" not in response.text
        assert "runner-secret-9012" not in response.text

        cleared = client.patch(
            "/api/v1/settings/api-keys",
            json={"paper_search": ""},
        )
        assert cleared.status_code == 200
        cleared_slots = {slot["id"]: slot for slot in cleared.json()["slots"]}
        assert cleared_slots["paper_search"]["configured"] is False
        assert cleared_slots["experiment_runner"]["configured"] is True
    finally:
        app.dependency_overrides.clear()


def test_runtime_api_key_update_requires_a_slot() -> None:
    response = client.patch("/api/v1/settings/api-keys", json={})
    assert response.status_code == 422


def test_invalid_runtime_api_key_request_does_not_echo_secret() -> None:
    secret = "x" * 501
    response = client.patch(
        "/api/v1/settings/api-keys",
        json={"paper_search": secret},
    )
    assert response.status_code == 422
    assert secret not in response.text


def test_runtime_model_proxy_settings_are_non_secret_and_process_local() -> None:
    settings = Settings(
        explanation_provider="openai",
        explanation_model="gpt-4.1-mini",
        explanation_base_url="https://api.openai.com/v1",
        explanation_api_key=SecretStr("model-secret-1234"),
        demo_mode=True,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        initial = client.get("/api/v1/settings/runtime")
        assert initial.status_code == 200
        assert initial.json()["explanation_base_url"] == "https://api.openai.com/v1"
        assert initial.json()["storage"] == "environment"

        response = client.patch(
            "/api/v1/settings/runtime",
            json={
                "explanation_provider": "openai_compatible",
                "explanation_model": "qwen-plus",
                "explanation_base_url": "https://proxy.example.test/v1/",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["explanation_provider"] == "openai_compatible"
        assert body["explanation_model"] == "qwen-plus"
        assert body["explanation_base_url"] == "https://proxy.example.test/v1"
        assert body["storage"] == "runtime_memory"
        assert settings.explanation_base_url == "https://proxy.example.test/v1"
        assert "model-secret-1234" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_runtime_model_proxy_settings_reject_invalid_base_url() -> None:
    response = client.patch(
        "/api/v1/settings/runtime",
        json={"explanation_base_url": "proxy.example.test/v1"},
    )
    assert response.status_code == 422


def test_generic_provider_slots_are_returned_without_secrets() -> None:
    settings = Settings(
        _env_file=None,
        paper_provider="semantic_scholar",
        paper_base_url="https://papers.example.test/graph/v1",
        paper_model="search-v2",
        paper_enabled=True,
        community_provider="demo",
        explanation_provider="openai_compatible",
        explanation_model="qwen-plus",
        explanation_base_url="https://llm.example.test/v1/",
        experiment_provider="remote_runner",
        experiment_base_url="https://runner.example.test/api",
        experiment_model="runner-v1",
        experiment_enabled=False,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = client.get("/api/v1/settings/runtime")
        assert response.status_code == 200
        body = response.json()
        slots = {slot["id"]: slot for slot in body["slots"]}
        assert slots["paper_search"] == {
            "id": "paper_search",
            "label": "论文检索",
            "provider": "semantic_scholar",
            "base_url": "https://papers.example.test/graph/v1",
            "model": "search-v2",
            "enabled": True,
            "credential_required": True,
            "credential_configured": False,
            "storage": "environment",
        }
        assert slots["explanation_model"]["base_url"] == "https://llm.example.test/v1"
        assert slots["experiment_runner"]["enabled"] is False
        assert "api_key" not in response.text.lower()
    finally:
        app.dependency_overrides.clear()


def test_generic_provider_slot_patch_and_connection_status_are_safe() -> None:
    settings = Settings(_env_file=None, explanation_provider="rule_based")
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = client.patch(
            "/api/v1/settings/providers/explanation_model",
            json={
                "provider": "openai_compatible",
                "model": "qwen-plus",
                "base_url": "https://proxy.example.test/v1/",
                "enabled": True,
            },
        )
        assert response.status_code == 200
        slot = next(item for item in response.json()["slots"] if item["id"] == "explanation_model")
        assert slot["provider"] == "openai_compatible"
        assert slot["model"] == "qwen-plus"
        assert slot["base_url"] == "https://proxy.example.test/v1"
        assert slot["enabled"] is True

        missing = client.post(
            "/api/v1/settings/providers/explanation_model/test",
            json={},
        )
        assert missing.status_code == 200
        assert missing.json()["status"] == "missing_credential"
        assert missing.json()["ok"] is False

        disabled = client.patch(
            "/api/v1/settings/providers/explanation_model",
            json={"enabled": False},
        )
        assert disabled.status_code == 200
        status = client.post(
            "/api/v1/settings/providers/explanation_model/test",
            json={"probe": True},
        )
        assert status.status_code == 200
        assert status.json()["status"] == "disabled"
        assert "proxy.example.test" not in status.text
    finally:
        app.dependency_overrides.clear()


def test_generic_provider_slot_rejects_query_and_unknown_slot() -> None:
    invalid = client.patch(
        "/api/v1/settings/providers/paper_search",
        json={"base_url": "https://proxy.example.test/v1?token=secret"},
    )
    assert invalid.status_code == 422
    assert "secret" not in invalid.text

    unknown = client.patch(
        "/api/v1/settings/providers/not_a_slot",
        json={"enabled": True},
    )
    assert unknown.status_code == 422
