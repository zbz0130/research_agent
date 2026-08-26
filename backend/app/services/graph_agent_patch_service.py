"""Natural-language concept-graph patch proposals.

The first version intentionally keeps this translator deterministic.  A model
provider can be added behind the same service later, but the safety boundary
does not change: the translator may only emit a small, typed set of graph
operations and :mod:`graph_service` validates the proposal before it is
persisted.  Agent proposals are never applied implicitly.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.research_schemas import (
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    ConceptNodeUpdate,
    GraphAgentPatchCreate,
    GraphOperation,
    GraphPatch,
    GraphPatchCreate,
)
from app.services.graph_service import GraphConflict, graph_service


MAX_REQUEST_CHARS = 2000
MAX_WARNING_COUNT = 8


@dataclass(frozen=True)
class _Translation:
    operations: list[GraphOperation]
    reason: str
    warnings: list[str]


class GraphAgentPatchService:
    """Turn a bounded natural-language request into a reviewed patch."""

    def propose(self, graph_id: str, payload: GraphAgentPatchCreate) -> GraphPatch:
        # ``GraphAgentPatchCreate`` already enforces this limit, but keeping a
        # second guard here protects direct Python callers that bypass FastAPI
        # validation.
        request = payload.request.strip()
        if len(request) < 3 or len(request) > MAX_REQUEST_CHARS:
            raise GraphConflict("Agent 修改请求长度必须在 3 到 2000 个字符之间")

        graph = graph_service.get(graph_id)
        expected_version = payload.base_version or graph.version
        if expected_version != graph.version:
            # create_patch performs the authoritative check again.  Failing
            # before translation avoids spending work on a stale proposal and
            # gives callers a predictable 409 response.
            raise GraphConflict(
                f"graph version changed: expected {expected_version}, current {graph.version}"
            )

        target = self._resolve_target(graph, request, payload.target_node_id)
        translation = self._translate(graph, target, request, payload.max_operations)
        if not translation.operations:
            # GraphPatch requires at least one operation.  This should only be
            # reachable if a future translator is added incorrectly.
            raise GraphConflict("Agent 没有生成可审阅的图谱操作")
        if len(translation.operations) > payload.max_operations:
            raise GraphConflict(
                f"Agent 提案最多允许 {payload.max_operations} 个操作，当前生成了 "
                f"{len(translation.operations)} 个"
            )

        patch_payload = GraphPatchCreate(
            actor="agent",
            base_version=expected_version,
            operations=translation.operations,
            reason=translation.reason,
            translation_mode="heuristic",
            source_request=request,
            warnings=translation.warnings[:MAX_WARNING_COUNT],
        )
        # GraphService performs the final root/lock/edge/version validation and
        # persists this as ``status=proposed`` without mutating the graph.
        return graph_service.create_patch(graph_id, patch_payload)

    def translate_for_graph(
        self,
        graph: ConceptGraph,
        payload: GraphAgentPatchCreate,
    ) -> GraphPatchCreate:
        """Translate against an embedded/transient graph without persisting it."""

        request = payload.request.strip()
        if len(request) < 3 or len(request) > MAX_REQUEST_CHARS:
            raise GraphConflict("Agent 修改请求长度必须在 3 到 2000 个字符之间")
        expected_version = payload.base_version or graph.version
        if expected_version != graph.version:
            raise GraphConflict(
                f"graph version changed: expected {expected_version}, current {graph.version}"
            )
        target = self._resolve_target(graph, request, payload.target_node_id)
        translation = self._translate(graph, target, request, payload.max_operations)
        return GraphPatchCreate(
            actor="agent",
            base_version=expected_version,
            operations=translation.operations,
            reason=translation.reason,
            translation_mode="heuristic",
            source_request=request,
            warnings=translation.warnings[:MAX_WARNING_COUNT],
        )

    @staticmethod
    def _resolve_target(
        graph: ConceptGraph,
        request: str,
        target_node_id: str | None,
    ) -> ConceptNode:
        by_id = {node.id: node for node in graph.nodes}
        if target_node_id:
            target = by_id.get(target_node_id)
            if target is None:
                raise GraphConflict("target_node_id 必须指向图中的现有节点")
            return target

        # Prefer an explicit node ID, then the longest matching label.  Longest
        # first prevents a generic root label such as “注意力” from winning
        # over a more specific child such as “空间注意力”.
        id_matches = [node for node in graph.nodes if node.id and node.id in request]
        if id_matches:
            return max(id_matches, key=lambda node: len(node.id))
        folded_request = request.casefold()
        label_matches = [
            node
            for node in graph.nodes
            if node.label and node.label.casefold() in folded_request
        ]
        if label_matches:
            return max(label_matches, key=lambda node: len(node.label))
        return by_id[graph.root_id]

    def _translate(
        self,
        graph: ConceptGraph,
        target: ConceptNode,
        request: str,
        max_operations: int,
    ) -> _Translation:
        normalized = request.lower()
        warnings = [
            "本次使用透明规则启发式翻译，未调用外部模型；复杂或有歧义的请求请人工检查操作预览。",
            "Agent 只生成待批准 GraphPatch，不会直接修改概念图。",
        ]

        if _contains_any(normalized, ("删除", "移除", "删掉", "delete", "remove")):
            operation = GraphOperation(op="remove_node", node_id=target.id)
            return _Translation(
                operations=[operation],
                reason=f"启发式 Agent 提案：根据请求移除节点“{_display_label(target.label)}”；等待用户批准。",
                warnings=warnings,
            )

        if _contains_any(normalized, ("重命名", "改名", "改为", "改成", "rename", "renamed")):
            new_label = _extract_new_label(request)
            if new_label:
                operation = GraphOperation(
                    op="update_node",
                    node_id=target.id,
                    updates=ConceptNodeUpdate(label=new_label),
                )
                return _Translation(
                    operations=[operation],
                    reason=(
                        f"启发式 Agent 提案：将节点“{_display_label(target.label)}”重命名为“{_display_label(new_label)}”；"
                        "等待用户批准。"
                    ),
                    warnings=warnings,
                )
            warnings.append("请求包含改名意图，但未识别出新的节点名称；已转为备注提案。")
            return self._fallback_note(target, request, warnings)

        if _contains_any(
            normalized,
            ("增加", "添加", "新增", "加入", "引入", "补充", "新建", "add", "insert", "create"),
        ):
            label = _extract_new_node_label(request)
            if label:
                return self._add_node(graph, target, label, request, max_operations, warnings)
            warnings.append("请求包含新增节点意图，但未识别出节点名称；已转为备注提案。")
            return self._fallback_note(target, request, warnings)

        summary = _extract_summary(request)
        if summary:
            operation = GraphOperation(
                op="update_node",
                node_id=target.id,
                updates=ConceptNodeUpdate(summary=summary),
            )
            return _Translation(
                operations=[operation],
                reason=f"启发式 Agent 提案：更新节点“{_display_label(target.label)}”的说明；等待用户批准。",
                warnings=warnings,
            )

        warnings.append("未识别出明确的新增、改名、删除或说明操作；已将原请求保存为节点备注，避免猜测结构性修改。")
        return self._fallback_note(target, request, warnings)

    @staticmethod
    def _add_node(
        graph: ConceptGraph,
        target: ConceptNode,
        label: str,
        request: str,
        max_operations: int,
        warnings: list[str],
    ) -> _Translation:
        label = _clean_label(label)
        if not label:
            warnings.append("节点名称为空，已转为备注提案。")
            return GraphAgentPatchService._fallback_note(target, request, warnings)

        existing = next((node for node in graph.nodes if node.label.casefold() == label.casefold()), None)
        if existing is not None:
            warnings.append(f"图中已经存在同名节点“{existing.label}”，未重复创建；改为补充其待核验说明。")
            return GraphAgentPatchService._fallback_note(existing, request, warnings)

        node_id = _unique_node_id(graph, label, request)
        node_type = _infer_node_type(label, request)
        summary = _candidate_summary(label, request)
        if max_operations < 2:
            warnings.append(
                "新增节点需要同时建立一条关系边；当前操作预算只有 1，"
                "已改为在目标节点保存待核验备注。"
            )
            return GraphAgentPatchService._fallback_note(target, request, warnings)
        operations = [
            GraphOperation(
                op="add_node",
                node=ConceptNode(
                    id=node_id,
                    label=label,
                    summary=summary,
                    node_type=node_type,
                    evidence_ids=[],
                    editable=True,
                ),
            )
        ]
        edge_id = _stable_edge_id(target.id, node_id)
        operations.append(
            GraphOperation(
                op="add_edge",
                edge=ConceptEdge(
                    id=edge_id,
                    source=target.id,
                    target=node_id,
                    relation="is_a" if node_type in {"method", "problem", "concept"} else "related_to",
                    evidence_ids=[],
                ),
            )
        )
        return _Translation(
            operations=operations,
            reason=(
                f"启发式 Agent 提案：在“{_display_label(target.label)}”下新增待核验节点“"
                f"{_display_label(label)}”；等待用户批准。"
            ),
            warnings=warnings,
        )

    @staticmethod
    def _fallback_note(
        target: ConceptNode,
        request: str,
        warnings: list[str],
    ) -> _Translation:
        marker = "Agent 请求（未解析，待人工核验）："
        addition = f"{marker}{request}"
        current = target.summary.strip()
        summary = f"{current}\n\n{addition}".strip() if current else addition
        # ConceptNodeUpdate caps summaries at 5000 characters.  Keep the
        # beginning of an existing explanation and the complete user request
        # whenever possible.
        summary = summary[:5000]
        return _Translation(
            operations=[
                GraphOperation(
                    op="update_node",
                    node_id=target.id,
                    updates=ConceptNodeUpdate(summary=summary),
                )
            ],
            reason=(
                f"启发式 Agent 提案：把请求作为节点“{_display_label(target.label)}”的待核验备注；"
                "等待用户批准。"
            ),
            warnings=warnings,
        )


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _quoted_values(value: str) -> list[str]:
    return [
        item.strip()
        for item in re.findall(r"[\"“「『](.{1,160}?)[\"”」』]", value)
        if item.strip()
    ]


def _extract_new_label(request: str) -> str | None:
    # The phrase after “改为/重命名为” is the least ambiguous signal.  Quote
    # marks are supported so names may contain spaces or punctuation.
    match = re.search(
        r"(?:重命名为|命名为|改为|改成|rename(?:\s+it)?\s+(?:to|as)|rename\s+[^\s]+\s+to)\s*[\"“「『]?"
        r"([^\"”」』。！？!?,，;；]{1,160})",
        request,
        flags=re.IGNORECASE,
    )
    if match:
        return _clean_label(match.group(1))
    english_rename = re.search(
        r"rename\s+.+?\s+to\s*[\"“「『]?([^\"”」』。！？!?,，;；]{1,160})",
        request,
        flags=re.IGNORECASE,
    )
    if english_rename:
        return _clean_label(english_rename.group(1))
    quoted = _quoted_values(request)
    return _clean_label(quoted[-1]) if len(quoted) >= 2 else None


def _extract_new_node_label(request: str) -> str | None:
    quoted = _quoted_values(request)
    if quoted:
        # In “在『父节点』下增加『子节点』” the final quoted value is the
        # new node.  For a single quote it is the only useful candidate.
        return _clean_label(quoted[-1])

    match = re.search(
        r"(?:增加|添加|新增|加入|引入|补充|新建)\s*(?:一个|一個|新的|新)?\s*"
        r"(?:概念|方法|机制|节点|node)?\s*[:：]?\s*"
        r"([A-Za-z0-9][A-Za-z0-9_+./-]{0,120}|[\u4e00-\u9fff][^\s，,。；;:：]{0,80})",
        request,
        flags=re.IGNORECASE,
    )
    if match:
        return _clean_label(match.group(1))

    # English requests often put the noun between “add” and “as a node”.
    match = re.search(
        r"(?:add|insert|create)\s+(?:a\s+|an\s+|the\s+)?"
        r"([A-Za-z0-9][A-Za-z0-9_+./ -]{0,120}?)(?:\s+node|\s+method|\s+concept|\s+under\s+|$)",
        request,
        flags=re.IGNORECASE,
    )
    return _clean_label(match.group(1)) if match else None


def _extract_summary(request: str) -> str | None:
    match = re.search(
        r"(?:说明|摘要|注释|描述|解释)(?:改为|改成|更新为|设置为|为|是|：|:)\s*"
        r"(.{2,4800})$",
        request,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().rstrip("。.!！")[:5000]
    english = re.search(
        r"(?:set|update|change)\s+(?:the\s+)?summary\s*(?:to|as|:)\s*(.{2,4800})$",
        request,
        flags=re.IGNORECASE,
    )
    if english:
        return english.group(1).strip().lstrip(" :：").rstrip(".!")[:5000]
    # “给节点补充解释/说明” without explicit content is intentionally left
    # to the fallback so we do not invent a scientific definition.
    return None


def _clean_label(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"(?:节点|node)$", "", value.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"^[：:，,\s]+|[：:，,。；;\s]+$", "", cleaned)
    return cleaned[:500] or None


def _display_label(value: str, limit: int = 180) -> str:
    """Keep human-readable patch reasons below GraphPatch's 1000-char cap."""

    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)] + "…"


