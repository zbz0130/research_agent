from fastapi import APIRouter, Depends, status

from app.config import Settings, get_settings
from app.schemas import ApiKeyStatusResponse, HealthResponse, Project, ProjectCreate
from app.services.project_service import project_service
from app.services.settings_service import api_key_slots

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name, version=settings.version)


@router.get("/settings/api-keys", response_model=ApiKeyStatusResponse, tags=["settings"])
def api_key_status(settings: Settings = Depends(get_settings)) -> ApiKeyStatusResponse:
    """Expose configuration status without ever returning a raw API key."""

    return ApiKeyStatusResponse(slots=list(api_key_slots(settings)))


@router.get("/projects", response_model=list[Project], tags=["projects"])
def list_projects() -> list[Project]:
    return project_service.list()


@router.post(
    "/projects",
    response_model=Project,
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
)
def create_project(payload: ProjectCreate) -> Project:
    return project_service.create(payload)
