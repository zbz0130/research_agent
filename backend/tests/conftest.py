import pytest

from app.services.project_service import project_service


@pytest.fixture(autouse=True)
def reset_in_memory_store() -> None:
    project_service.clear()
    yield
    project_service.clear()
