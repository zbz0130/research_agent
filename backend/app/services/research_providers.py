import json
import re
import hashlib
from datetime import datetime, timezone
from collections.abc import Sequence
from typing import Protocol

import httpx

from app.research_schemas import (
    CommunitySignal,
    EvidenceCard,
    ExplanationResult,
    FutureWorkSignal,
    InnovationCandidate,
    PaperRecord,
)


class ProviderUnavailable(RuntimeError):
    """Raised when an external provider cannot be reached or understood."""


class SearchProvider(Protocol):
    name: str

    def search(self, concept: str, limit: int) -> list[PaperRecord]:
        ...


class ExplanationProvider(Protocol):
    name: str

    def explain(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        evidence: Sequence[EvidenceCard],
        audience: str,
        language: str,
    ) -> ExplanationResult:
        ...


class BrainstormProvider(Protocol):
    """Optional model capability used by the research-mode brainstorm agent."""

    name: str

    def brainstorm(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        evidence: Sequence[EvidenceCard],
        language: str,
    ) -> list[InnovationCandidate]:
        ...


class SynthesisProvider(Protocol):
    """Optional model capability for combining the three research branches."""

    name: str

    def synthesize_research(
        self,
        concept: str,
        community_signals: Sequence[CommunitySignal],
        model_ideas: Sequence[InnovationCandidate],
        future_work_signals: Sequence[FutureWorkSignal],
    ) -> tuple[str, list[InnovationCandidate]]:
        ...


