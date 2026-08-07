from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


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
