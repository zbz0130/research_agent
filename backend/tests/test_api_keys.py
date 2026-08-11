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
