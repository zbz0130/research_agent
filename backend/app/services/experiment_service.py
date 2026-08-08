"""Generate reviewable experiment-plan drafts without executing experiments.

The service is intentionally deterministic and side-effect free.  It accepts a
free-form idea or the existing research objects and turns them into a modest,
auditable first-pass design.  A future execution runner can consume the
result *after* a human approval step, but this module never invokes a shell,
Python process, model tool, network provider, or experiment backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app.experiment_schemas import (
    EvidenceProvenance,
    ExpectedOutcome,
    ExperimentAblation,
    ExperimentControl,
    ExperimentMetric,
    ExperimentPlan,
    ExperimentPlanRequest,
    ExperimentPlanReview,
    ExperimentVariable,
    FailureCriterion,
    ResourceEstimate,
)
from app.research_schemas import IdeaCheckResult, InnovationCandidate


class ExperimentPlanError(ValueError):
    """Raised when a plan cannot be drafted from the supplied source."""


@dataclass(frozen=True)
class _IdeaContext:
    idea: str
    title: str
    problem: str
    mechanism: str
    nearest_work: tuple[str, ...]
    validation_steps: tuple[str, ...]
    warnings: tuple[str, ...]
    provenance: tuple[EvidenceProvenance, ...]
    confidence: str
    novelty_level: str | None
    paper_count: int


class ExperimentService:
    """Build a structured experiment draft using transparent heuristics.

    ``generate`` is the primary entry point.  ``create``, ``build_plan`` and
    ``generate_plan`` are small aliases useful to route or UI integrations;
    they all share the same pure implementation.
    """

    def generate(
        self,
        payload: ExperimentPlanRequest
        | str
        | InnovationCandidate
        | IdeaCheckResult
        | Mapping[str, Any],
        **overrides: Any,
    ) -> ExperimentPlan:
        """Generate a plan draft and never execute code.

        ``payload`` can be a validated request, a plain idea string, an
        ``InnovationCandidate``, an ``IdeaCheckResult``, or a mapping accepted
        by ``ExperimentPlanRequest``.  Keyword overrides (for example
        ``baseline=...`` or ``metrics=[...]``) are validated through the same
        Pydantic request model before generation.
        """

        request = self._coerce_request(payload)
        if overrides:
            request = self._with_overrides(request, overrides)

        context = self._build_context(request)
        baseline = request.baseline or self._default_baseline(context)
        variables = request.variables or self._default_variables(context)
        controls = request.controls or self._default_controls(context)
        metrics = request.metrics or self._default_metrics(context)
        metrics = self._ensure_primary_metric(metrics)
        ablation = request.ablation or self._default_ablations(context, metrics)
        expected_outcomes = request.expected_outcomes or self._default_expected_outcomes(
            context, baseline, metrics
        )
        failure_criteria = request.failure_criteria or self._default_failure_criteria(
            context, metrics
        )
        resource_estimate = request.resource_estimate or self._default_resources(context)
        validation_steps = list(request.validation_steps or context.validation_steps)
        if not validation_steps:
            validation_steps = self._default_validation_steps(context)

        warnings = self._build_warnings(context)
        title = request.title or context.title
        provenance = self._merge_provenance(request.provenance, context.provenance)

        return ExperimentPlan(
            title=title,
            hypothesis=self._build_hypothesis(context, baseline, metrics),
            baseline=baseline,
            variables=variables,
            controls=controls,
            metrics=metrics,
            ablation=ablation,
            expected_outcomes=expected_outcomes,
            failure_criteria=failure_criteria,
            resource_estimate=resource_estimate,
            validation_steps=validation_steps,
            warnings=warnings,
            provenance=provenance,
            approval_status="draft",
            # The literal field makes this boundary machine-checkable: this
            # function only drafts a plan and does not start a run.
            execution_status="not_started",
            project_id=request.project_id,
        )

    def create(self, payload: Any, **overrides: Any) -> ExperimentPlan:
        """Alias for integrations that use repository-style ``create`` APIs."""

        return self.generate(payload, **overrides)

    def build_plan(self, payload: Any, **overrides: Any) -> ExperimentPlan:
        return self.generate(payload, **overrides)

    def generate_plan(self, payload: Any, **overrides: Any) -> ExperimentPlan:
        return self.generate(payload, **overrides)

    def from_candidate(
        self, candidate: InnovationCandidate, **overrides: Any
    ) -> ExperimentPlan:
        """Generate directly from an existing innovation candidate."""

        return self.generate(candidate, **overrides)

    def from_idea_check(
        self, result: IdeaCheckResult, **overrides: Any
    ) -> ExperimentPlan:
        """Generate directly from a prior-art check result."""

        return self.generate(result, **overrides)

    @staticmethod
    def review(plan: ExperimentPlan, review: ExperimentPlanReview) -> ExperimentPlan:
        """Apply a human review label without starting execution."""

        return plan.model_copy(
            update={
                "approval_status": review.status,
                "review_note": review.note,
                "reviewed_by": review.reviewer,
                "reviewed_at": datetime.now(timezone.utc),
            }
        )

    @staticmethod
    def _coerce_request(
        payload: ExperimentPlanRequest
        | str
        | InnovationCandidate
        | IdeaCheckResult
        | Mapping[str, Any],
    ) -> ExperimentPlanRequest:
        if isinstance(payload, ExperimentPlanRequest):
            return payload
        if isinstance(payload, InnovationCandidate):
            seed = next(
                (
                    value.strip()
                    for value in (payload.title, payload.problem, payload.mechanism)
                    if isinstance(value, str) and len(value.strip()) >= 3
                ),
                None,
            )
            if seed is None:
                raise ExperimentPlanError("InnovationCandidate 缺少至少三个字符的可用想法文本")
            return ExperimentPlanRequest(
                idea=seed,
                candidate=payload,
            )
        if isinstance(payload, IdeaCheckResult):
            idea = (payload.idea or "").strip()
            if len(idea) < 3:
                raise ExperimentPlanError("IdeaCheckResult 缺少至少三个字符的可用想法文本")
            return ExperimentPlanRequest(idea=idea, idea_check=payload)
        if isinstance(payload, str):
            return ExperimentPlanRequest(idea=payload)
        if isinstance(payload, Mapping):
            return ExperimentPlanRequest.model_validate(payload)
        raise TypeError(
            "实验方案输入必须是 ExperimentPlanRequest、字符串、"
            "InnovationCandidate、IdeaCheckResult 或映射"
        )

    @staticmethod
    def _with_overrides(
        request: ExperimentPlanRequest, overrides: Mapping[str, Any]
    ) -> ExperimentPlanRequest:
        data = request.model_dump(mode="python")
        accepted = {
            "idea",
            "candidate",
            "idea_check",
            "title",
            "baseline",
            "variables",
            "controls",
            "metrics",
            "ablation",
            "expected_outcomes",
            "failure_criteria",
            "resource_estimate",
            "validation_steps",
            "provenance",
            "project_id",
        }
        normalized: dict[str, Any] = {}
        for key, value in overrides.items():
            canonical = {
                "resources": "resource_estimate",
                "risks": "failure_criteria",
            }.get(key, key)
            if canonical not in accepted:
                raise TypeError(f"不支持的实验方案覆盖字段：{key}")
            normalized[canonical] = value
        data.update(normalized)
        return ExperimentPlanRequest.model_validate(data)

    @classmethod
    def _build_context(cls, request: ExperimentPlanRequest) -> _IdeaContext:
        candidate = request.candidate
        idea_check = request.idea_check
        warnings: list[str] = []
        provenance: list[EvidenceProvenance] = list(request.provenance)
        nearest_work: list[str] = []
        validation_steps: list[str] = []
        confidence = "low"
        novelty_level: str | None = None
        paper_count = 0

        if candidate is not None:
            idea = request.idea or candidate.title or candidate.problem
            title = request.title or candidate.title or f"验证：{idea[:100]}"
            problem = candidate.problem or f"验证“{idea}”在目标场景中的有效性。"
            mechanism = candidate.mechanism or idea
            nearest_work.extend(candidate.nearest_work)
            validation_steps.extend(candidate.validation_steps)
            confidence = candidate.confidence
            novelty_level = candidate.novelty_level
            warnings.append("创新候选是待验证假设，不是已确认的原创成果。")
            if candidate.warning:
                warnings.append(candidate.warning)
            provenance.append(
                EvidenceProvenance(
                    source=f"InnovationCandidate: {candidate.title}",
                    source_type=candidate.source_type,
                    source_id=candidate.id,
                    source_agent_run_id=candidate.source_agent_run_id,
                    evidence_ids=candidate.evidence_ids,
                    confidence=candidate.confidence,
                    verification_status="unverified",
                    notes=candidate.rationale,
                )
            )
            for nearest in candidate.nearest_work[:8]:
                provenance.append(
                    EvidenceProvenance(
                        source=nearest,
                        source_type="nearest_work",
                        confidence="low",
                        verification_status="unverified",
                        notes="候选记录中的近邻工作名称，尚未在本服务中核对全文等价性。",
                    )
                )
        elif idea_check is not None:
            idea = request.idea or idea_check.idea
            title = request.title or f"验证：{idea[:100]}"
            problem = idea_check.current_conclusion or f"验证“{idea}”的可行性。"
            if idea_check.alternative_ideas:
                alternative = idea_check.alternative_ideas[0]
                mechanism = alternative.mechanism or idea
                nearest_work.extend(alternative.nearest_work)
                validation_steps.extend(alternative.validation_steps)
            else:
                mechanism = idea
            nearest_work.extend(paper.title for paper in idea_check.papers)
            nearest_work = list(dict.fromkeys(nearest_work))
            validation_steps.extend(idea_check.validation_steps)
            confidence = idea_check.confidence
            novelty_level = idea_check.similarity_level
            paper_count = len(idea_check.papers)
            warnings.extend(idea_check.warnings)
            warnings.append("prior-art 检查范围有限；相似性结果需要人工核对全文和实验条件。")
            provenance.append(
                EvidenceProvenance(
                    source="IdeaCheckResult",
                    source_type="idea_check",
                    source_id=idea_check.id,
                    evidence_ids=[item.id for item in idea_check.evidence],
                    confidence=idea_check.confidence,
                    verification_status="partially_verified" if idea_check.evidence else "unverified",
                    notes=idea_check.search_scope,
                )
            )
            for paper in idea_check.papers[:8]:
                provenance.append(
                    EvidenceProvenance(
                        source=paper.title,
                        source_type="paper_metadata",
                        source_id=paper.id,
                        evidence_ids=[
                            item.id for item in idea_check.evidence if item.paper_id == paper.id
                        ],
                        source_url=paper.url,
                        confidence="low" if paper.source_kind == "demo" else "medium",
                        verification_status="unverified",
                        notes="仅使用论文标题、摘要或公开元数据。",
                    )
                )
        else:
            # The request validator guarantees a non-empty idea here.
            idea = (request.idea or "").strip()
            title = request.title or f"验证：{idea[:100]}"
            problem = f"验证“{idea}”是否能在目标场景中带来可重复的改进。"
            mechanism = idea
            warnings.append("当前输入只有自由文本，尚未绑定论文或人工核验的证据。")
            provenance.append(
                EvidenceProvenance(
                    source="用户输入",
                    source_type="user_input",
                    confidence="low",
                    verification_status="unverified",
                    notes="实验假设由自由文本经透明启发式展开。",
                )
            )

        # A caller may deliberately provide both a generated candidate and a
        # prior-art check.  Keep both provenance chains instead of silently
        # discarding the check just because the candidate supplied the main
        # mechanism text.
        if candidate is not None and idea_check is not None:
            warnings.extend(idea_check.warnings)
            warnings.append(
                "prior-art 检查范围有限；相似性结果需要人工核对全文和实验条件。"
            )
            nearest_work.extend(paper.title for paper in idea_check.papers)
            validation_steps.extend(idea_check.validation_steps)
            paper_count = max(paper_count, len(idea_check.papers))
            novelty_level = idea_check.similarity_level
            provenance.append(
                EvidenceProvenance(
                    source="IdeaCheckResult",
                    source_type="idea_check",
                    source_id=idea_check.id,
                    evidence_ids=[item.id for item in idea_check.evidence],
                    confidence=idea_check.confidence,
                    verification_status="partially_verified" if idea_check.evidence else "unverified",
                    notes=idea_check.search_scope,
                )
            )
            for paper in idea_check.papers[:8]:
                provenance.append(
                    EvidenceProvenance(
                        source=paper.title,
                        source_type="paper_metadata",
                        source_id=paper.id,
                        evidence_ids=[
                            item.id for item in idea_check.evidence if item.paper_id == paper.id
                        ],
                        source_url=paper.url,
                        confidence="low" if paper.source_kind == "demo" else "medium",
                        verification_status="unverified",
                        notes="仅使用论文标题、摘要或公开元数据。",
                    )
                )

        if request.idea and candidate is not None and request.idea.strip() != candidate.title.strip():
            # Preserve the user wording while retaining candidate structure.
            idea = request.idea.strip()
        if request.idea and idea_check is not None:
            idea = request.idea.strip()

        if nearest_work:
            nearest_work = list(dict.fromkeys(item.strip() for item in nearest_work if item.strip()))
        if validation_steps:
            validation_steps = list(dict.fromkeys(item.strip() for item in validation_steps if item.strip()))

        if paper_count == 0 and idea_check is None:
            # Candidate.nearest_work is useful provenance even when no paper
            # records are attached, but it is not equivalent to verified data.
            paper_count = len(nearest_work)

        return _IdeaContext(
            idea=idea.strip(),
            title=title.strip(),
            problem=problem.strip(),
            mechanism=mechanism.strip(),
            nearest_work=tuple(nearest_work),
            validation_steps=tuple(validation_steps),
            warnings=tuple(warnings),
            provenance=tuple(provenance),
            confidence=confidence,
            novelty_level=novelty_level,
            paper_count=paper_count,
        )

    @staticmethod
    def _default_baseline(context: _IdeaContext) -> str:
        if context.nearest_work:
            return (
                f"复现最接近的已有方法“{context.nearest_work[0]}”，并保持数据、"
                "训练/推理预算和调参范围与候选方法一致。"
            )
        text = f"{context.idea} {context.mechanism}".lower()
        if any(token in text for token in ("attention", "注意力", "kv cache", "kv缓存", "长上下文")):
            return "标准 Attention/当前主流长上下文实现（按任务选择 FlashAttention 或等价公开基线）。"
        if any(token in text for token in ("lora", "低秩", "微调", "fine-tun")):
            return "固定 rank 的 LoRA（保持可训练参数量、数据和训练步数一致）。"
        if any(token in text for token in ("retrieval", "检索", "rag", "搜索")):
            return "当前生产或公开数据集上的标准检索基线（如 BM25 或现有 RAG 流程）。"
        return "当前任务的标准方法或公开最佳可复现基线（固定数据、预算和调参范围）。"

    @staticmethod
    def _default_variables(context: _IdeaContext) -> list[ExperimentVariable]:
        text = f"{context.idea} {context.problem}".lower()
        scale_name = "序列长度/任务规模" if any(
            token in text for token in ("attention", "上下文", "序列", "llm", "language model")
        ) else "数据规模/任务难度"
        scale_levels = ["小", "中", "大"]
        if "dataset" in text or "数据" in text:
            scale_levels = ["低资源", "中等资源", "完整资源"]
        return [
            ExperimentVariable(
                name="method",
                role="independent",
                description="比较标准基线与候选机制，其他条件保持一致。",
                levels=["baseline", "proposed"],
                measurement="记录每个方法在所有预注册指标上的结果。",
            ),
            ExperimentVariable(
                name=scale_name,
                role="moderator",
                description="检查候选方法是否只在特定规模或难度下有效。",
                levels=scale_levels,
            ),
            ExperimentVariable(
                name="random_seed",
                role="nuisance",
                description="用多个固定随机种子估计结果方差，而不是只报告一次运行。",
                levels=["seed-1", "seed-2", "seed-3"],
            ),
        ]

    @staticmethod
    def _default_controls(context: _IdeaContext) -> list[ExperimentControl]:
        return [
            ExperimentControl(
                name="data_split",
                description="固定训练、验证和测试集划分，并记录数据版本。",
                rationale="避免数据泄漏或数据漂移造成的伪改进。",
                control_type="dataset_split",
            ),
            ExperimentControl(
                name="compute_budget",
                description="基线和候选使用相同硬件、最大步数、批大小和早停规则。",
                rationale="把差异归因于候选机制，而不是更多计算资源。",
                control_type="constant",
            ),
            ExperimentControl(
                name="randomization_and_repeats",
                description="至少使用三个预注册随机种子，并随机化运行顺序。",
                rationale="降低偶然种子和机器热身顺序造成的偏差。",
                control_type="randomization",
            ),
            ExperimentControl(
                name="metric_protocol",
                description="在同一评测脚本、版本和聚合方式下计算指标。",
                rationale="保证跨方法比较的测量口径一致。",
                control_type="statistical",
            ),
        ]

    @staticmethod
    def _default_metrics(context: _IdeaContext) -> list[ExperimentMetric]:
        text = f"{context.idea} {context.problem} {context.mechanism}".lower()
        if any(token in text for token in ("latency", "延迟", "推理", "attention", "上下文", "kv cache")):
            return [
                ExperimentMetric(
                    name="task_quality",
                    description="任务质量或准确性，按领域选择公开评测集。",
                    direction="maximize",
                    unit="score",
                    primary=True,
                    aggregation="mean ± standard deviation across seeds",
                    measurement_protocol="固定评测集、解码参数和评测脚本。",
                ),
                ExperimentMetric(
                    name="latency_ms",
                    description="端到端或每请求推理延迟。",
                    direction="minimize",
                    unit="ms/request",
                    aggregation="p50 and p95 across requests",
                    measurement_protocol="预热后固定并发度，报告 p50/p95 和测量环境。",
                ),
                ExperimentMetric(
                    name="peak_memory_mb",
                    description="运行期间峰值 CPU/GPU 内存。",
                    direction="minimize",
                    unit="MB",
                    aggregation="maximum across runs",
                    measurement_protocol="记录相同输入长度和批大小下的峰值。",
                ),
            ]
        if any(token in text for token in ("classification", "分类", "识别", "预测")):
            return [
                ExperimentMetric(
                    name="task_quality",
                    description="主任务效果，优先使用与领域一致的 F1/准确率或 AUROC。",
                    direction="maximize",
                    unit="score",
                    primary=True,
                    aggregation="mean ± standard deviation across seeds",
                    measurement_protocol="只在冻结测试集上做最终评估。",
                ),
                ExperimentMetric(
                    name="training_cost",
                    description="达到预设验证集质量所需训练时间或步数。",
                    direction="minimize",
                    unit="hours",
                    measurement_protocol="固定硬件和早停规则后记录墙钟时间。",
                ),
                ExperimentMetric(
                    name="robustness",
                    description="在预注册扰动或分布变化下的性能保持率。",
                    direction="maximize",
                    unit="score",
                    measurement_protocol="使用与主任务隔离的压力测试集。",
                ),
            ]
        return [
            ExperimentMetric(
                name="task_quality",
                description="与研究问题直接对应的主要质量指标。",
                direction="maximize",
                unit="domain score",
                primary=True,
                aggregation="mean ± standard deviation across seeds",
                measurement_protocol="预先固定评测数据、脚本、聚合和统计检验。",
            ),
            ExperimentMetric(
                name="resource_cost",
                description="达到同等质量所需的时间、显存或样本成本。",
                direction="minimize",
                unit="normalized cost",
                measurement_protocol="在相同资源上限下记录墙钟时间和峰值资源。",
            ),
            ExperimentMetric(
                name="reproducibility",
                description="不同随机种子或重复运行之间的结果波动。",
                direction="minimize",
                unit="standard deviation",
                measurement_protocol="至少三个种子，报告均值、标准差和置信区间。",
            ),
        ]

    @staticmethod
    def _ensure_primary_metric(metrics: Sequence[ExperimentMetric]) -> list[ExperimentMetric]:
        result = list(metrics)
        if not result:
            return [ExperimentMetric(name="task_quality", primary=True, direction="maximize")]
        if not any(metric.primary for metric in result):
            result[0] = result[0].model_copy(update={"primary": True})
        return result

    @staticmethod
    def _default_ablations(
        context: _IdeaContext, metrics: Sequence[ExperimentMetric]
    ) -> list[ExperimentAblation]:
        primary_names = [metric.name for metric in metrics[:3]]
        mechanism = context.mechanism[:180] or "候选机制"
        return [
            ExperimentAblation(
                component=mechanism,
                ablation_type="remove",
                variant="移除候选机制，退回基线流程",
                rationale="确认改进来自候选机制本身，而不是数据、调参或额外计算。",
                expected_effect="若假设成立，主要质量指标应下降或资源优势消失。",
                metrics=primary_names,
            ),
            ExperimentAblation(
                component="候选机制的关键超参数/容量",
                ablation_type="scale",
                variant="低、中、高三个容量档位",
                rationale="检查效果是否依赖极端容量，并估计收益—成本曲线。",
                expected_effect="结果应随容量变化呈现可解释趋势；若无趋势，需重新审视机制。",
                metrics=primary_names,
            ),
        ]

    @staticmethod
    def _default_expected_outcomes(
        context: _IdeaContext,
        baseline: str,
        metrics: Sequence[ExperimentMetric],
    ) -> list[ExpectedOutcome]:
        primary = next((metric for metric in metrics if metric.primary), metrics[0])
        quality_prediction = (
            f"相较于基线（{baseline[:180]}），候选机制在相同预算下使 {primary.name} "
            "有方向性改善；改善幅度需由预实验和统计区间确认。"
        )
        outcomes = [
            ExpectedOutcome(
                scenario="主要目标场景",
                prediction=quality_prediction,
                metric=primary.name,
                threshold="至少达到预注册的最小实际改进（建议先由人工设定）",
                confidence="low" if context.confidence == "low" else "medium",
            ),
            ExpectedOutcome(
                scenario="规模或难度变化",
                prediction="若机制确实针对目标瓶颈，规模增大时收益应保持或呈现可解释变化，而非只在单一设置有效。",
                metric=next((metric.name for metric in metrics if metric.name != primary.name), None),
                confidence="low",
            ),
            ExpectedOutcome(
                scenario="资源与质量权衡",
                prediction="候选机制不应以不可接受的资源开销换取微小质量提升；所有成本指标必须同时报告。",
                metric="resource_cost" if any(metric.name == "resource_cost" for metric in metrics) else None,
                confidence="low",
            ),
        ]
        return outcomes

    @staticmethod
    def _default_failure_criteria(
        context: _IdeaContext, metrics: Sequence[ExperimentMetric]
    ) -> list[FailureCriterion]:
        primary = next((metric for metric in metrics if metric.primary), metrics[0])
        return [
            FailureCriterion(
                condition=(
                    f"在至少三个随机种子下，{primary.name} 相对基线没有达到预注册的最小实际改进，"
                    "且置信区间跨过零。"
                ),
                severity="stop",
                action="停止扩大实验规模，记录负结果并回到假设或机制审查。",
                metric=primary.name,
            ),
            FailureCriterion(
                condition="候选方法导致主要质量指标下降超过 2%，或任一安全/正确性约束被违反。",
                severity="stop",
                action="停止该配置并检查实现、数据泄漏和评测脚本。",
                metric=primary.name,
            ),
            FailureCriterion(
                condition="资源成本（时间、峰值内存或样本量）比基线增加超过 20%，且没有相称的质量收益。",
                severity="major",
                action="将该方向标记为成本受限，并评估简化机制或更小规模设置。",
                metric="resource_cost",
            ),
            FailureCriterion(
                condition="不同随机种子之间方差过大、结果无法复现，或关键日志/版本信息缺失。",
                severity="major",
                action="暂停结论，补齐重复运行和审计信息后再解释结果。",
                metric="reproducibility",
            ),
        ]

    @staticmethod
    def _default_resources(context: _IdeaContext) -> ResourceEstimate:
        text = f"{context.idea} {context.mechanism}".lower()
        if any(token in text for token in ("llm", "language model", "attention", "长上下文", "kv cache")):
            return ResourceEstimate(
                compute="单张中高端 GPU；先用小模型/短序列做预实验",
                time_estimate_hours=12.0,
                gpu_hours=8.0,
                memory_gb=24.0,
                storage_gb=20.0,
                personnel_hours=4.0,
                data_requirements="固定公开评测集、模型版本和 tokenizer；保留运行配置与日志。",
                notes="先做小规模预实验，只有通过失败判据才扩大到完整长度或模型。",
            )
        if any(token in text for token in ("train", "训练", "微调", "lora", "低秩")):
            return ResourceEstimate(
                compute="单张 GPU 或等价云实例",
                time_estimate_hours=8.0,
                gpu_hours=6.0,
                memory_gb=16.0,
                storage_gb=15.0,
                personnel_hours=4.0,
                data_requirements="固定数据版本、训练步数、批大小和随机种子。",
                notes="先以 10% 数据和较短训练预算验证方向，再决定是否完整训练。",
            )
        return ResourceEstimate(
            compute="本地 CPU 或单张 GPU",
            time_estimate_hours=4.0,
            gpu_hours=1.0,
            memory_gb=8.0,
            storage_gb=5.0,
            personnel_hours=2.0,
            data_requirements="固定数据切分和版本，保留预处理配置。",
            notes="优先运行小规模、可复现的预实验，不在草案阶段分配外部资源。",
        )

    @staticmethod
    def _default_validation_steps(context: _IdeaContext) -> list[str]:
        return [
            "锁定数据、代码版本、硬件、超参数和随机种子，并记录实验配置。",
            "先在小规模数据和短预算上比较基线、候选及消融变体。",
            "通过预注册的指标、失败判据和至少三个随机种子检查结果。",
            "人工核对最接近论文、证据定位和方法差异，再决定是否扩大实验。",
        ]

    @staticmethod
    def _build_hypothesis(
        context: _IdeaContext,
        baseline: str,
        metrics: Sequence[ExperimentMetric],
    ) -> str:
        primary = next((metric for metric in metrics if metric.primary), metrics[0])
        return (
            f"如果将“{context.mechanism}”用于缓解“{context.problem}”，则在与基线“{baseline}”"
            f"相同的数据、预算和评测协议下，{primary.name} 应出现可重复的方向性改善；"
            "该改善不能以违反预注册资源或正确性约束为代价。"
        )

    @staticmethod
    def _build_warnings(context: _IdeaContext) -> list[str]:
        warnings = [
            "仅生成结构化实验方案草案，不执行代码、命令、网络调用或外部实验。",
            "方案由透明启发式展开，不能替代领域专家对方法、统计设计和安全性的审查。",
            "预期结果是事前假设，不是已经观察到的实验结果。",
        ]
        warnings.extend(context.warnings)
        if not context.provenance or not any(item.evidence_ids for item in context.provenance):
            warnings.append("当前方案没有绑定可核验证据 ID；请在审批前补充论文、数据或人工记录来源。")
        if context.novelty_level in {"L0", "L1"}:
            warnings.append(
                f"来源的 prior-art 相似等级为 {context.novelty_level}；应先明确与最高相关工作的差异。"
            )
        if context.paper_count == 0:
            warnings.append("尚未附带论文记录；基线和指标仍需由研究者按领域具体化。")
        return list(dict.fromkeys(item.strip() for item in warnings if item and item.strip()))

    @staticmethod
    def _merge_provenance(
        provided: Sequence[EvidenceProvenance], generated: Sequence[EvidenceProvenance]
    ) -> list[EvidenceProvenance]:
        merged: list[EvidenceProvenance] = []
        seen: dict[tuple[str, str | None], int] = {}
        for item in [*provided, *generated]:
            key = (item.source, item.source_id)
            existing_index = seen.get(key)
            if existing_index is not None:
                existing = merged[existing_index]
                evidence_ids = list(
                    dict.fromkeys([*existing.evidence_ids, *item.evidence_ids])
                )
                merged[existing_index] = existing.model_copy(
                    update={
                        "evidence_ids": evidence_ids,
                        "evidence": evidence_ids,
                        "notes": existing.notes or item.notes,
                        "source_agent_run_id": existing.source_agent_run_id
                        or item.source_agent_run_id,
                    }
                )
                continue
            seen[key] = len(merged)
            merged.append(item)
        return merged


experiment_service = ExperimentService()
ExperimentPlanService = ExperimentService
experiment_plan_service = experiment_service


def generate_experiment_plan(payload: Any, **overrides: Any) -> ExperimentPlan:
    """Module-level convenience wrapper for simple integrations."""

    return experiment_service.generate(payload, **overrides)


build_experiment_plan = generate_experiment_plan
generate_plan = generate_experiment_plan


__all__ = [
    "ExperimentPlanError",
    "ExperimentPlanService",
    "ExperimentService",
    "build_experiment_plan",
    "experiment_plan_service",
    "experiment_service",
    "generate_experiment_plan",
    "generate_plan",
]
