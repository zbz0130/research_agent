from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class ApiKeySlot(BaseModel):
    """Public, non-secret view of one provider credential slot."""

    id: Literal["paper_search", "community_search", "explanation_model", "experiment_runner"]
    label: str
    provider: str
    configured: bool
    credential_required: bool = True
    masked: str | None = None
    environment_variable: str


class ApiKeyStatusResponse(BaseModel):
    slots: list[ApiKeySlot]
    storage: Literal["environment", "runtime_memory"] = "environment"


class ApiKeyUpdate(BaseModel):
    """Update one or more provider credentials for the current process.

    Values are accepted only on input and are never returned by the API.  A
    blank string explicitly clears a slot; an omitted field leaves it alone.
    The first version keeps these values in memory so a local demo does not
    write secrets into SQLite or the browser's persistent storage.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    paper_search: str | None = Field(default=None, max_length=500)
    community_search: str | None = Field(default=None, max_length=500)
    explanation_model: str | None = Field(default=None, max_length=500)
    experiment_runner: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_at_least_one_slot(self) -> "ApiKeyUpdate":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("至少需要提供一个 API Key 槽位")
        return self


class ProjectCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    research_question: str = Field(min_length=1, max_length=2000)


class Project(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    research_question: str
    status: Literal["draft", "planning", "running", "completed"] = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
