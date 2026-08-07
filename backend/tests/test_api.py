from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings, get_settings
from app.main import app
from app.services.settings_service import api_key_slots

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_web_shell_is_served() -> None:
    page = client.get("/")
    stylesheet = client.get("/static/styles.css")

    assert page.status_code == 200
    assert "WishForge" in page.text
    assert stylesheet.status_code == 200


def test_create_and_list_project() -> None:
    payload = {
        "name": "标签噪声下的 Mixup 鲁棒性",
        "research_question": "Mixup 是否能提升标签噪声下的分类性能？",
    }

    created = client.post("/api/v1/projects", json=payload)
    assert created.status_code == 201
    assert created.json()["status"] == "draft"

    projects = client.get("/api/v1/projects")
    assert projects.status_code == 200
    assert len(projects.json()) == 1
    assert projects.json()[0]["name"] == payload["name"]


def test_project_validation() -> None:
    response = client.post(
        "/api/v1/projects",
        json={"name": "", "research_question": ""},
    )

    assert response.status_code == 422


def test_api_key_status_is_separated_and_masked() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        paper_provider="semantic_scholar",
        explanation_provider="openai",
        experiment_provider="remote_runner",
        paper_api_key=SecretStr("paper-secret-1234"),
        experiment_api_key=SecretStr("run-secret-5678"),
    )

    try:
        response = client.get("/api/v1/settings/api-keys")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["storage"] == "environment"
    slots = {slot["id"]: slot for slot in response.json()["slots"]}
    assert slots["paper_search"]["configured"] is True
    assert slots["paper_search"]["masked"] == "••••••••1234"
    assert slots["experiment_runner"]["configured"] is True
    assert slots["experiment_runner"]["masked"] == "••••••••5678"
    assert slots["explanation_model"]["configured"] is False
    assert "paper-secret-1234" not in response.text
    assert "run-secret-5678" not in response.text


def test_settings_load_separate_environment_keys(monkeypatch) -> None:
    monkeypatch.setenv("WISHFORGE_PAPER_API_KEY", "paper-env-9999")
    monkeypatch.setenv("WISHFORGE_EXPERIMENT_API_KEY", "runner-env-8888")

    slots = {slot.id: slot for slot in api_key_slots(Settings())}

    assert slots["paper_search"].configured is True
    assert slots["paper_search"].masked == "••••••••9999"
    assert slots["experiment_runner"].configured is True
    assert slots["experiment_runner"].masked == "••••••••8888"
    assert slots["explanation_model"].configured is False
