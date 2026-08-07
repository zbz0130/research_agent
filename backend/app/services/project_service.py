from uuid import UUID

from app.schemas import Project, ProjectCreate


class ProjectService:
    """Temporary in-memory service.

    Persistence is intentionally deferred to a later stage so the first review
    can focus on the API/UI boundary and the domain model.
    """

    def __init__(self) -> None:
        self._projects: dict[UUID, Project] = {}

    def list(self) -> list[Project]:
        return sorted(self._projects.values(), key=lambda project: project.created_at, reverse=True)

    def create(self, payload: ProjectCreate) -> Project:
        project = Project(
            name=payload.name.strip(),
            research_question=payload.research_question.strip(),
        )
        self._projects[project.id] = project
        return project

    def clear(self) -> None:
        self._projects.clear()


project_service = ProjectService()
