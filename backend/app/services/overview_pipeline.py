from __future__ import annotations

"""Bounded, auditable building blocks for a research-direction Overview.

The classes in this module are deliberately deterministic.  They are separate
workers with explicit inputs and audit records, but they are *not* presented as
independent language-model agents.  A later model-backed implementation can
replace the planner or adjudicator without changing the safety boundaries here:
one shared search provider, at most four concurrent direction tasks, bounded
paper counts, and honest abstract/PDF provenance.
"""

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
import importlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from threading import BoundedSemaphore, Lock
import time
from typing import Callable, Iterable, Literal, Sequence
from urllib.parse import urlparse

import httpx

from app.research_schemas import PaperRecord
from app.services.research_providers import ProviderUnavailable, SearchProvider


DirectionDecision = Literal["split", "keep", "merge", "discard"]


@dataclass(frozen=True)
class TaxonomyRule:
    key: str
    label: str
    definition: str
    boundary: str
    search_phrases: tuple[str, ...]
    match_terms: tuple[str, ...]
    subdirections: tuple[tuple[str, str, tuple[str, ...]], ...] = ()


TAXONOMY_RULES: tuple[TaxonomyRule, ...] = (
    TaxonomyRule(
        "efficiency",
        "效率、推理与系统优化",
        "研究如何减少推理延迟、显存占用和服务成本。",
        "不把只报告任务精度、但没有系统或计算开销分析的论文归入本方向。",
        ("efficient inference", "memory optimization", "model serving"),
        ("efficient", "efficiency", "latency", "throughput", "memory", "cache", "serving", "inference", "quantization", "compression", "sparse", "flashattention", "kv cache", "加速", "效率", "显存", "缓存", "吞吐"),
        (
            ("cache", "缓存与上下文管理", ("cache", "memory", "context", "kv", "缓存", "显存")),
            ("serving", "推理服务与吞吐", ("serving", "throughput", "latency", "inference", "推理", "吞吐")),
            ("compression", "压缩、稀疏与低精度", ("quant", "compress", "sparse", "prun", "压缩", "量化", "稀疏")),
        ),
    ),
    TaxonomyRule(
        "reasoning",
        "推理、规划与反思",
        "研究模型或智能体如何分解任务、搜索解法和纠正中间过程。",
        "不把仅有普通前向预测、且没有规划或推理过程的工作归入本方向。",
        ("reasoning planning", "test-time search", "self reflection"),
        ("reasoning", "planning", "chain-of-thought", "reflection", "deliberation", "decision", "test-time", "推理", "规划", "反思", "决策"),
        (
            ("planning", "任务规划与搜索", ("planning", "search", "decision", "规划", "搜索", "决策")),
            ("reflection", "反思与自我修正", ("reflection", "self-correct", "critique", "反思", "修正")),
            ("inference_compute", "推理时计算", ("reasoning", "test-time", "inference", "chain-of-thought", "推理")),
        ),
    ),
    TaxonomyRule(
        "agents_tools",
        "Agent 架构与工具使用",
        "研究智能体架构、工具调用、工作流和多智能体协作。",
        "不把没有自主决策、工具或交互循环的普通语言模型应用归入本方向。",
        ("agent tool use", "multi-agent orchestration", "agent memory"),
        ("agent", "multi-agent", "tool use", "function calling", "workflow", "orchestration", "autonomous", "agent memory", "智能体", "多智能体", "工具调用"),
        (
            ("tool_use", "工具调用与工作流", ("tool", "function", "workflow", "工具", "工作流")),
            ("multi_agent", "多智能体协作", ("multi-agent", "collabor", "orchestrat", "多智能体", "协作")),
            ("agent_memory", "记忆与状态管理", ("memory", "context", "state", "记忆", "状态")),
        ),
    ),
    TaxonomyRule(
        "retrieval_knowledge",
        "检索、知识与上下文",
        "研究外部检索、知识注入、证据定位和长上下文组织。",
        "不把仅使用训练参数中的知识、没有外部上下文机制的论文归入本方向。",
        ("retrieval augmented generation", "knowledge grounding", "long context"),
        ("retrieval", "rag", "knowledge", "grounding", "context", "document", "search", "检索", "知识", "上下文", "文档"),
        (
            ("retrieval", "检索与证据定位", ("retrieval", "search", "document", "检索", "搜索")),
            ("grounding", "知识增强与事实对齐", ("knowledge", "rag", "ground", "知识", "事实")),
            ("context", "长上下文组织", ("context", "long", "上下文", "长文本")),
        ),
    ),
    TaxonomyRule(
        "learning",
        "训练、适配与对齐",
        "研究参数适配、强化学习、偏好优化、蒸馏和持续改进。",
        "不把仅改变推理提示、没有训练或参数适配的工作归入本方向。",
        ("fine tuning alignment", "reinforcement learning", "model distillation"),
        ("training", "fine-tuning", "learning", "reinforcement", "alignment", "preference", "adaptation", "distillation", "训练", "微调", "强化学习", "对齐", "蒸馏"),
        (
            ("finetuning", "参数适配与微调", ("fine-tun", "adapt", "lora", "微调", "适配")),
            ("rl", "强化学习与偏好优化", ("reinforcement", "preference", "reward", "强化学习", "偏好")),
            ("distill", "蒸馏与自我改进", ("distill", "self-improv", "蒸馏", "自我改进")),
        ),
    ),
    TaxonomyRule(
        "evaluation_safety",
        "评测、安全与可靠性",
        "研究能力评测、鲁棒性、安全风险、幻觉和可解释性。",
        "不把只把基准作为结果表、没有评测方法或可靠性问题的论文归入本方向。",
        ("evaluation benchmark", "safety robustness", "hallucination reliability"),
        ("benchmark", "evaluation", "safety", "robust", "hallucination", "attack", "trust", "interpretability", "评测", "安全", "鲁棒", "幻觉", "可靠"),
    ),
    TaxonomyRule(
        "multimodal_embodied",
        "多模态与具身智能",
        "研究文本与视觉、语音、机器人环境之间的联合感知和行动。",
        "不把纯文本任务或只使用单一结构化输入的论文归入本方向。",
        ("multimodal agent", "vision language", "embodied robotics"),
        ("multimodal", "vision-language", "visual", "audio", "embodied", "robot", "多模态", "视觉", "语音", "具身", "机器人"),
    ),
    TaxonomyRule(
        "applications",
        "领域应用与科学发现",
        "研究方法在医疗、软件、科学、教育等具体领域中的适配和验证。",
        "不把没有领域数据、任务或评价的通用方法论文归入本方向。",
        ("scientific applications", "medical applications", "software engineering"),
        ("medical", "health", "code", "software", "science", "scientific", "biology", "chemistry", "education", "医疗", "代码", "科学", "教育"),
    ),
    TaxonomyRule(
        "foundations",
        "基础方法与模型架构",
        "研究主题的基础定义、核心计算机制和通用模型架构。",
        "已有更具体方向证据时优先归入具体方向，避免把所有论文都放进基础方法。",
        ("foundations architecture", "core mechanism", "survey taxonomy"),
        ("architecture", "framework", "mechanism", "model", "transformer", "attention", "survey", "taxonomy", "架构", "机制", "模型", "综述"),
    ),
)


