from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.evidence_schemas import EvidenceLedger


AnalysisLevel = Literal["quick", "literature", "research"]
AnalysisStatus = Literal["queued", "running", "completed", "failed"]
Audience = Literal["beginner", "student", "researcher"]
SourceKind = Literal["academic", "official", "community", "demo"]
EvidenceType = Literal["definition", "mechanism", "result", "limitation", "future_work", "context"]
EvidenceRelation = Literal["supports", "contradicts", "qualified_support", "background", "unclear"]
VerificationStatus = Literal["unverified", "reviewed"]
Confidence = Literal["high", "medium", "low"]
NoveltyLevel = Literal["L0", "L1", "L2", "L3", "L4"]
ManualReviewStatus = Literal["needs_review", "reviewed", "dismissed"]
ArxivCheckStatus = Literal["not_checked", "indirect_metadata", "checked", "unavailable"]
AgentRole = Literal["community", "model_brainstorm", "future_work", "synthesis"]
AgentRunStatus = Literal["queued", "running", "completed", "failed", "skipped"]
CommunityPlatform = Literal["x", "知乎", "zhihu", "reddit", "other"]
ArxivNoveltyStatus = Literal[
    "not_checked", "no_direct_match_in_scope", "matched", "unavailable", "checked"
]
EvidenceLocationKind = Literal["abstract", "page", "section", "figure", "table", "url", "unknown"]
SearchQueryPurpose = Literal[
    "core",
    "foundational",
    "recent",
    "method_family",
    "application",
    "limitations",
    "comparison",
]
SearchQueryPhase = Literal["initial", "feedback"]
AtomicClaimType = Literal["definition", "mechanism", "result", "evolution"]
ResearchLimitationKind = Literal[
    "method_limitation",
    "failure_mode",
    "tradeoff",
    "applicability_boundary",
    "evaluation_limitation",
    "theoretical_limit",
]
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


class SearchQueryPlan(BaseModel):
    """One transparent retrieval angle generated before paper search."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=2, max_length=160)
    purpose: SearchQueryPurpose = "core"
    phase: SearchQueryPhase = "initial"
    derived_from_paper_ids: list[str] = Field(default_factory=list, max_length=6)


class EvolutionItem(BaseModel):
    """A dated change with explicit paper and evidence provenance."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    year: int | None = Field(default=None, ge=1900, le=2100)
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=3000)
    paper_ids: list[str] = Field(default_factory=list, max_length=6)
    evidence_ids: list[str] = Field(default_factory=list, max_length=6)


class AtomicClaimDraft(BaseModel):
    """One independently verifiable statement proposed by the explainer."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    claim_type: AtomicClaimType
    text: str = Field(min_length=1, max_length=1200)
    paper_ids: list[str] = Field(default_factory=list, max_length=3)
    evidence_ids: list[str] = Field(default_factory=list, max_length=3)
    scope: str = Field(default="", max_length=1000)


class ResearchLimitation(BaseModel):
    """An evidence-backed limitation of a method, theory, or evaluation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=1200)
    limitation_kind: ResearchLimitationKind
    target: str = Field(min_length=1, max_length=500)
    condition: str = Field(default="", max_length=1000)
    consequence: str = Field(min_length=1, max_length=1000)
    paper_ids: list[str] = Field(min_length=1, max_length=3)
    evidence_ids: list[str] = Field(min_length=1, max_length=3)
    explicitness: Literal["explicit", "inferred"] = "explicit"


