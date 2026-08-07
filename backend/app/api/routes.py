from fastapi import APIRouter, Depends, status

from app.config import Settings, get_settings
from app.schemas import HealthResponse, Project, ProjectCreate
from app.services.project_service import project_service

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name, version=settings.version)


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