def _unique_node_id(graph: ConceptGraph, label: str, request: str) -> str:
    existing = {node.id for node in graph.nodes}
    base = "agent-" + re.sub(r"[^A-Za-z0-9_-]+", "-", label.lower()).strip("-")
    if not base or base == "agent-":
        base = "agent-node"
    # A digest makes the proposal deterministic and avoids leaking arbitrary
    # user text into an ID.  Keep the ID comfortably below the schema limit.
    base = f"{base}-{hashlib.sha1(request.encode('utf-8')).hexdigest()[:8]}"[:180]
    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base[:170]}-{suffix}"
        suffix += 1
    return candidate


def _stable_edge_id(source: str, target: str) -> str:
    return "agent-edge-" + hashlib.sha1(f"{source}:{target}".encode("utf-8")).hexdigest()[:12]


def _infer_node_type(label: str, request: str) -> str:
    value = f"{label} {request}".lower()
    if _contains_any(value, ("问题", "痛点", "瓶颈", "限制", "problem", "limitation", "bottleneck")):
        return "problem"
    if _contains_any(value, ("想法", "创新", "idea", "创新点")):
        return "idea"
    if _contains_any(value, ("方法", "机制", "算法", "模型", "attention", "method", "algorithm")):
        return "method"
    return "concept"


def _candidate_summary(label: str, request: str) -> str:
    problem = re.search(r"(?:解决|缓解|针对|用于|solve|address|reduce)\s*([^，,。；;]{2,180})", request, re.IGNORECASE)
    if problem:
        return f"用户请求希望它用于“{problem.group(1).strip()}”；具体机制和论文证据待核验。"[:5000]
    return f"由 Agent 根据请求提出的“{label}”候选节点；具体机制、证据和适用边界待核验。"


graph_agent_patch_service = GraphAgentPatchService()
