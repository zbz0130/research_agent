"""Contracts for the first, plan-only experiment workflow.

The research pipeline deliberately stops at a structured experiment draft in
this version of WishForge.  These models are kept in a separate module so the
draft can be integrated into an API, project storage, or a future execution
runner without changing the existing research contracts.

Nothing in this module represents a run or an observed result.  In
particular, :class:`ExperimentPlan` is a proposal that still requires human
review before any code, command, or external experiment is allowed to run.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import ClassVar, Literal
from uuid import UUID, uuid4
from urllib.parse import urlparse

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from app.research_schemas import IdeaCheckResult, InnovationCandidate


Confidence = Literal["high", "medium", "low"]
ApprovalStatus = Literal["draft", "needs_review", "approved", "rejected"]
ReviewStatus = Literal["draft", "needs_review", "approved", "rejected"]
VariableRole = Literal[
    "independent",
    "dependent",
    "moderator",
    "nuisance",
    "confounder",
]
ControlType = Literal[
    "constant",
    "randomization",
    "counterbalance",
    "dataset_split",
    "statistical",
    "eligibility",
]
MetricDirection = Literal["maximize", "minimize", "target", "monitor"]
AblationType = Literal["remove", "replace", "freeze", "shuffle", "scale"]
ProvenanceStatus = Literal["unverified", "partially_verified", "verified"]


def _http_url_or_none(value: str | None) -> str | None:
    """Validate optional provenance URLs without requiring one for all sources."""

    if value is None or value == "":
        return value
    parsed = urlparse(str(value))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("来源链接只允许 http 或 https")
    return str(value)


class EvidenceProvenance(BaseModel):
    """Trace where an experiment-plan statement came from.

    ``evidence`` and ``evidence_ids`` intentionally coexist as a compatibility
    bridge.  New callers can use the explicit ``evidence_ids`` field, while a
    UI or an integration that uses the shorter ``evidence`` spelling can still
    submit and inspect the same identifiers.  The service keeps both lists in
    sync and removes duplicates.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    source: str = Field(min_length=1, max_length=500)
    source_type: str = Field(default="user_input", min_length=1, max_length=100)
    source_id: str | None = Field(default=None, max_length=300)
    source_agent_run_id: str | None = Field(default=None, max_length=300)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    evidence: list[str] = Field(default_factory=list, max_length=100)
    excerpt: str | None = Field(default=None, max_length=5000)
    locator: str | None = Field(default=None, max_length=500)
    source_url: str | None = Field(default=None, max_length=2000)
    confidence: Confidence = "low"
    verification_status: ProvenanceStatus = "unverified"
    notes: str = Field(default="", max_length=2000)

    @field_validator("source_url", mode="before")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        return _http_url_or_none(value)

    @model_validator(mode="after")
    def merge_evidence_ids(self) -> "EvidenceProvenance":
        merged = list(dict.fromkeys([*self.evidence_ids, *self.evidence]))
        self.evidence_ids = merged
        self.evidence = merged.copy()
        return self


class ExperimentVariable(BaseModel):
    """One variable and the levels at which it should be evaluated."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    name: str = Field(min_length=1, max_length=200)
    role: VariableRole = "independent"
    description: str = Field(default="", max_length=2000)
    levels: list[str] = Field(default_factory=list, max_length=50)
    # ``values`` is a friendly spelling used by some clients.  The service
    # mirrors it to ``levels`` so both names are safe to use at the boundary.
    values: list[str] = Field(default_factory=list, max_length=50)
    unit: str | None = Field(default=None, max_length=100)
    measurement: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def merge_levels(self) -> "ExperimentVariable":
        merged = list(dict.fromkeys([*self.levels, *self.values]))
        self.levels = merged
        self.values = merged.copy()
        return self


class ExperimentControl(BaseModel):
    """A factor held fixed or balanced to reduce confounding."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    rationale: str = Field(default="", max_length=2000)
    control_type: ControlType = Field(
        default="constant",
        validation_alias=AliasChoices("control_type", "type"),
    )
    implementation: str | None = Field(default=None, max_length=2000)

    @property
    def type(self) -> ControlType:
        """Compatibility alias for clients that call this field ``type``."""

        return self.control_type


class ExperimentMetric(BaseModel):
    """A measurable outcome, including direction and collection protocol."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    direction: MetricDirection = "monitor"
    unit: str | None = Field(default=None, max_length=100)
    primary: bool = Field(default=False, validation_alias=AliasChoices("primary", "is_primary"))
    aggregation: str = Field(default="mean across runs", max_length=300)
    target: str | float | None = None
    measurement_protocol: str = Field(default="", max_length=2000)

    @property
    def is_primary(self) -> bool:
        """Compatibility alias for table-oriented clients."""

        return self.primary


class ExperimentAblation(BaseModel):
    """One component-removal or component-replacement comparison."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    component: str = Field(min_length=1, max_length=300)
    ablation_type: AblationType = Field(
        default="remove",
        validation_alias=AliasChoices("ablation_type", "type"),
    )
    variant: str = Field(default="removed", max_length=1000)
    rationale: str = Field(default="", max_length=2000)
    expected_effect: str = Field(default="", max_length=2000)
    metrics: list[str] = Field(default_factory=list, max_length=30)

    @property
    def type(self) -> AblationType:
        return self.ablation_type