class ResearchGapCandidate(BaseModel):
    """A scoped, unverified gap candidate rather than a proven absence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=1200)
    scope: str = Field(min_length=1, max_length=1000)
    paper_ids: list[str] = Field(default_factory=list, max_length=3)
    evidence_ids: list[str] = Field(default_factory=list, max_length=3)


class ReproducibilityCheck(BaseModel):
    """A verification task that must not be confused with a research limitation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=1000)
    check_type: Literal["code", "data", "environment", "license", "benchmark"]
    paper_ids: list[str] = Field(default_factory=list, max_length=3)


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
    evolution_items: list[EvolutionItem] = Field(default_factory=list, max_length=12)
    claims: list[AtomicClaimDraft] = Field(default_factory=list, max_length=40)
    research_limitations: list[ResearchLimitation] = Field(default_factory=list, max_length=20)
    research_gap_candidates: list[ResearchGapCandidate] = Field(default_factory=list, max_length=20)
    reproducibility_checks: list[ReproducibilityCheck] = Field(default_factory=list, max_length=20)
    scope_warnings: list[str] = Field(default_factory=list, max_length=12)
    related_concepts: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class AnalysisStageTiming(BaseModel):
    """Completed pipeline stage timing exposed for progress diagnosis."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    stage: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    duration_ms: int = Field(ge=0)


class InnovationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    problem: str
    mechanism: str
    nearest_work: list[str] = Field(default_factory=list)
    novelty_level: NoveltyLevel
    confidence: Confidence = "low"
    feasibility: Literal["low", "medium", "high"] = "medium"
    rationale: str
    validation_steps: list[str] = Field(default_factory=list)
    warning: str | None = None
    # Provenance is deliberately explicit.  A generated candidate must never
    # be presented as a verified scientific result or silently mixed with a
    # paper-backed claim.
    source_type: Literal[
        "heuristic", "model_generated", "community_signal", "paper_future_work", "synthesis"
    ] = "heuristic"
    source_agent_run_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    arxiv_status: ArxivNoveltyStatus = "not_checked"
    arxiv_match_paper_ids: list[str] = Field(default_factory=list)


class CommunitySignal(BaseModel):
    """An exploratory pain-point signal from a community platform.

    Community posts are useful for discovering problems, but they are not
    scientific evidence.  The source and verification fields are mandatory in
    the object so the UI cannot accidentally render a post as a citation.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    platform: CommunityPlatform
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=5000)
    pain_point: str = Field(default="", max_length=2000)
    open_question: str = Field(default="", max_length=2000)
    url: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_type: Literal["community_signal"] = "community_signal"
    verification_status: VerificationStatus = "unverified"
    confidence: Confidence = "low"

    @field_validator("url", mode="before")
    @classmethod
    def validate_community_url(cls, value: str | None) -> str | None:
        return _http_url_or_none(value)


class FutureWorkSignal(BaseModel):
    """A limitation/discussion/future-work clue extracted from a paper.

    The first version usually has only abstracts, so ``section`` may be
    ``abstract_signal``.  This prevents an abstract sentence from being
    misrepresented as a verified quotation from a paper's Discussion section.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    paper_id: str
    paper_title: str
    section: Literal[
        "discussion",
        "conclusion",
        "limitations",
        "future_work",
        "error_analysis",
        "supplementary",
        "abstract_signal",
    ] = "abstract_signal"
    claim: str
    excerpt: str
    evidence_id: str | None = None
    locator: EvidenceLocator | None = None
    source_type: Literal["academic"] = "academic"
    verification_status: VerificationStatus = "unverified"
    confidence: Confidence = "low"


class AgentRun(BaseModel):
    """Auditable execution record for one bounded research sub-agent."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    role: AgentRole
    status: AgentRunStatus = "queued"
    provider: str
    query_terms: list[str] = Field(default_factory=list)
    input_paper_ids: list[str] = Field(default_factory=list)
    output_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class ResearchBrief(BaseModel):
    """Structured result of the research-mode multi-agent orchestration.

    ``innovation_candidates`` is the synthesis output.  The three upstream
    collections remain separate so a user can inspect which ideas came from
    community signals, model brainstorming, or paper limitations before
    accepting the synthesis.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    topic: str
    objective: str = "发现研究痛点、候选方向和最小验证路径"
    agent_runs: list[AgentRun] = Field(default_factory=list)
    community_signals: list[CommunitySignal] = Field(default_factory=list)
    model_ideas: list[InnovationCandidate] = Field(default_factory=list)
    future_work_signals: list[FutureWorkSignal] = Field(default_factory=list)
    innovation_candidates: list[InnovationCandidate] = Field(default_factory=list)
    synthesis: str = ""
    arxiv_status: ArxivNoveltyStatus = "not_checked"
    arxiv_checked_terms: list[str] = Field(default_factory=list)
    arxiv_match_paper_ids: list[str] = Field(default_factory=list)
    coverage: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnalysisResult(BaseModel):
    id: str
    concept: str
    level: AnalysisLevel
    audience: Audience
    provider: str
    warnings: list[str] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    retrieval_queries: list[SearchQueryPlan] = Field(default_factory=list, max_length=8)
    retrieval_scope: str = "摘要和论文元数据"
    papers: list[PaperRecord] = Field(default_factory=list)
    evidence: list[EvidenceCard] = Field(default_factory=list)
    explanation: ExplanationResult
    graph: ConceptGraph
    innovation_candidates: list[InnovationCandidate] = Field(default_factory=list)
    novelty_note: str | None = None
    research_brief: ResearchBrief | None = None
    # Claim-level provenance is kept alongside the original evidence cards so
    # the UI can show which generated statements are supported, contradicted,
    # or still unverified without changing the existing response contract.
    evidence_ledger: EvidenceLedger | None = None
    stage_timings: list[AnalysisStageTiming] = Field(default_factory=list, max_length=12)
    total_duration_ms: int | None = Field(default=None, ge=0)
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
    current_stage: str | None = Field(default=None, max_length=80)
    stage_timings: list[AnalysisStageTiming] = Field(default_factory=list, max_length=12)
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


class IdeaCheckCreate(BaseModel):
    """Request for an explicit prior-art check.

    This is intentionally separate from ``AnalysisCreate``.  A concept
    explanation asks "what is this?"; an idea check asks "how close is this to
    work already published?".  Keeping the contracts separate prevents the
    UI from presenting a lightweight concept search as a novelty verdict.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idea: str = Field(min_length=3, max_length=2000)
    max_papers: int = Field(default=8, ge=1, le=12)
    language: Literal["zh-CN", "en"] = "zh-CN"
    project_id: UUID | None = None


