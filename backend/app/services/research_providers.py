import re
import hashlib
from datetime import datetime, timezone
from collections.abc import Sequence
from typing import Protocol

import httpx

from app.research_schemas import ExplanationResult, EvidenceCard, PaperRecord


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
