from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_web_shell_is_served() -> None:
    page = client.get("/")
    stylesheet = client.get("/static/styles.css")

    assert page.status_code == 200
    assert "TraceLab" in page.text
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