@dataclass(frozen=True)
class DirectionPlan:
    key: str
    label: str
    definition: str
    boundary: str
    query_terms: tuple[str, ...]
    match_terms: tuple[str, ...]
    seed_paper_ids: tuple[str, ...] = ()
    subdirections: tuple[tuple[str, str, tuple[str, ...]], ...] = ()


@dataclass
class DirectionResearchOutcome:
    plan: DirectionPlan
    papers: list[PaperRecord] = field(default_factory=list)
    provider_name: str = "unknown"
    retrieved_count: int = 0
    rejected_count: int = 0
    truncated_count: int = 0
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None


@dataclass
class DirectionExpansionDecision:
    direction_key: str
    decision: DirectionDecision
    reason: str
    paper_ids: list[str] = field(default_factory=list)
    subgroups: dict[str, list[str]] = field(default_factory=dict)
    subgroup_labels: dict[str, str] = field(default_factory=dict)
    merge_target: str | None = None


@dataclass
class DirectionPipelineResult:
    plans: list[DirectionPlan]
    outcomes: list[DirectionResearchOutcome]
    decisions: list[DirectionExpansionDecision]
    papers: list[PaperRecord]
    paper_direction: dict[str, str]
    provider_name: str
    partial: bool
    warnings: list[str]

    def plan_by_key(self) -> dict[str, DirectionPlan]:
        return {plan.key: plan for plan in self.plans}

    def decision_by_key(self) -> dict[str, DirectionExpansionDecision]:
        return {decision.direction_key: decision for decision in self.decisions}

    def audit_lines(self) -> list[str]:
        decisions = self.decision_by_key()
        lines: list[str] = []
        for outcome in self.outcomes:
            decision = decisions[outcome.plan.key]
            query = " | ".join(outcome.plan.query_terms)
            detail = (
                f"方向审计[{outcome.plan.label}]：decision={decision.decision}；"
                f"provider={outcome.provider_name}；检索词={query}；"
                f"返回={outcome.retrieved_count}，接纳={len(outcome.papers)}，"
                f"拒绝={outcome.rejected_count}，上限截断={outcome.truncated_count}；"
                f"原因={decision.reason}"
            )
            if decision.merge_target:
                detail += f"；merge_target={decision.merge_target}"
            if outcome.error:
                detail += f"；error={outcome.error}"
            lines.append(detail[:2000])
        return lines