class NoveltyCheck(BaseModel):
    """Cautious, scoped prior-art assessment, never a proof of originality."""

    level: NoveltyLevel
    reason: str
    confidence: Confidence = "low"
    matched_paper_ids: list[str] = Field(default_factory=list)
    compared_terms: list[str] = Field(default_factory=list)
    scope_note: str


class RelatedWorkSummary(BaseModel):
    """Plain-language, abstract-level account of a matched paper."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    paper_id: str
    paper_title: str
    what_problem: str = Field(default="摘要未明确说明问题。", max_length=2000)
    core_mechanism: str = Field(default="摘要未提供足够机制细节。", max_length=3000)
    plain_language_summary: str = Field(max_length=4000)
    overlap_with_idea: str = Field(default="尚未从摘要确认具体重叠。", max_length=2000)
    possible_difference: str = Field(default="仅凭摘要无法确认与用户想法的差异。", max_length=2000)
    summary_level: Literal["abstract_only", "full_text_verified"] = "abstract_only"
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    verification_status: VerificationStatus = "unverified"
    confidence: Confidence = "low"


class IdeaCheckResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    idea: str
    project_id: UUID | None = None
    search_terms: list[str] = Field(default_factory=list)
    search_scope: str = "论文标题、摘要和公开元数据"
    arxiv_status: ArxivCheckStatus = "not_checked"
    papers: list[PaperRecord] = Field(default_factory=list)
    evidence: list[EvidenceCard] = Field(default_factory=list)
    related_work_summaries: list[RelatedWorkSummary] = Field(default_factory=list, max_length=30)
    novelty: NoveltyCheck
    # Flattened fields make the first-version API convenient for a table or a
    # spreadsheet export, while ``novelty`` keeps the assessment grouped.
    similarity_level: NoveltyLevel
    similarity_reason: str
    current_conclusion: str
    confidence: Confidence = "low"
    manual_review_status: ManualReviewStatus = "needs_review"
    review_note: str | None = Field(default=None, max_length=2000)
    reviewed_by: str | None = Field(default=None, max_length=200)
    reviewed_at: datetime | None = None
    alternative_ideas: list[InnovationCandidate] = Field(default_factory=list)
    validation_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IdeaCheckReview(BaseModel):
    """Human review metadata for a prior-art triage result."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: ManualReviewStatus
    note: str | None = Field(default=None, max_length=2000)
    reviewer: str | None = Field(default=None, max_length=200)


