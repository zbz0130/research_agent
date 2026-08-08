from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AnalysisLevel = Literal["quick", "literature", "research"]
AnalysisStatus = Literal["queued", "running", "completed", "failed"]
Audience = Literal["beginner", "student", "researcher"]
SourceKind = Literal["academic", "official", "community", "demo"]
EvidenceType = Literal["definition", "mechanism", "result", "limitation", "future_work", "context"]
EvidenceRelation = Literal["supports", "contradicts", "qualified_support", "background", "unclear"]
VerificationStatus = Literal["unverified", "reviewed"]
Confidence = Literal["high", "medium", "low"]
EvidenceLocationKind = Literal["abstract", "page", "section", "figure", "table", "url", "unknown"]
GraphNodeType = Literal["concept", "method", "problem", "paper", "idea", "note"]
GraphRelation = Literal[
    "is_a",
    "part_of",
    "related_to",
    "supports",
    "contradicts",
    "has_problem",
    "improves",
    "uses",
    "inspired_by",
]


def _http_url_or_none(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    parsed = urlparse(str(value))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("来源链接只允许 http 或 https")
    return str(value)


class AnalysisCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    concept: str = Field(min_length=1, max_length=500)
    level: AnalysisLevel = "literature"
    audience: Audience = "beginner"
    language: Literal["zh-CN", "en"] = "zh-CN"
    max_papers: int = Field(default=6, ge=1, le=12)
    project_id: UUID | None = None
    graph_name: str | None = Field(default=None, min_length=1, max_length=200)


class PaperRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    # ``id`` is kept as the provider-facing identifier for backwards
    # compatibility. These fields allow later providers to map preprint,
    # conference and journal versions to one canonical work.
    canonical_id: str | None = None
    provider_id: str | None = None
    arxiv_id: str | None = None
    version: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str = ""
    url: str | None = None
    doi: str | None = None
    citation_count: int | None = None
    source: str
    source_kind: SourceKind = "academic"
    access_type: Literal["open_access", "abstract_only", "metadata_only", "demo", "unknown"] = "unknown"
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("url", mode="before")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        return _http_url_or_none(value)


class EvidenceLocator(BaseModel):
    """Structured location for a quoted source passage.

    ``location`` on :class:`EvidenceCard` remains as a human-readable
    compatibility field, while this object gives later storage and UI layers
    stable fields for page/section/figure/table anchors.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: EvidenceLocationKind = "unknown"
    page: int | None = Field(default=None, ge=1)
    section: str | None = Field(default=None, max_length=300)
    figure: str | None = Field(default=None, max_length=100)
    table: str | None = Field(default=None, max_length=100)
    paragraph: int | None = Field(default=None, ge=1)
    url: str | None = Field(default=None, max_length=2000)

    @field_validator("url", mode="before")
    @classmethod
    def validate_locator_url(cls, value: str | None) -> str | None:
        return _http_url_or_none(value)


class EvidenceCard(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    paper_id: str
    claim: str
    excerpt: str
    location: str | None = None
    locator: EvidenceLocator | None = None
    evidence_type: EvidenceType = "context"
    relation: EvidenceRelation = "background"
    confidence: Confidence = "medium"
    verification_status: VerificationStatus = "unverified"
    source_url: str | None = None

    @field_validator("source_url", mode="before")
    @classmethod
    def validate_evidence_url(cls, value: str | None) -> str | None:
        return _http_url_or_none(value)


class ConceptNode(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=500)
    summary: str = Field(default="", max_length=5000)
    node_type: GraphNodeType = "concept"
    evidence_ids: list[str] = Field(default_factory=list)
    editable: bool = True


class ConceptEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=200)
    relation: GraphRelation = "related_to"
    evidence_ids: list[str] = Field(default_factory=list)


class ConceptGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    # These fields make a graph independently addressable when more than one
    # graph is shown in the workspace. They are optional for compatibility
    # with the Stage 0 in-memory graph builder.
    project_id: UUID | None = None
    name: str = Field(default="未命名概念图", min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    root_id: str = Field(min_length=1, max_length=200)
    version: int = Field(default=1, ge=1)
    nodes: list[ConceptNode] = Field(default_factory=list)
    edges: list[ConceptEdge] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_integrity(self) -> "ConceptGraph":
        node_ids = [node.id for node in self.nodes]
        if self.root_id not in node_ids:
            raise ValueError("root_id 必须指向图中的现有节点")
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("概念图不能包含重复节点 ID")

        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("概念图不能包含重复边 ID")
        node_id_set = set(node_ids)
        if any(edge.source not in node_id_set or edge.target not in node_id_set for edge in self.edges):
            raise ValueError("概念图中的边必须连接现有节点")
        return self


class GraphMetadataUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    root_id: str | None = Field(default=None, min_length=1, max_length=200)
    base_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_change(self) -> "GraphMetadataUpdate":
        values = self.model_dump(exclude_unset=True)
        if not values or all(key == "base_version" for key in values):
            raise ValueError("至少需要一个图谱元数据字段")
        if any(value is None for key, value in values.items() if key != "base_version"):
            raise ValueError("图谱元数据不能设置为 null")
        return self


class NodeExplanationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    audience: Audience = "beginner"
    language: Literal["zh-CN", "en"] = "zh-CN"


class ExplanationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    one_sentence: str
    intuitive: str
    technical: str
    evolution: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class InnovationCandidate(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    problem: str
    mechanism: str
    nearest_work: list[str] = Field(default_factory=list)
    novelty_level: Literal["L0", "L1", "L2", "L3", "L4"]
    confidence: Confidence = "low"
    feasibility: Literal["low", "medium", "high"] = "medium"
    rationale: str
    validation_steps: list[str] = Field(default_factory=list)
    warning: str | None = None


class AnalysisResult(BaseModel):
    id: str
    concept: str
    level: AnalysisLevel
    audience: Audience
    provider: str
    warnings: list[str] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    retrieval_scope: str = "摘要和论文元数据"
    papers: list[PaperRecord] = Field(default_factory=list)
    evidence: list[EvidenceCard] = Field(default_factory=list)
    explanation: ExplanationResult
    graph: ConceptGraph
    innovation_candidates: list[InnovationCandidate] = Field(default_factory=list)
    novelty_note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnalysisJob(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    concept: str
    level: AnalysisLevel
    audience: Audience
    project_id: UUID | None = None
    status: AnalysisStatus = "queued"
    progress: int = Field(default=0, ge=0, le=100)
    message: str = "等待开始"
    result: AnalysisResult | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


class AnalysisSummary(BaseModel):
    id: UUID
    concept: str
    level: AnalysisLevel
    project_id: UUID | None = None
    status: AnalysisStatus
    progress: int
    message: str
    created_at: datetime


class ConceptNodeUpdate(BaseModel):
    """The only fields an update_node operation may change.

    ``id`` and ``editable`` are intentionally immutable through GraphPatch.
    A node can be locked by setting ``editable=False`` when it is created by a
    trusted importer; changing that lock must happen through a separate,
    explicitly authorized workflow.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str | None = Field(default=None, min_length=1, max_length=500)
    summary: str | None = Field(default=None, max_length=5000)
    node_type: GraphNodeType | None = None
    evidence_ids: list[str] | None = None

    @model_validator(mode="after")
    def require_non_empty_update(self) -> "ConceptNodeUpdate":
        values = self.model_dump(exclude_unset=True)
        if not values:
            raise ValueError("updates 至少需要一个可编辑字段")
        if any(value is None for value in values.values()):
            raise ValueError("updates 中的可编辑字段不能为 null")
        return self


class GraphOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_node", "update_node", "remove_node", "add_edge", "remove_edge"]
    node_id: str | None = None
    node: ConceptNode | None = None
    edge: ConceptEdge | None = None
    updates: ConceptNodeUpdate | None = None

    @model_validator(mode="after")
    def validate_operation_shape(self) -> "GraphOperation":
        supplied = {
            "node_id": self.node_id,
            "node": self.node,
            "edge": self.edge,
            "updates": self.updates,
        }

        if self.op == "add_node":
            if self.node is None or any(value is not None for key, value in supplied.items() if key != "node"):
                raise ValueError("add_node 只能包含 node")
        elif self.op == "update_node":
            if not self.node_id or self.updates is None or self.node is not None or self.edge is not None:
                raise ValueError("update_node 需要 node_id 和 updates，且不能包含 node/edge")
        elif self.op == "remove_node":
            if not self.node_id or self.node is not None or self.edge is not None or self.updates is not None:
                raise ValueError("remove_node 只能包含 node_id")
        elif self.op == "add_edge":
            if self.edge is None or any(value is not None for key, value in supplied.items() if key != "edge"):
                raise ValueError("add_edge 只能包含 edge")
        elif self.op == "remove_edge":
            has_edge = self.edge is not None
            has_edge_id = bool(self.node_id)
            if has_edge == has_edge_id or self.updates is not None or (self.edge is not None and self.edge.id == ""):
                raise ValueError("remove_edge 需要且只能提供 edge 或 node_id（边 ID）")
        return self


class GraphPatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    operations: list[GraphOperation] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=1000)
    # Optional keeps existing clients working. The service fills it with the
    # graph's current version; a supplied value is checked for optimistic
    # concurrency before a patch is accepted.
    base_version: int | None = Field(default=None, ge=1)
    actor: Literal["user", "agent"] = "agent"


class GraphPatch(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    graph_id: str
    base_version: int = Field(ge=1)
    operations: list[GraphOperation]
    reason: str
    actor: Literal["user", "agent"]
    status: Literal["proposed", "applied", "rejected"] = "proposed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
