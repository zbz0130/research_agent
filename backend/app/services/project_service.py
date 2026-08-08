from app.schemas import Project, ProjectCreate
from app.storage import storage


class ProjectService:
    """Project repository facade backed by the shared SQLite store."""

    def list(self) -> list[Project]:
        return storage.list_projects()

    def create(self, payload: ProjectCreate) -> Project:
        project = Project(
            name=payload.name.strip(),
            research_question=payload.research_question.strip(),
        )
        return storage.save_project(project)

    def clear(self) -> None:
        storage.clear_projects()


project_service = ProjectService()
