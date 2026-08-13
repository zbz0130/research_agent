from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse
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


class RuntimeProviderSettings(BaseModel):
    """Non-secret provider settings used by the current API process."""

    explanation_provider: str
    explanation_model: str
    explanation_base_url: str
    demo_mode: bool
    storage: Literal["environment", "runtime_memory"] = "environment"
    # The legacy explanation_* fields above remain for clients from the first
    # release.  ``slots`` is the canonical, purpose-separated view used by
    # the desktop settings screen.
    slots: list["ProviderRuntimeSlot"] = Field(default_factory=list)


ProviderSlotId = Literal[
    "paper_search",
    "community_search",
    "explanation_model",
    "experiment_runner",
]


class ProviderRuntimeSlot(BaseModel):
    """Public non-secret configuration for one provider responsibility."""

    id: ProviderSlotId
    label: str
    provider: str
    base_url: str | None = None
    model: str | None = None
    enabled: bool = True
    credential_required: bool = True
    credential_configured: bool = False
    storage: Literal["environment", "runtime_memory"] = "environment"


class ProviderRuntimeSlotUpdate(BaseModel):
    """Patch one provider slot without accepting credentials."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None

    @model_validator(mode="after")
    def validate_values(self) -> "ProviderRuntimeSlotUpdate":
        values = self.model_dump(exclude_unset=True)
        if not values:
            raise ValueError("至少需要提供一个 Provider 设置")
        if "base_url" in values and values["base_url"]:
            parsed = urlparse(values["base_url"])
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Base URL 必须是完整的 http:// 或 https:// 地址")
            if parsed.query or parsed.fragment:
                raise ValueError("Base URL 不应包含 query 或 fragment")
        return self


class ProviderConnectionTestRequest(BaseModel):
    """Optional bounded network probe for a provider connection."""

    model_config = ConfigDict(extra="forbid")

    probe: bool = False


class ProviderConnectionTestResponse(BaseModel):
    slot: ProviderSlotId
    provider: str
    enabled: bool
    ok: bool
    status: Literal[
        "ready",
        "disabled",
        "missing_credential",
        "unsupported",
        "reachable",
        "unreachable",
        "invalid_configuration",
    ]
    message: str
    latency_ms: int | None = None


class RuntimeProviderSettingsUpdate(BaseModel):
    """Update the model endpoint without accepting or returning credentials."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    explanation_provider: Literal["openai", "openai_compatible", "rule_based"] | None = None
    explanation_model: str | None = Field(default=None, min_length=1, max_length=200)
    explanation_base_url: str | None = Field(default=None, max_length=500)
    demo_mode: bool | None = None

    @model_validator(mode="after")
    def validate_endpoint(self) -> "RuntimeProviderSettingsUpdate":
        values = self.model_dump(exclude_unset=True)
        if not values:
            raise ValueError("至少需要提供一个运行时 Provider 设置")
        if any(value is None for value in values.values()):
            raise ValueError("运行时 Provider 设置不能为 null")
        if "explanation_base_url" in values:
            value = values["explanation_base_url"]
            if value == "":
                raise ValueError("解释模型代理 Base URL 不能为空；如需规则解释，请将 Provider 设为 rule_based")
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("解释模型代理 Base URL 必须是完整的 http:// 或 https:// 地址")
            if parsed.query or parsed.fragment:
                raise ValueError("解释模型代理 Base URL 不应包含 query 或 fragment")
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