class ExpectedOutcome(BaseModel):
    """A directional prediction, never an observed result."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    scenario: str = Field(min_length=1, max_length=300)
    prediction: str = Field(min_length=1, max_length=3000)
    metric: str | None = Field(default=None, max_length=200)
    threshold: str | float | None = None
    confidence: Confidence = "low"


class FailureCriterion(BaseModel):
    """A pre-registered condition that should stop or revise the study."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    condition: str = Field(min_length=1, max_length=3000)
    severity: Literal["warning", "major", "stop"] = "major"
    action: str = Field(default="暂停并人工复核", max_length=2000)
    metric: str | None = Field(default=None, max_length=200)


class ResourceEstimate(BaseModel):
    """Coarse budget information for planning; no resource is allocated here."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    compute: str = Field(default="本地 CPU 或单张 GPU", max_length=500)
    time_estimate_hours: float = Field(
        default=4.0,
        ge=0,
        le=100000,
        validation_alias=AliasChoices("time_estimate_hours", "wall_clock_hours", "time"),
    )
    gpu_hours: float = Field(default=0.0, ge=0, le=100000)
    memory_gb: float = Field(default=8.0, ge=0, le=100000)
    storage_gb: float = Field(default=5.0, ge=0, le=100000)
    budget_usd: float | None = Field(default=None, ge=0, le=100000000)
    personnel_hours: float = Field(default=2.0, ge=0, le=100000)
    data_requirements: str = Field(default="固定训练/验证/测试划分；记录数据版本", max_length=2000)
    notes: str = Field(default="先做小规模预实验，再扩大预算。", max_length=2000)

    @property
    def wall_clock_hours(self) -> float:
        return self.time_estimate_hours

    @property
    def estimated_wall_clock_hours(self) -> float:
        return self.time_estimate_hours

    @property
    def estimated_gpu_hours(self) -> float:
        return self.gpu_hours


class ExperimentPlanRequest(BaseModel):
    """Input accepted by :class:`~app.services.experiment_service.ExperimentService`.

    A caller may provide free text, an existing ``InnovationCandidate``, an
    ``IdeaCheckResult``, or a combination of those.  Optional lists are
    overrides for the deterministic defaults generated by the service.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    idea: str | None = Field(default=None, min_length=3, max_length=4000)
    candidate: InnovationCandidate | None = None
    idea_check: IdeaCheckResult | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    baseline: str | None = Field(default=None, min_length=1, max_length=2000)
    variables: list[ExperimentVariable] | None = Field(default=None, max_length=50)
    controls: list[ExperimentControl] | None = Field(default=None, max_length=50)
    metrics: list[ExperimentMetric] | None = Field(default=None, max_length=50)
    ablation: list[ExperimentAblation] | None = Field(default=None, max_length=50)
    expected_outcomes: list[ExpectedOutcome] | None = Field(default=None, max_length=50)
    failure_criteria: list[FailureCriterion] | None = Field(
        default=None,
        validation_alias=AliasChoices("failure_criteria", "risks"),
        max_length=50,
    )
    resource_estimate: ResourceEstimate | None = Field(
        default=None,
        validation_alias=AliasChoices("resource_estimate", "resources"),
    )
    validation_steps: list[str] | None = Field(default=None, max_length=50)
    provenance: list[EvidenceProvenance] = Field(default_factory=list, max_length=100)
    project_id: UUID | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_compatibility_aliases(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        if "resource_estimate" in data:
            data.pop("resources", None)
        elif "resources" in data:
            data["resource_estimate"] = data.pop("resources")
        if "failure_criteria" in data:
            data.pop("risks", None)
        elif "risks" in data:
            data["failure_criteria"] = data.pop("risks")
        return data

    @model_validator(mode="after")
    def require_source(self) -> "ExperimentPlanRequest":
        if not self.idea and self.candidate is None and self.idea_check is None:
            raise ValueError("至少需要提供 idea、candidate 或 idea_check 之一")
        return self


class ExperimentPlanReview(BaseModel):
    """Human review action for a plan draft.

    Approval only changes the plan's review metadata. It never starts an
    experiment; execution remains a separate, sandboxed future workflow.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: ReviewStatus
    note: str = Field(default="", max_length=3000)
    reviewer: str = Field(default="user", min_length=1, max_length=200)


class ExperimentPlan(BaseModel):
    """A reviewable, non-executable experiment-plan draft."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(min_length=1, max_length=300)
    hypothesis: str = Field(min_length=1, max_length=5000)
    baseline: str = Field(min_length=1, max_length=3000)
    variables: list[ExperimentVariable] = Field(default_factory=list, max_length=50)
    controls: list[ExperimentControl] = Field(default_factory=list, max_length=50)
    metrics: list[ExperimentMetric] = Field(default_factory=list, max_length=50)
    ablation: list[ExperimentAblation] = Field(default_factory=list, max_length=50)
    expected_outcomes: list[ExpectedOutcome] = Field(default_factory=list, max_length=50)
    failure_criteria: list[FailureCriterion] = Field(
        default_factory=list,
        validation_alias=AliasChoices("failure_criteria", "risks"),
        max_length=50,
    )
    resource_estimate: ResourceEstimate = Field(
        default_factory=ResourceEstimate,
        validation_alias=AliasChoices("resource_estimate", "resources"),
    )
    validation_steps: list[str] = Field(default_factory=list, max_length=50)
    warnings: list[str] = Field(default_factory=list, max_length=100)
    provenance: list[EvidenceProvenance] = Field(default_factory=list, max_length=100)
    approval_status: ApprovalStatus = "draft"
    review_note: str = Field(default="", max_length=3000)
    reviewed_by: str | None = Field(default=None, max_length=200)
    reviewed_at: datetime | None = None
    # This is intentionally a constant status.  It makes the plan's boundary
    # explicit for integrations and prevents consumers from mistaking a draft
    # for an observed experiment result.
    execution_status: Literal["not_started"] = "not_started"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    project_id: UUID | None = None

    # Keep persistence deliberately explicit.  The public model exposes a few
    # convenience properties (``resources``, ``risks`` and
    # ``source_evidence_provenance``) for integrations, but those aliases are
    # not part of the canonical storage contract.  Listing the fields here
    # also protects SQLite round-trips if a future Pydantic version starts
    # serializing computed properties by default.
    _persistence_fields: ClassVar[frozenset[str]] = frozenset(
        {
            "id",
            "title",
            "hypothesis",
            "baseline",
            "variables",
            "controls",
            "metrics",
            "ablation",
            "expected_outcomes",
            "failure_criteria",
            "resource_estimate",
            "validation_steps",
            "warnings",
            "provenance",
            "approval_status",
            "review_note",
            "reviewed_by",
            "reviewed_at",
            "execution_status",
            "generated_at",
            "project_id",
        }
    )

    def persistence_payload(self) -> dict:
        """Return the canonical JSON-compatible SQLite payload.

        This is intentionally separate from the response serialization.  The
        API can keep friendly aliases without making stored documents depend
        on Pydantic's treatment of properties or computed fields.
        """

        return self.model_dump(mode="json", include=self._persistence_fields)

    @model_validator(mode="before")
    @classmethod
    def normalize_compatibility_aliases(cls, value: object) -> object:
        """Accept old payloads that serialized both canonical and short names.

        The first draft exposed ``resources``/``risks`` as convenience
        spellings in a few clients.  If such a payload is later read from
        SQLite alongside the canonical fields, strict ``extra=forbid`` would
        otherwise reject the duplicate aliases.  Canonical values win.
        """

        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        if "resource_estimate" in data:
            data.pop("resources", None)
        elif "resources" in data:
            data["resource_estimate"] = data.pop("resources")
        if "failure_criteria" in data:
            data.pop("risks", None)
        elif "risks" in data:
            data["failure_criteria"] = data.pop("risks")
        return data

    @computed_field(return_type=ResourceEstimate, alias="resources")
    @property
    def resources(self) -> ResourceEstimate:
        """Compatibility alias for the shorter ``resources`` spelling."""

        return self.resource_estimate

    @computed_field(return_type=list[FailureCriterion], alias="risks")
    @property
    def risks(self) -> list[FailureCriterion]:
        """Compatibility alias for UIs that label failure criteria as risks."""

        return self.failure_criteria

    @property
    def source_evidence_provenance(self) -> list[EvidenceProvenance]:
        return self.provenance


# Descriptive aliases keep the module pleasant to integrate without creating
# a second set of incompatible Pydantic contracts.
ExperimentPlanCreate = ExperimentPlanRequest
ExperimentPlanDraft = ExperimentPlan
VariableSpec = ExperimentVariable
ControlSpec = ExperimentControl
MetricSpec = ExperimentMetric
AblationSpec = ExperimentAblation
SourceProvenance = EvidenceProvenance


__all__ = [
    "AblationSpec",
    "ApprovalStatus",
    "ControlSpec",
    "EvidenceProvenance",
    "ExpectedOutcome",
    "ExperimentAblation",
    "ExperimentControl",
    "ExperimentMetric",
    "ExperimentPlan",
    "ExperimentPlanCreate",
    "ExperimentPlanDraft",
    "ExperimentPlanRequest",
    "ExperimentPlanReview",
    "ExperimentVariable",
    "FailureCriterion",
    "MetricSpec",
    "ResourceEstimate",
    "ReviewStatus",
    "SourceProvenance",
    "VariableSpec",
]