class GraphCompareCreate(BaseModel):
    """Select several saved graphs (and optionally a node subset) to compare."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    graph_ids: list[str] = Field(min_length=2, max_length=6)
    node_ids: list[str] = Field(default_factory=list, max_length=60)
    focus: str = Field(
        default="找出可以互相借鉴的机制，并给出最小验证实验",
        min_length=1,
        max_length=1000,
    )

    @model_validator(mode="after")
    def unique_graphs(self) -> "GraphCompareCreate":
        if any(not graph_id for graph_id in self.graph_ids):
            raise ValueError("graph_ids 不能包含空字符串")
        if len(set(self.graph_ids)) != len(self.graph_ids):
            raise ValueError("graph_ids 不能重复")
        return self


class GraphConnection(BaseModel):
    source_graph_id: str
    target_graph_id: str
    source_node_id: str
    target_node_id: str
    relation: Literal["cross_domain_candidate", "shared_problem", "method_transfer"] = (
        "cross_domain_candidate"
    )
    idea: str
    source_evidence_ids: list[str] = Field(default_factory=list)
    target_evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "low"
    validation_steps: list[str] = Field(default_factory=list)
    warning: str = "跨图连接是未验证假设，不代表已有证据证明可行。"


class GraphCompareResult(BaseModel):
    graph_ids: list[str]
    focus: str
    connections: list[GraphConnection] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GraphSubsetResult(BaseModel):
    source_graph_id: str
    graph: ConceptGraph
    selected_node_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


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
    # These fields are populated by the natural-language Agent Patch tool.
    # Keeping them on the canonical patch contract makes the translation
    # decision visible in the review UI and preserves it in SQLite.  Existing
    # callers can omit them and continue to create ordinary patches.
    translation_mode: Literal["heuristic", "model"] = "heuristic"
    source_request: str | None = Field(default=None, max_length=2000)
    warnings: list[str] = Field(default_factory=list, max_length=8)


class GraphAgentPatchCreate(BaseModel):
    """Bounded natural-language request for an Agent concept-graph patch.

    The endpoint accepts a request rather than arbitrary operations.  The
    server translates it into at most ``max_operations`` validated
    :class:`GraphOperation` objects and stores the result as an Agent
    proposal.  It deliberately does not expose fields such as ``editable``
    or arbitrary node IDs for mutation; GraphService remains the final
    authority for root, lock, endpoint, and optimistic-version checks.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request: str = Field(min_length=3, max_length=2000)
    target_node_id: str | None = Field(default=None, min_length=1, max_length=200)
    base_version: int | None = Field(default=None, ge=1)
    language: Literal["zh-CN", "en"] = "zh-CN"
    # A small caller-selectable budget is useful for previews, but the upper
    # bound is intentionally lower than the generic GraphPatch limit.
    max_operations: int = Field(default=4, ge=1, le=4)


class GraphCreate(BaseModel):
    """Payload for creating an independent, user-editable concept graph.

    Analysis results create graphs automatically, but the workspace also needs
    a small import/create contract so users can keep a hand-built tree or a
    graph copied from another project.  ``id`` is optional; when omitted the
    service generates one.  Existing graph IDs are never overwritten by the
    public create endpoint.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str | None = Field(default=None, min_length=1, max_length=200)
    project_id: UUID | None = None
    name: str = Field(default="未命名概念图", min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    root_id: str = Field(min_length=1, max_length=200)
    nodes: list[ConceptNode] = Field(min_length=1, max_length=500)
    edges: list[ConceptEdge] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def validate_integrity(self) -> "GraphCreate":
        node_ids = [node.id for node in self.nodes]
        if self.root_id not in node_ids:
            raise ValueError("root_id 必须指向图中的现有节点")
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("概念图不能包含重复节点 ID")
        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("概念图不能包含重复边 ID")
        known = set(node_ids)
        if any(edge.source not in known or edge.target not in known for edge in self.edges):
            raise ValueError("概念图中的边必须连接现有节点")
        if any(edge.source == edge.target for edge in self.edges):
            raise ValueError("概念图不能包含自环边")
        return self


class GraphPatch(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    graph_id: str
    base_version: int = Field(ge=1)
    operations: list[GraphOperation]
    reason: str
    actor: Literal["user", "agent"]
    status: Literal["proposed", "applied", "rejected"] = "proposed"
    translation_mode: Literal["heuristic", "model"] = "heuristic"
    source_request: str | None = Field(default=None, max_length=2000)
    warnings: list[str] = Field(default_factory=list, max_length=8)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Friendly aliases for callers that prefer the request/agent naming order.
# They point at one Pydantic model so OpenAPI and runtime validation stay in
# sync while older integrations can choose either spelling.
AgentGraphPatchRequest = GraphAgentPatchCreate
GraphAgentPatchRequest = GraphAgentPatchCreate