class SemanticScholarProvider:
    name = "semantic_scholar"

    def __init__(self, api_key: str | None = None, timeout: float = 20.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def search(self, concept: str, limit: int) -> list[PaperRecord]:
        headers = {"User-Agent": "WishForge/0.1"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        params = {
            "query": concept,
            "limit": limit,
            "fields": "paperId,title,abstract,authors,year,venue,url,openAccessPdf,citationCount,externalIds",
        }
        try:
            response = httpx.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise ProviderUnavailable(f"Semantic Scholar 暂时不可用：{exc}") from exc

        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderUnavailable("Semantic Scholar 返回了无法解析的响应。") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data", []), list):
            raise ProviderUnavailable("Semantic Scholar 返回格式不符合预期。")

        records: list[PaperRecord] = []
        for item in payload.get("data", []):
            if not isinstance(item, dict):
                continue
            external_ids = item.get("externalIds") or {}
            open_access = item.get("openAccessPdf") or {}
            records.append(
                PaperRecord(
                    id=item.get("paperId") or external_ids.get("DOI") or item.get("title", "unknown"),
                    provider_id=item.get("paperId"),
                    canonical_id=external_ids.get("DOI") or item.get("paperId"),
                    arxiv_id=external_ids.get("ArXiv"),
                    title=item.get("title") or "未命名论文",
                    authors=[author.get("name", "") for author in item.get("authors", []) if author.get("name")],
                    year=item.get("year"),
                    venue=item.get("venue") or None,
                    abstract=item.get("abstract") or "",
                    url=item.get("url") or open_access.get("url"),
                    doi=external_ids.get("DOI"),
                    citation_count=item.get("citationCount"),
                    source=self.name,
                    source_kind="academic",
                    access_type="open_access" if open_access.get("url") else "abstract_only",
                    retrieved_at=datetime.now(timezone.utc),
                )
            )
        return records


class DemoSearchProvider:
    """Small transparent fixture so the first version works without credentials."""

    name = "demo"

    _fixtures = {
        "paged_attention": [
            PaperRecord(
                id="demo-vllm-paged-attention",
                title="vLLM: Easy, Fast, and Cheap LLM Serving with PagedAttention",
                authors=["Woosuk Kwon", "Zongyu Li"],
                year=2023,
                venue="ACM SOSP",
                abstract=(
                    "The paper presents vLLM, a high-throughput serving system for large language models. "
                    "PagedAttention manages the key-value cache as fixed-size pages, borrowing the idea of virtual memory "
                    "to reduce fragmentation and support efficient sharing during generation. "
                    "The authors report improved serving throughput while discussing scheduling and memory trade-offs."
                ),
                url="https://arxiv.org/abs/2309.06180",
                source="demo_fixture",
                source_kind="demo",
                access_type="demo",
            ),
            PaperRecord(
                id="demo-kv-cache-compression",
                title="Efficient KV Cache Compression for Long-Context Language Model Serving",
                authors=["WishForge demo fixture"],
                year=2024,
                venue="arXiv",
                abstract=(
                    "This fixture represents work on reducing key-value cache memory for long-context generation. "
                    "It highlights a common limitation: compression can lower memory use but may affect answer quality, "
                    "so sequence length, latency and accuracy should be evaluated together."
                ),
                url="https://arxiv.org/",
                source="demo_fixture",
                source_kind="demo",
                access_type="demo",
            ),
        ],
        "attention": [
            PaperRecord(
                id="demo-attention-vaswani",
                title="Attention Is All You Need",
                authors=["Ashish Vaswani", "Noam Shazeer"],
                year=2017,
                venue="NeurIPS",
                abstract=(
                    "The paper introduces the Transformer, an architecture based entirely on attention mechanisms. "
                    "Self-attention connects tokens in a sequence and avoids recurrence, enabling parallel training. "
                    "The authors report strong machine translation results while discussing computational trade-offs."
                ),
                url="https://arxiv.org/abs/1706.03762",
                source="demo_fixture",
                source_kind="demo",
                access_type="demo",
            ),
            PaperRecord(
                id="demo-attention-flash",
                title="FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness",
                authors=["Tri Dao", "Daniel Y. Fu"],
                year=2022,
                venue="NeurIPS",
                abstract=(
                    "FlashAttention computes exact attention with an IO-aware tiled algorithm. "
                    "The work targets the memory movement bottleneck of standard attention and reports faster training "
                    "and lower memory use without changing the mathematical attention operation."
                ),
                url="https://arxiv.org/abs/2205.14135",
                source="demo_fixture",
                source_kind="demo",
                access_type="demo",
            ),
        ],
        "lora": [
            PaperRecord(
                id="demo-lora-original",
                title="LoRA: Low-Rank Adaptation of Large Language Models",
                authors=["Edward J. Hu", "Yelong Shen"],
                year=2021,
                venue="ICLR",
                abstract=(
                    "LoRA freezes pretrained model weights and injects trainable low-rank matrices into Transformer layers. "
                    "The approach substantially reduces trainable parameters while maintaining competitive task quality. "
                    "The authors discuss rank selection and the limits of transferring a single adaptation across tasks."
                ),
                url="https://arxiv.org/abs/2106.09685",
                source="demo_fixture",
                source_kind="demo",
                access_type="demo",
            ),
        ],
    }

    def search(self, concept: str, limit: int) -> list[PaperRecord]:
        normalized = re.sub(r"[^a-z0-9]+", " ", concept.lower()).strip()
        aliases = {
            "paged_attention": {"pagedattention", "paged attention", "分页注意力", "分页机制", "kv cache", "kv缓存", "键值缓存"},
            "attention": {"注意力", "注意力机制", "self attention", "自注意力"},
            "lora": {"低秩适配", "低秩微调", "参数高效微调", "qlora"},
        }
        for key, papers in self._fixtures.items():
            if key in normalized or key in concept.lower() or any(
                alias in concept.lower() for alias in aliases.get(key, set())
            ):
                return papers[:limit]
        slug = re.sub(r"[^a-z0-9]+", "-", concept.lower()).strip("-")
        if not slug:
            slug = f"concept-{hashlib.sha1(concept.encode('utf-8')).hexdigest()[:10]}"
        return [
            PaperRecord(
                id=f"demo-{slug}",
                title=f"关于“{concept}”的示例研究资料",
                year=None,
                abstract=(
                    f"这是 WishForge 的演示资料占位项，用于展示“{concept}”的证据卡和概念图流程。"
                    "它不是实际论文，接入真实检索 Provider 后会被替换。"
                ),
                url=None,
                source="demo_fixture",
                source_kind="demo",
                access_type="demo",
            )
        ][:limit]


class RuleBasedExplanationProvider:
    name = "rule_based_fallback"

    def explain(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        evidence: Sequence[EvidenceCard],
        audience: str,
        language: str,
    ) -> ExplanationResult:
        evidence_text = evidence[0].excerpt if evidence else "当前还没有可用的文献证据。"
        related = _related_terms(concept, papers)
        return ExplanationResult(
            one_sentence=f"{concept} 是一个需要结合具体问题和证据来理解的科研概念。",
            intuitive=(
                f"可以先把“{concept}”看成一种解决特定研究问题的思路。"
                "它的具体作用、优点和限制，需要结合论文中的实验条件来判断。"
            ),
            technical=(
                f"当前为 {audience} 生成的第一版解释：{evidence_text}"
                "详细机制会在接入解释模型后，根据证据卡进一步展开。"
            ),
            evolution=[f"{paper.year or '未标年份'}：{paper.title}" for paper in papers[:5]],
            related_concepts=related,
            limitations=[
                "当前第一版主要使用摘要和元数据，不能替代对论文全文和实验细节的人工核验。",
                "规则回退解释不是模型生成结论，需等待解释模型配置后获得更丰富的分层说明。",
            ],
            evidence_ids=[item.id for item in evidence],
        )


class OpenAICompatibleExplanationProvider:
    name = "openai_compatible"

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 45.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def explain(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        evidence: Sequence[EvidenceCard],
        audience: str,
        language: str,
    ) -> ExplanationResult:
        evidence_payload = "\n\n".join(
            f"[{item.id}] {item.claim}\n关系：{item.relation}\n原文：{item.excerpt}" for item in evidence[:12]
        )
        paper_payload = "\n".join(f"- {paper.title} ({paper.year or 'n.d.'})" for paper in papers[:12])
        prompt = f"""
你是 WishForge 的科研概念解释器。请使用下方资料解释“{concept}”。
目标读者：{audience}；语言：{language}。
只能把资料支持的内容写成事实；证据不足时明确说证据不足。
必须返回 JSON，字段为：one_sentence、intuitive、technical、evolution（字符串数组）、
related_concepts（字符串数组）、limitations（字符串数组）、evidence_ids（证据卡 ID 数组）。

论文：
{paper_payload}

证据卡：
{evidence_payload}
""".strip()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "你是一名严谨、诚实、重视证据的科研教师。"},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ProviderUnavailable("解释模型返回的 content 不是字符串。")
            return ExplanationResult.model_validate_json(_strip_code_fence(content))
        except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ProviderUnavailable(f"解释模型暂时不可用：{exc}") from exc

    def brainstorm(
        self,
        concept: str,
        papers: Sequence[PaperRecord],
        evidence: Sequence[EvidenceCard],
        language: str,
    ) -> list[InnovationCandidate]:
        """Ask the configured compatible model for explicitly unverified ideas.

        This is a separate method from ``explain`` so the service can expose
        which model call produced a candidate and can fall back to the
        deterministic heuristic without pretending the two are equivalent.
        """

        paper_payload = "\n".join(
            f"- {paper.title} ({paper.year or 'n.d.'})\n  摘要：{paper.abstract[:900]}"
            for paper in papers[:10]
        )
        evidence_payload = "\n".join(
            f"[{item.id}] {item.claim}\n原文：{item.excerpt[:900]}" for item in evidence[:10]
        )
        prompt = f"""
你是 WishForge 的科研创新脑暴 Agent。围绕“{concept}”提出最多 3 个可检验的研究候选。
语言：{language}。只能把论文资料支持的内容当作背景，所有候选都必须标记为未验证。
返回 JSON 对象，唯一字段为 candidates；其值是对象数组。每个对象必须包含：
title、problem、mechanism、nearest_work（字符串数组）、novelty_level（只能是 L0/L1/L2/L3/L4）、
confidence（只能是 high/medium/low，建议 low）、feasibility（low/medium/high）、rationale、
validation_steps（字符串数组）、warning（字符串）。不要声称“保证原创”或“arXiv 没有”。

论文资料：
{paper_payload or '无'}

证据卡：
{evidence_payload or '无'}
""".strip()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0.4,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "你是一名严谨、保守、重视可复现性的科研方法专家。"},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ProviderUnavailable("创新脑暴模型返回的 content 不是字符串。")
            payload = json.loads(_strip_code_fence(content))
            raw_candidates = payload.get("candidates") if isinstance(payload, dict) else None
            if not isinstance(raw_candidates, list):
                raise ProviderUnavailable("创新脑暴模型没有返回 candidates 数组。")
            candidates: list[InnovationCandidate] = []
            for item in raw_candidates[:3]:
                if not isinstance(item, dict):
                    continue
                candidate = InnovationCandidate.model_validate(item).model_copy(
                    update={
                        "source_type": "model_generated",
                        "confidence": "low",
                        "warning": item.get("warning")
                        or "模型生成的待验证候选，不是已确认的新颖成果。",
                        "evidence_ids": [evidence_item.id for evidence_item in evidence],
                    }
                )
                candidates.append(candidate)
            if not candidates:
                raise ProviderUnavailable("创新脑暴模型返回的候选无法通过结构校验。")
            return candidates
        except ProviderUnavailable:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ProviderUnavailable(f"创新脑暴模型暂时不可用：{exc}") from exc

    def synthesize_research(
        self,
        concept: str,
        community_signals: Sequence[CommunitySignal],
        model_ideas: Sequence[InnovationCandidate],
        future_work_signals: Sequence[FutureWorkSignal],
    ) -> tuple[str, list[InnovationCandidate]]:
        """Synthesize bounded upstream artifacts into cautious candidates."""

        community_payload = "\n".join(
            f"- [{item.platform}] {item.title}\n  痛点：{item.pain_point}\n  问题：{item.open_question}"
            for item in community_signals[:8]
        )
        model_payload = "\n".join(
            f"- {item.title}\n  问题：{item.problem}\n  机制：{item.mechanism}"
            for item in model_ideas[:6]
        )
        future_payload = "\n".join(
            f"- {item.paper_title} [{item.section}]：{item.excerpt[:700]}"
            for item in future_work_signals[:8]
        )
        prompt = f"""
你是 WishForge 的研究综合 Agent。请综合以下三类输入，围绕“{concept}”生成最多 4 个
值得人工核验的创新候选。社区内容只能作为痛点信号，论文内容目前主要是摘要级线索。
不要声称全球唯一、保证原创或 arXiv 上不存在相同工作。
返回 JSON 对象，字段：summary（字符串）、candidates（对象数组）。candidates 每项必须包含：
title、problem、mechanism、nearest_work（字符串数组）、novelty_level（L0-L4）、confidence、
feasibility、rationale、validation_steps（字符串数组）、warning。

社区信号：
{community_payload or '无'}

模型脑暴：
{model_payload or '无'}

论文限制 / Future Work 线索：
{future_payload or '无'}
""".strip()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "你是一名保守、可审计的科研综述编辑。"},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ProviderUnavailable("研究综合模型返回的 content 不是字符串。")
            payload = json.loads(_strip_code_fence(content))
            if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
                raise ProviderUnavailable("研究综合模型没有返回 candidates 数组。")
            candidates: list[InnovationCandidate] = []
            for item in payload["candidates"][:4]:
                if not isinstance(item, dict):
                    continue
                candidates.append(
                    InnovationCandidate.model_validate(item).model_copy(
                        update={
                            "source_type": "synthesis",
                            "confidence": "low",
                            "warning": item.get("warning")
                            or "综合模型生成的待验证候选，不是已确认的新颖成果。",
                        }
                    )
                )
            if not candidates:
                raise ProviderUnavailable("研究综合模型返回的候选无法通过结构校验。")
            summary = payload.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                summary = f"模型综合了社区、脑暴和论文 Future Work 线索，形成 {len(candidates)} 个待验证候选。"
            return summary.strip()[:4000], candidates
        except ProviderUnavailable:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ProviderUnavailable(f"研究综合模型暂时不可用：{exc}") from exc


def _strip_code_fence(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return content.strip()


def _related_terms(concept: str, papers: Sequence[PaperRecord]) -> list[str]:
    known_terms = [
        "Self-Attention",
        "Cross-Attention",
        "Transformer",
        "FlashAttention",
        "LoRA",
        "参数高效微调",
        "长序列建模",
        "可复现性",
    ]
    haystack = " ".join([concept, *(paper.title for paper in papers)]).lower()
    matches = [term for term in known_terms if term.lower() in haystack]
    return matches[:8]