@dataclass(frozen=True)
class SectionReadResult:
    attempted: bool
    sections: dict[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    pdf_url: str | None = None


class TopicTaxonomyPlanner:
    """Create bounded direction hypotheses from the retained corpus.

    Empty hypotheses are allowed at this stage and are subsequently audited as
    ``discard``.  This avoids pretending that a direction is supported before
    its dedicated query has run.
    """

    def __init__(self, rules: Sequence[TaxonomyRule] = TAXONOMY_RULES) -> None:
        self.rules = tuple(rules)

    def plan(
        self,
        topic: str,
        papers: Sequence[PaperRecord],
        prior_queries: Sequence[str],
        *,
        max_directions: int,
    ) -> list[DirectionPlan]:
        corpus = " ".join(
            [topic, *prior_queries, *(f"{paper.title} {paper.abstract}" for paper in papers)]
        ).casefold()
        scored: list[tuple[int, int, TaxonomyRule]] = []
        for index, rule in enumerate(self.rules):
            score = sum(corpus.count(term.casefold()) for term in rule.match_terms)
            scored.append((score, -index, rule))
        scored.sort(reverse=True, key=lambda item: (item[0], item[1]))

        # Six hypotheses provide useful breadth under the default request.  A
        # smaller explicit max is respected; unsupported hypotheses disappear
        # after direction research rather than becoming graph nodes.
        target = min(max_directions, max(1, min(6, len(self.rules))))
        selected = [item[2] for item in scored[:target]]
        unmatched = [
            paper
            for paper in papers
            if not any(_paper_rule_score(rule, paper) > 0 for rule in selected)
        ]
        other_seed_ids: tuple[str, ...] = ()
        if unmatched:
            # Preserve source papers under an explicit catch-all rather than
            # silently forcing them into an unsupported scientific category.
            selected = selected[:-1]
            matched_ids = {
                paper.id
                for paper in papers
                if any(_paper_rule_score(rule, paper) > 0 for rule in selected)
            }
            other_seed_ids = tuple(paper.id for paper in papers if paper.id not in matched_ids)
        plans: list[DirectionPlan] = []
        for rule in selected:
            seed_ids = tuple(
                paper.id for paper in papers if _paper_rule_score(rule, paper) > 0
            )
            query_terms = tuple(
                _clean_query(f"{topic} {phrase}") for phrase in rule.search_phrases[:1]
            )
            plans.append(
                DirectionPlan(
                    key=rule.key,
                    label=rule.label,
                    definition=rule.definition,
                    boundary=rule.boundary,
                    query_terms=query_terms,
                    match_terms=rule.match_terms,
                    seed_paper_ids=seed_ids,
                    subdirections=rule.subdirections,
                )
            )
        if other_seed_ids:
            topic_terms = tuple(
                token for token in re.findall(r"[\w-]+", topic.casefold()) if len(token) >= 2
            ) or (topic.casefold(),)
            plans.append(
                DirectionPlan(
                    key="other",
                    label="其他待核验方向",
                    definition="保留尚未被当前分类规则覆盖的原分析论文。",
                    boundary="该节点不是成熟分类结论；需要研究者检查或重新命名。",
                    query_terms=(_clean_query(f"{topic} related work"),),
                    match_terms=topic_terms,
                    seed_paper_ids=other_seed_ids,
                )
            )
        return plans

    def validate_model_plans(
        self,
        raw_directions: Sequence[object],
        papers: Sequence[PaperRecord],
        *,
        max_directions: int,
    ) -> list[DirectionPlan]:
        """Turn an untrusted model taxonomy into bounded domain plans."""

        known_papers = {paper.id for paper in papers}
        plans: list[DirectionPlan] = []
        used_keys: set[str] = set()
        for index, raw in enumerate(raw_directions[:max_directions]):
            if not isinstance(raw, dict):
                continue
            label = " ".join(str(raw.get("label") or "").split())[:500]
            definition = " ".join(str(raw.get("definition") or "").split())[:2000]
            boundary = " ".join(str(raw.get("boundary") or "").split())[:2000]
            if not label or not definition or not boundary:
                continue
            requested = re.sub(
                r"[^a-z0-9_-]+",
                "-",
                str(raw.get("key") or f"model-{index}").casefold(),
            ).strip("-")[:100]
            key = requested or f"model-{index}"
            suffix = 2
            while key in used_keys:
                key = f"{requested or f'model-{index}'}-{suffix}"
                suffix += 1
            query_terms = tuple(dict.fromkeys(
                _clean_query(value)
                for value in raw.get("query_terms", [])[:3]
                if isinstance(value, str) and 2 <= len(_clean_query(value)) <= 160
            ))
            match_terms = tuple(dict.fromkeys(
                " ".join(value.split()).casefold()[:100]
                for value in raw.get("match_terms", [])[:40]
                if isinstance(value, str) and len(value.strip()) >= 2
            ))
            if not query_terms or len(match_terms) < 2:
                continue
            seed_ids = tuple(dict.fromkeys(
                value for value in raw.get("seed_paper_ids", [])
                if isinstance(value, str) and value in known_papers
            ))[:80]
            subdirections: list[tuple[str, str, tuple[str, ...]]] = []
            for sub_index, sub in enumerate(raw.get("subdirections", [])[:3]):
                if not isinstance(sub, dict):
                    continue
                sub_label = " ".join(str(sub.get("label") or "").split())[:300]
                sub_terms = tuple(
                    " ".join(value.split()).casefold()[:100]
                    for value in sub.get("match_terms", [])[:20]
                    if isinstance(value, str) and len(value.strip()) >= 2
                )
                if not sub_label or not sub_terms:
                    continue
                sub_key = re.sub(
                    r"[^a-z0-9_-]+", "-", str(sub.get("key") or f"sub-{sub_index}").casefold()
                ).strip("-")[:100] or f"sub-{sub_index}"
                subdirections.append((sub_key, sub_label, sub_terms))
            used_keys.add(key)
            plans.append(
                DirectionPlan(
                    key=key,
                    label=label,
                    definition=definition,
                    boundary=boundary,
                    query_terms=query_terms,
                    match_terms=match_terms,
                    seed_paper_ids=seed_ids,
                    subdirections=tuple(subdirections),
                )
            )
        return plans


class _StartRateLimiter:
    """Serialize request *starts* without serializing network response time."""

    def __init__(
        self,
        interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.interval_seconds = max(0.0, interval_seconds)
        self._clock = clock
        self._sleep = sleep
        self._next_start = 0.0
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            delay = self._next_start - now
            if delay > 0:
                self._sleep(delay)
                now = self._clock()
            self._next_start = max(now, self._next_start) + self.interval_seconds


class SharedSearchCoordinator:
    """One provider instance and one limiter shared by all direction workers."""

    def __init__(
        self,
        provider: SearchProvider,
        *,
        max_concurrency: int = 4,
        minimum_interval_seconds: float | None = None,
    ) -> None:
        self.provider = provider
        self.max_concurrency = max(1, min(4, max_concurrency))
        if minimum_interval_seconds is None:
            minimum_interval_seconds = 3.0 if provider.name == "arxiv" else 0.0
        self._limiter = _StartRateLimiter(minimum_interval_seconds)
        self._semaphore = BoundedSemaphore(self.max_concurrency)

    def search(self, query: str, limit: int) -> list[PaperRecord]:
        with self._semaphore:
            self._limiter.wait()
            return self.provider.search(query, limit)


class DirectionResearchAgent:
    """A deterministic direction worker; no model call is implied."""

    def __init__(self, search: SharedSearchCoordinator) -> None:
        self.search = search

    def run(
        self,
        plan: DirectionPlan,
        seed_papers: Sequence[PaperRecord],
        *,
        paper_limit: int,
    ) -> DirectionResearchOutcome:
        started_at = datetime.now(timezone.utc)
        started_perf = time.perf_counter()
        seed_by_id = {_paper_identity(paper): paper for paper in seed_papers}
        accepted = dict(seed_by_id)
        retrieved_count = 0
        rejected_count = 0
        error: str | None = None
        for query in plan.query_terms:
            try:
                found = self.search.search(query, paper_limit)
            except Exception as exc:  # noqa: BLE001 - direction failure is durable partial state
                error = _safe_error(exc)
                break
            retrieved_count += len(found)
            for paper in found:
                identity = _paper_identity(paper)
                if identity in accepted:
                    accepted[identity] = _prefer_paper(accepted[identity], paper)
                    continue
                if _paper_rule_score_from_terms(plan.match_terms, paper) <= 0:
                    rejected_count += 1
                    continue
                accepted[identity] = paper
        all_accepted = list(accepted.values())
        papers = all_accepted[:paper_limit]
        return DirectionResearchOutcome(
            plan=plan,
            papers=papers,
            provider_name=self.search.provider.name,
            retrieved_count=retrieved_count,
            rejected_count=rejected_count,
            truncated_count=max(0, len(all_accepted) - len(papers)),
            error=error,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            duration_ms=max(0, round((time.perf_counter() - started_perf) * 1000)),
        )


class DirectionExpansionAgent:
    """Make explicit split/keep/merge/discard decisions from accepted papers."""

    def decide(
        self,
        plans: Sequence[DirectionPlan],
        outcomes: Sequence[DirectionResearchOutcome],
    ) -> tuple[list[DirectionExpansionDecision], dict[str, str]]:
        # A paper is one entity even if several direction queries found it.
        candidates: dict[str, list[str]] = defaultdict(list)
        paper_by_identity: dict[str, PaperRecord] = {}
        for outcome in outcomes:
            for paper in outcome.papers:
                identity = _paper_identity(paper)
                candidates[identity].append(outcome.plan.key)
                paper_by_identity[identity] = _prefer_paper(
                    paper_by_identity.get(identity), paper
                )

        order = {plan.key: index for index, plan in enumerate(plans)}
        plans_by_key = {plan.key: plan for plan in plans}
        owner_by_identity: dict[str, str] = {}
        for identity, candidate_keys in candidates.items():
            paper = paper_by_identity[identity]
            owner_by_identity[identity] = max(
                candidate_keys,
                key=lambda key: (
                    _paper_rule_score_from_terms(plans_by_key[key].match_terms, paper),
                    -order[key],
                ),
            )

        owned: dict[str, list[PaperRecord]] = defaultdict(list)
        for identity, key in owner_by_identity.items():
            owned[key].append(paper_by_identity[identity])

        decisions: list[DirectionExpansionDecision] = []
        for outcome in outcomes:
            plan = outcome.plan
            papers = owned.get(plan.key, [])
            if not papers:
                overlapping_owners = [
                    owner_by_identity[_paper_identity(paper)]
                    for paper in outcome.papers
                    if owner_by_identity.get(_paper_identity(paper)) != plan.key
                ]
                if overlapping_owners:
                    target = Counter(overlapping_owners).most_common(1)[0][0]
                    decisions.append(
                        DirectionExpansionDecision(
                            direction_key=plan.key,
                            decision="merge",
                            reason="本方向接纳的论文均与另一方向重复，为避免复制论文实体而合并。",
                            merge_target=target,
                        )
                    )
                else:
                    reason = (
                        "方向专属检索失败且没有种子论文，当前证据不足。"
                        if outcome.error
                        else "方向专属检索没有得到符合边界的论文，当前证据不足。"
                    )
                    decisions.append(
                        DirectionExpansionDecision(
                            direction_key=plan.key,
                            decision="discard",
                            reason=reason,
                        )
                    )
                continue

            subgroups, labels = _subgroup_papers(plan, papers)
            substantial_groups = [items for items in subgroups.values() if items]
            if len(substantial_groups) >= 2 and len(papers) >= 3:
                decision: DirectionDecision = "split"
                reason = f"{len(papers)} 篇论文形成 {len(substantial_groups)} 个可区分的方法/问题簇。"
            else:
                decision = "keep"
                reason = (
                    "当前论文数量或方法差异不足以可靠细分，保留为一级方向。"
                )
                # A keep node still needs one leaf route so papers remain leaves
                # without pretending a supported taxonomy split exists.
                subgroups = {"papers": [paper.id for paper in papers]}
                labels = {"papers": "代表论文"}
            decisions.append(
                DirectionExpansionDecision(
                    direction_key=plan.key,
                    decision=decision,
                    reason=reason,
                    paper_ids=[paper.id for paper in papers],
                    subgroups=subgroups,
                    subgroup_labels=labels,
                )
            )
        return decisions, {
            paper_by_identity[identity].id: key for identity, key in owner_by_identity.items()
        }


class DirectionResearchCoordinator:
    """Run bounded direction workers and return an auditable corpus."""

    def __init__(
        self,
        provider: SearchProvider,
        *,
        max_concurrency: int = 4,
        minimum_interval_seconds: float | None = None,
    ) -> None:
        self.search = SharedSearchCoordinator(
            provider,
            max_concurrency=max_concurrency,
            minimum_interval_seconds=minimum_interval_seconds,
        )
        self.max_concurrency = self.search.max_concurrency

    def research(
        self,
        plans: Sequence[DirectionPlan],
        seed_papers: Sequence[PaperRecord],
        *,
        papers_per_direction: int,
        max_total_papers: int,
    ) -> DirectionPipelineResult:
        seed_by_id = {paper.id: paper for paper in seed_papers}
        outcomes_by_key: dict[str, DirectionResearchOutcome] = {}

        def run_one(plan: DirectionPlan) -> DirectionResearchOutcome:
            seeds = [seed_by_id[item] for item in plan.seed_paper_ids if item in seed_by_id]
            return DirectionResearchAgent(self.search).run(
                plan,
                seeds,
                paper_limit=papers_per_direction,
            )

        workers = max(1, min(self.max_concurrency, len(plans)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="wishforge-direction") as pool:
            futures = {pool.submit(run_one, plan): plan for plan in plans}
            for future in as_completed(futures):
                plan = futures[future]
                try:
                    outcomes_by_key[plan.key] = future.result()
                except Exception as exc:  # defensive: one worker never erases successful peers
                    outcomes_by_key[plan.key] = DirectionResearchOutcome(
                        plan=plan,
                        provider_name=self.search.provider.name,
                        error=_safe_error(exc),
                    )
        outcomes = [outcomes_by_key[plan.key] for plan in plans]
        decisions, paper_direction = DirectionExpansionAgent().decide(plans, outcomes)

        decision_by_key = {item.direction_key: item for item in decisions}
        all_by_id: dict[str, PaperRecord] = {}
        for outcome in outcomes:
            for paper in outcome.papers:
                all_by_id[paper.id] = _prefer_paper(all_by_id.get(paper.id), paper)
        merged: dict[str, PaperRecord] = {}
        ordered: list[str] = []
        for decision in decisions:
            if decision.decision not in {"split", "keep"}:
                continue
            for paper_id in decision.paper_ids:
                paper = all_by_id.get(paper_id)
                if paper is None:
                    continue
                identity = _paper_identity(paper)
                if identity not in merged:
                    ordered.append(identity)
                merged[identity] = _prefer_paper(merged.get(identity), paper)
        all_unique_papers = [merged[identity] for identity in ordered]
        papers = all_unique_papers[:max_total_papers]
        allowed_paper_ids = {paper.id for paper in papers}
        paper_direction = {
            paper_id: key for paper_id, key in paper_direction.items() if paper_id in allowed_paper_ids
        }
        # Trim decisions after the global bound so graph counts cannot exceed
        # the request even when every direction returns its local maximum.
        for decision in decisions:
            decision.paper_ids = [item for item in decision.paper_ids if item in allowed_paper_ids]
            decision.subgroups = {
                key: [item for item in items if item in allowed_paper_ids]
                for key, items in decision.subgroups.items()
                if any(item in allowed_paper_ids for item in items)
            }

        failed = [outcome for outcome in outcomes if outcome.error]
        warnings = []
        supported = any(
            decision.decision in {"split", "keep"} and decision.paper_ids
            for decision in decisions
        )
        if failed:
            warnings.append(
                f"{len(failed)}/{len(outcomes)} 个方向的专属检索失败；已保留成功方向和原分析论文，任务标记为 partial。"
            )
        local_truncations = sum(outcome.truncated_count for outcome in outcomes)
        if local_truncations:
            warnings.append(
                f"方向级论文数量上限共截断 {local_truncations} 个候选；截断项未进入图谱。"
            )
        if len(all_unique_papers) > len(papers):
            warnings.append(
                f"总论文上限截断 {len(all_unique_papers) - len(papers)} 个候选；截断项未进入图谱。"
            )
        return DirectionPipelineResult(
            plans=list(plans),
            outcomes=outcomes,
            decisions=decisions,
            papers=papers,
            paper_direction=paper_direction,
            provider_name=self.search.provider.name,
            # If every direction failed and no retained seed supports a graph,
            # there is no useful partial result; the service will fail graph
            # validation instead of returning an empty success shell.
            partial=bool(failed) and supported,
            warnings=warnings,
        )


def build_search_provider(provider_name: str, settings=None) -> SearchProvider | None:
    """Recreate the analysis search provider without crossing API-key scopes.

    Overview jobs are created after the original HTTP request has returned, so
    they cannot safely capture request dependencies.  The provider name stored
    in ``AnalysisResult.provider`` is sufficient for arXiv and demo, neither of
    which requires a secret.  Semantic Scholar may need the separately scoped
    paper key; callers deliberately receive ``None`` here instead of silently
    issuing unauthenticated requests or borrowing another provider's key.
    """

    normalized = provider_name.casefold().strip()
    if "search=arxiv" in normalized or normalized == "arxiv":
        from app.services.research_providers import ArxivSearchProvider

        # The shared coordinator owns the start-rate limiter.  Disable the
        # provider's second interval so concurrent workers do not race on its
        # unprotected timestamp or sleep twice.
        return ArxivSearchProvider(
            minimum_interval_seconds=0.0,
            endpoint=getattr(settings, "paper_base_url", None) if settings is not None else None,
        )
    if "search=demo" in normalized or normalized == "demo":
        from app.services.research_providers import DemoSearchProvider

        return DemoSearchProvider()
    if "search=semantic_scholar" in normalized or normalized == "semantic_scholar":
        # The Overview worker may safely reuse the live paper key captured by
        # the request. It remains scoped to paper_search and is never copied
        # into the durable job payload.
        from app.services.research_providers import SemanticScholarProvider

        api_key = None
        if settings is not None and getattr(settings, "paper_api_key", None):
            api_key = settings.paper_api_key.get_secret_value()
        # A Semantic Scholar overview cannot safely issue anonymous requests:
        # the public quota is very small and the old contract intentionally
        # fell back to retained analysis papers when the paper key was absent.
        # Keep that boundary even when a live Settings object is available.
        if not api_key:
            return None
        return SemanticScholarProvider(
            api_key=api_key,
            endpoint=getattr(settings, "paper_base_url", None) if settings is not None else None,
        )
    return None


class OpenArxivSectionReader:
    """Download and extract selected sections from a legal open arXiv PDF.

    The reader never follows an arbitrary paper URL: it derives a canonical
    HTTPS PDF URL only from an arXiv identifier.  Download and extraction are
    bounded to 30 seconds, 20 MiB and a finite text budget.  It uses textual
    PDF extraction (optional pypdf or ``pdftotext``); OCR is intentionally not
    attempted.  Every failure returns an explicit warning so callers can fall
    back to the abstract without claiming full-text reading.
    """

    MAX_PDF_BYTES = 20 * 1024 * 1024
    MAX_TEXT_CHARS = 2_000_000
    MAX_SECTION_CHARS = 45_000
    DOWNLOAD_TIMEOUT_SECONDS = 30.0
    EXTRACT_TIMEOUT_SECONDS = 30.0
    USER_AGENT = "WishForge/0.1 (open arXiv section reader)"

    def __init__(
        self,
        *,
        downloader: Callable[[str], bytes] | None = None,
        text_extractor: Callable[[bytes], str] | None = None,
    ) -> None:
        self._downloader = downloader or self._download
        self._text_extractor = text_extractor or self._extract_text

    def read(self, paper: PaperRecord) -> SectionReadResult:
        arxiv_id = _arxiv_id(paper)
        if not arxiv_id or paper.source_kind != "academic":
            return SectionReadResult(attempted=False)
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        try:
            payload = self._downloader(pdf_url)
            if len(payload) > self.MAX_PDF_BYTES:
                raise ValueError("PDF 超过 20 MB 上限")
            if not payload.startswith(b"%PDF-"):
                raise ValueError("响应不是可识别的 PDF")
            text = self._text_extractor(payload)
            if not text.strip():
                raise ValueError("PDF 没有可抽取文本；按无 OCR 策略停止")
            sections = _split_research_sections(text[: self.MAX_TEXT_CHARS])
            if not sections:
                raise ValueError("未识别到 Introduction/Method/Experiment/Discussion/Conclusion 章节")
            return SectionReadResult(
                attempted=True,
                sections=sections,
                warnings=("PDF 使用文本层抽取，未进行 OCR；章节边界需人工核验。",),
                pdf_url=pdf_url,
            )
        except Exception as exc:  # noqa: BLE001 - expected bounded fallback
            return SectionReadResult(
                attempted=True,
                warnings=(f"arXiv PDF 章节读取失败，已退回摘要级：{_safe_error(exc)}",),
                pdf_url=pdf_url,
            )

    def _download(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"arxiv.org", "www.arxiv.org"}:
            raise ValueError("只允许下载规范的 HTTPS arXiv PDF")
        timeout = httpx.Timeout(self.DOWNLOAD_TIMEOUT_SECONDS)
        chunks: list[bytes] = []
        size = 0
        with httpx.stream(
            "GET",
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": self.USER_AGENT, "Accept": "application/pdf"},
        ) as response:
            response.raise_for_status()
            final_host = response.url.host.casefold()
            if final_host != "arxiv.org" and not final_host.endswith(".arxiv.org"):
                raise ValueError("arXiv PDF 重定向到了未允许的主机")
            declared = response.headers.get("content-length")
            if declared and int(declared) > self.MAX_PDF_BYTES:
                raise ValueError("PDF 超过 20 MB 上限")
            for chunk in response.iter_bytes(64 * 1024):
                size += len(chunk)
                if size > self.MAX_PDF_BYTES:
                    raise ValueError("PDF 超过 20 MB 上限")
                chunks.append(chunk)
        return b"".join(chunks)

    def _extract_text(self, payload: bytes) -> str:
        # Optional pure-Python path.  This import is deliberately lazy so the
        # application still runs when pypdf is not packaged.
        try:
            pypdf = importlib.import_module("pypdf")
        except ImportError:
            pypdf = None
        if pypdf is not None:
            # pypdf has no built-in parse timeout.  Run the bounded extraction
            # in a daemon-backed future so the Overview worker can fall back to
            # the abstract after 30 seconds instead of hanging indefinitely on
            # a malformed or adversarial PDF.  We intentionally do not wait for
            # the timed-out future during executor shutdown.
            executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="wishforge-pypdf",
            )
            future = executor.submit(self._extract_with_pypdf, pypdf, payload)
            try:
                return future.result(timeout=self.EXTRACT_TIMEOUT_SECONDS)
            except FutureTimeoutError as exc:
                future.cancel()
                raise TimeoutError("pypdf 文本抽取超过 30 秒上限") from exc
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        executable = shutil.which("pdftotext")
        if not executable:
            raise RuntimeError("未安装 pypdf 或 pdftotext，无法读取 PDF 文本层")
        with tempfile.TemporaryDirectory(prefix="wishforge-arxiv-") as directory:
            pdf_path = Path(directory) / "paper.pdf"
            pdf_path.write_bytes(payload)
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            completed = subprocess.run(
                [executable, "-layout", str(pdf_path), "-"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.EXTRACT_TIMEOUT_SECONDS,
                creationflags=creation_flags,
            )
            if completed.returncode != 0:
                detail = completed.stderr.decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"pdftotext 失败：{detail or completed.returncode}")
            return completed.stdout.decode("utf-8", errors="replace")[: self.MAX_TEXT_CHARS]

    def _extract_with_pypdf(self, pypdf, payload: bytes) -> str:
        reader = pypdf.PdfReader(io.BytesIO(payload))
        pieces: list[str] = []
        length = 0
        for page in reader.pages[:160]:
            page_text = page.extract_text() or ""
            pieces.append(page_text)
            length += len(page_text)
            if length >= self.MAX_TEXT_CHARS:
                break
        return "\n".join(pieces)[: self.MAX_TEXT_CHARS]


def _split_research_sections(text: str) -> dict[str, str]:
    aliases = (
        ("Introduction", r"introduction"),
        ("Method", r"methods?|methodology|approach|proposed (?:method|approach|framework)|model architecture"),
        ("Experiment", r"experiments?|experimental (?:setup|results)|evaluation|results"),
        ("Discussion", r"discussion|limitations?|future work"),
        ("Conclusion", r"conclusions?|concluding remarks"),
    )
    heading_re = re.compile(
        r"^\s*(?:[IVXLC]+|\d+(?:\.\d+)*)?[.)]?\s*("
        + "|".join(f"(?P<s{index}>{pattern})" for index, (_, pattern) in enumerate(aliases))
        + r")\s*[:.]?\s*$",
        re.IGNORECASE,
    )
    sections: dict[str, list[str]] = defaultdict(list)
    current: str | None = None
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            if current and sections[current] and sections[current][-1] != "":
                sections[current].append("")
            continue
        match = heading_re.match(line)
        if match:
            for index, (canonical, _) in enumerate(aliases):
                if match.group(f"s{index}") is not None:
                    current = canonical
                    break
            continue
        if current:
            if sum(len(item) for item in sections[current]) < OpenArxivSectionReader.MAX_SECTION_CHARS:
                sections[current].append(line)
    result = {
        name: "\n".join(lines).strip()[: OpenArxivSectionReader.MAX_SECTION_CHARS]
        for name, lines in sections.items()
        # A legitimate Conclusion or Limitations section is sometimes only one
        # sentence.  Keep short-but-substantive sections while rejecting empty
        # headings and page furniture.
        if len(" ".join(lines)) >= 30
    }
    return result


def _subgroup_papers(
    plan: DirectionPlan, papers: Sequence[PaperRecord]
) -> tuple[dict[str, list[str]], dict[str, str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    labels: dict[str, str] = {}
    for paper in papers:
        text = f"{paper.title} {paper.abstract}".casefold()
        scored = [
            (sum(text.count(term.casefold()) for term in terms), key, label)
            for key, label, terms in plan.subdirections
        ]
        if scored:
            score, key, label = max(scored, key=lambda item: item[0])
        else:
            score, key, label = 0, "core_methods", "核心方法与代表工作"
        if score <= 0:
            key, label = "core_methods", "核心方法与代表工作"
        groups[key].append(paper.id)
        labels[key] = label
    return dict(groups), labels


def _paper_rule_score(rule: TaxonomyRule, paper: PaperRecord) -> int:
    return _paper_rule_score_from_terms(rule.match_terms, paper)


def _paper_rule_score_from_terms(terms: Sequence[str], paper: PaperRecord) -> int:
    text = f"{paper.title} {paper.abstract}".casefold()
    return sum(text.count(term.casefold()) for term in terms)


def _paper_identity(paper: PaperRecord) -> str:
    if paper.doi:
        return f"doi:{paper.doi.casefold().strip()}"
    if paper.arxiv_id:
        return f"arxiv:{re.sub(r'v\d+$', '', paper.arxiv_id.casefold())}"
    if paper.canonical_id:
        return f"canonical:{paper.canonical_id.casefold().strip()}"
    title = re.sub(r"[^a-z0-9]+", " ", paper.title.casefold()).strip()
    return f"title:{title or paper.id.casefold()}"


def _prefer_paper(current: PaperRecord | None, candidate: PaperRecord) -> PaperRecord:
    if current is None:
        return candidate
    current_score = (bool(current.abstract), bool(current.arxiv_id), len(current.abstract), bool(current.url))
    candidate_score = (bool(candidate.abstract), bool(candidate.arxiv_id), len(candidate.abstract), bool(candidate.url))
    return candidate if candidate_score > current_score else current


def _arxiv_id(paper: PaperRecord) -> str | None:
    raw = paper.arxiv_id
    if not raw and paper.url:
        match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#/]+)", paper.url, re.IGNORECASE)
        raw = match.group(1) if match else None
    if not raw and paper.id.casefold().startswith("arxiv:"):
        raw = paper.id.split(":", 1)[1]
    if not raw:
        return None
    raw = raw.removesuffix(".pdf")
    raw = re.sub(r"v\d+$", "", raw)
    if not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})", raw, re.IGNORECASE):
        return None
    return raw


def _clean_query(value: str) -> str:
    return " ".join(value.replace('"', " ").split())[:160]


def _safe_error(exc: Exception) -> str:
    """Persist a useful category without retaining provider response bodies.

    Provider exceptions can include URLs, request headers or upstream response
    excerpts.  The structured direction audit already records provider and
    query scope, so an exception class plus a bounded public classification is
    enough for retry/debug decisions and is safer than storing ``str(exc)``.
    """

    if isinstance(exc, ProviderUnavailable):
        return f"{type(exc).__name__}: provider unavailable"
    return f"{type(exc).__name__}: direction worker failed"


__all__ = [
    "DirectionExpansionAgent",
    "DirectionExpansionDecision",
    "DirectionPipelineResult",
    "DirectionPlan",
    "DirectionResearchAgent",
    "DirectionResearchCoordinator",
    "DirectionResearchOutcome",
    "OpenArxivSectionReader",
    "SectionReadResult",
    "SharedSearchCoordinator",
    "TAXONOMY_RULES",
    "TopicTaxonomyPlanner",
    "build_search_provider",
]
