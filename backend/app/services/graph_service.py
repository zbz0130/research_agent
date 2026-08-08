from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from threading import RLock
from uuid import uuid4

from app.research_schemas import (
    ConceptEdge,
    ConceptGraph,
    GraphCreate,
    ConceptNode,
    GraphMetadataUpdate,
    GraphOperation,
    GraphPatch,
    GraphPatchCreate,
    GraphCompareCreate,
    GraphCompareResult,
    GraphConnection,
    GraphSubsetResult,
)
from app.storage import storage


class GraphNotFound(KeyError):
    pass


class GraphConflict(ValueError):
    pass


class GraphService:
    """Versioned concept-graph repository with SQLite persistence.

    The service keeps validation and patch semantics here, while ``Storage``
    provides durable documents.  A successful graph write uses an indexed
    ``version`` compare-and-swap so two server workers cannot silently
    overwrite one another's edits.
    """

    def __init__(self) -> None:
        self._graphs: dict[str, ConceptGraph] = {}
        self._patches: dict[str, GraphPatch] = {}
        self._lock = RLock()

    def save(self, graph: ConceptGraph) -> ConceptGraph:
        with self._lock:
            stored = ConceptGraph.model_validate(graph.model_dump())
            storage.save_graph(stored)
            self._graphs[stored.id] = stored.model_copy(deep=True)
            return stored.model_copy(deep=True)

    def create(self, payload: GraphCreate) -> ConceptGraph:
        """Create an independent graph without overwriting an existing ID.

        Analysis jobs use :meth:`save` because they own the generated graph
        document.  The public create endpoint uses this stricter method so a
        user importing a tree cannot accidentally replace another saved graph.
        """

        with self._lock:
            graph_id = payload.id or str(uuid4())
            if storage.get_graph(graph_id) is not None:
                raise GraphConflict(f"概念图 ID 已存在：{graph_id}")
            graph = ConceptGraph(
                id=graph_id,
                project_id=payload.project_id,
                name=payload.name,
                description=payload.description,
                root_id=payload.root_id,
                nodes=payload.nodes,
                edges=payload.edges,
            )
            storage.save_graph(graph)
            self._graphs[graph.id] = graph.model_copy(deep=True)
            return graph.model_copy(deep=True)

    def get(self, graph_id: str) -> ConceptGraph:
        with self._lock:
            graph = storage.get_graph(graph_id)
            if graph is None:
                raise GraphNotFound(graph_id)
            self._graphs[graph.id] = graph.model_copy(deep=True)
            return graph.model_copy(deep=True)

    def list(self, project_id=None) -> list[ConceptGraph]:
        with self._lock:
            graphs = storage.list_graphs(str(project_id) if project_id else None)
            self._graphs = {graph.id: graph.model_copy(deep=True) for graph in graphs}
            return [graph.model_copy(deep=True) for graph in graphs]

    def list_patches(self, graph_id: str) -> list[GraphPatch]:
        with self._lock:
            if storage.get_graph(graph_id) is None:
                raise GraphNotFound(graph_id)
            patches = storage.list_patches(graph_id)
            self._patches = {patch.id: patch.model_copy(deep=True) for patch in patches}
            return [patch.model_copy(deep=True) for patch in patches]

    def compare(self, payload: GraphCompareCreate) -> GraphCompareResult:
        """Find cautious cross-graph connections without mutating either graph.

        The first version uses graph structure and node labels as a stable
        fallback.  The output is intentionally a proposal list: a later
        model-backed agent may enrich the wording and attach paper evidence,
        but it must still write back through a reviewed GraphPatch.
        """

        with self._lock:
            graphs: list[ConceptGraph] = []
            for graph_id in payload.graph_ids:
                graph = storage.get_graph(graph_id)
                if graph is None:
                    raise GraphNotFound(graph_id)
                graphs.append(graph)

            selected: dict[str, list[ConceptNode]] = {}
            requested = set(payload.node_ids)
            for graph in graphs:
                nodes = [
                    node
                    for node in graph.nodes
                    if node.node_type in {"concept", "method", "problem", "idea", "note"}
                    and (not requested or node.id in requested)
                ]
                # Keep a comparison bounded and readable. Prefer explicit
                # problem/method nodes over the automatically generated paper
                # leaves when a graph is large.
                nodes.sort(
                    key=lambda node: (
                        {"problem": 0, "method": 1, "idea": 2, "concept": 3, "note": 4}.get(
                            node.node_type, 5
                        ),
                        node.id,
                    )
                )
                selected[graph.id] = nodes[:12]

            connections: list[GraphConnection] = []
            for left_index, left in enumerate(graphs):
                for right in graphs[left_index + 1 :]:
                    pairs: list[tuple[int, ConceptNode, ConceptNode, str]] = []
                    for source in selected[left.id]:
                        for target in selected[right.id]:
                            if source.id == target.id and source.id == left.root_id:
                                continue
                            relation, score = _compare_relation(source, target)
                            if score <= 0:
                                continue
                            pairs.append((score, source, target, relation))
                    pairs.sort(key=lambda item: (-item[0], item[1].id, item[2].id))
                    for _, source, target, relation in pairs[:4]:
                        connections.append(
                            GraphConnection(
                                source_graph_id=left.id,
                                target_graph_id=right.id,
                                source_node_id=source.id,
                                target_node_id=target.id,
                                relation=relation,
                                idea=(
                                    f"能否把“{source.label}”中的机制借鉴到“{target.label}”，"
                                    f"围绕“{payload.focus}”设计一个最小对照实验？"
                                ),
                                source_evidence_ids=list(source.evidence_ids),
                                target_evidence_ids=list(target.evidence_ids),
                                confidence="low",
                                validation_steps=[
                                    "先阅读两个节点关联的原始论文，确认术语和适用条件不是表面相似",
                                    "固定数据、预算和评价指标，只替换一个跨域机制",
                                    "报告正例、失败案例、额外开销和消融结果",
                                ],
                            )
                        )

            warnings = [
                "跨图连接是模型/规则生成的未验证假设，不代表论文已经证明该组合有效。",
                "当前比较使用节点标签、类型和已有证据 ID；尚未做全文语义验证。",
            ]
            if payload.node_ids and not any(selected.values()):
                warnings.append("指定的节点子集在所选概念图中都不存在，因此没有可比较节点。")
            if not connections:
                warnings.append("当前节点子集没有形成明显的跨域候选，可以扩大节点选择或修改研究焦点。")
            return GraphCompareResult(
                graph_ids=list(payload.graph_ids),
                focus=payload.focus,
                connections=connections[:12],
                warnings=warnings,
            )

    def subset(
        self,
        graph_id: str,
        node_ids: list[str],
        *,
        include_ancestors: bool = True,
    ) -> GraphSubsetResult:
        """Return an ephemeral, non-persisted view of part of a graph."""

        with self._lock:
            graph = storage.get_graph(graph_id)
            if graph is None:
                raise GraphNotFound(graph_id)
            requested = {node_id for node_id in node_ids if node_id}
            known = {node.id for node in graph.nodes}
            selected = requested & known
            warnings: list[str] = []
            if requested - known:
                warnings.append("部分 node_id 不存在，已忽略。")
            if not selected:
                raise GraphConflict("至少需要一个存在于图谱中的 node_id")

            if include_ancestors:
                parents: dict[str, set[str]] = {}
                for edge in graph.edges:
                    if edge.relation in {"is_a", "part_of"}:
                        parents.setdefault(edge.target, set()).add(edge.source)
                frontier = list(selected)
                while frontier:
                    current = frontier.pop()
                    for parent in parents.get(current, set()):
                        if parent in known and parent not in selected:
                            selected.add(parent)
                            frontier.append(parent)
            selected.add(graph.root_id)
            nodes = [node for node in graph.nodes if node.id in selected]
            edges = [
                edge
                for edge in graph.edges
                if edge.source in selected and edge.target in selected
            ]
            digest = hashlib.sha1(",".join(sorted(selected)).encode("utf-8")).hexdigest()[:12]
            subset_graph = ConceptGraph(
                id=f"{graph.id}:subset:{digest}",
                project_id=graph.project_id,
                name=f"{graph.name} · 局部视图",
                description="临时裁剪视图，不会修改或覆盖原概念图。",
                root_id=graph.root_id,
                version=graph.version,
                nodes=nodes,
                edges=edges,
                created_at=graph.created_at,
                updated_at=graph.updated_at,
            )
            return GraphSubsetResult(
                source_graph_id=graph.id,
                graph=subset_graph,
                selected_node_ids=sorted(selected),
                warnings=warnings,
            )

    def update_metadata(self, graph_id: str, payload: GraphMetadataUpdate) -> ConceptGraph:
        with self._lock:
            graph = self.get(graph_id)
            expected_version = payload.base_version or graph.version
            if expected_version != graph.version:
                raise GraphConflict(
                    f"graph version changed: expected {expected_version}, current {graph.version}"
                )
            candidate = graph.model_copy(deep=True)
            changes = payload.model_dump(exclude_unset=True, exclude={"base_version"})
            if "root_id" in changes and changes["root_id"] not in {node.id for node in candidate.nodes}:
                raise GraphConflict("root_id 必须指向图中的现有节点")
            for key, value in changes.items():
                setattr(candidate, key, value)
            candidate.version += 1
            candidate.updated_at = datetime.now(timezone.utc)
            validated = ConceptGraph.model_validate(candidate.model_dump())
            if not storage.update_graph_if_version(validated, expected_version):
                raise GraphConflict(
                    f"graph version changed: expected {expected_version}, current version is newer"
                )
            self._graphs[graph_id] = validated.model_copy(deep=True)
            return validated.model_copy(deep=True)

    def clear(self) -> None:
        with self._lock:
            self._graphs.clear()
            self._patches.clear()
            storage.clear_graphs()

    def create_patch(self, graph_id: str, payload: GraphPatchCreate) -> GraphPatch:
        with self._lock:
            graph = self.get(graph_id)
            expected_version = payload.base_version or graph.version
            patch = GraphPatch(
                graph_id=graph_id,
                base_version=expected_version,
                operations=payload.operations,
                reason=payload.reason,
                actor=payload.actor,
                status="proposed",
                translation_mode=payload.translation_mode,
                source_request=payload.source_request,
                warnings=list(payload.warnings),
            )

            # Validate against a copy before persisting a proposal. This also
            # catches stale versions without changing the real graph.
            self._validate_patch_locked(graph, patch)
            if payload.actor == "user":
                previous_version = graph.version
                self._apply_patch_locked(graph, patch)
                patch.status = "applied"
                if not storage.update_graph_and_patch_if_version(graph, patch, previous_version):
                    raise GraphConflict(
                        f"graph version changed: expected {previous_version}, current version is newer"
                    )
                self._graphs[graph.id] = graph.model_copy(deep=True)
            else:
                storage.save_patch(patch)
            self._patches[patch.id] = patch.model_copy(deep=True)
            return patch.model_copy(deep=True)

    def apply_patch(self, graph_id: str, patch_id: str) -> GraphPatch:
        with self._lock:
            graph = self.get(graph_id)
            patch = storage.get_patch(patch_id)
            if patch is None or patch.graph_id != graph_id:
                raise GraphNotFound(patch_id)
            self._patches[patch.id] = patch.model_copy(deep=True)
            if patch.status != "proposed":
                raise GraphConflict(f"patch {patch_id} is already {patch.status}")
            previous_version = graph.version
            self._apply_patch_locked(graph, patch)
            patch.status = "applied"
            if not storage.update_graph_and_patch_if_version(graph, patch, previous_version):
                raise GraphConflict(
                    f"graph version changed: expected {previous_version}, current version is newer"
                )
            self._graphs[graph.id] = graph.model_copy(deep=True)
            self._patches[patch.id] = patch.model_copy(deep=True)
            return patch.model_copy(deep=True)

    def reject_patch(self, graph_id: str, patch_id: str) -> GraphPatch:
        with self._lock:
            self.get(graph_id)
            patch = storage.get_patch(patch_id)
            if patch is None or patch.graph_id != graph_id:
                raise GraphNotFound(patch_id)
            if patch.status != "proposed":
                raise GraphConflict(f"patch {patch_id} is already {patch.status}")
            patch.status = "rejected"
            storage.save_patch(patch)
            self._patches[patch.id] = patch.model_copy(deep=True)
            return patch.model_copy(deep=True)

    def _apply_patch_locked(self, graph: ConceptGraph, patch: GraphPatch) -> None:
        if graph.version != patch.base_version:
            raise GraphConflict(
                f"graph version changed: expected {patch.base_version}, current {graph.version}"
            )

        # Apply to an isolated candidate first. If any operation fails, the
        # stored graph remains unchanged (transaction-like behavior).
        candidate = graph.model_copy(deep=True)
        nodes = {node.id: node for node in candidate.nodes}
        edges = {edge.id: edge for edge in candidate.edges}
        for operation in patch.operations:
            self._apply_operation_locked(candidate, nodes, edges, operation)

        candidate.nodes = list(nodes.values())
        candidate.edges = list(edges.values())
        candidate.version += 1
        candidate.updated_at = datetime.now(timezone.utc)
        validated = ConceptGraph.model_validate(candidate.model_dump())
        graph.nodes = validated.nodes
        graph.edges = validated.edges
        graph.version = validated.version
        graph.updated_at = validated.updated_at

    def _validate_patch_locked(self, graph: ConceptGraph, patch: GraphPatch) -> None:
        candidate = graph.model_copy(deep=True)
        self._apply_patch_locked(candidate, patch)

    def _apply_operation_locked(
        self,
        graph: ConceptGraph,
        nodes: dict[str, ConceptNode],
        edges: dict[str, ConceptEdge],
        operation: GraphOperation,
    ) -> None:
        if operation.op == "add_node":
            if operation.node is None or operation.node.id in nodes:
                raise GraphConflict("add_node requires a new node")
            nodes[operation.node.id] = operation.node
            return

        if operation.op == "update_node":
            if operation.node_id not in nodes or operation.updates is None:
                raise GraphConflict("update_node requires an existing node and updates")
            current = nodes[operation.node_id]
            if not current.editable:
                raise GraphConflict("node is locked and cannot be updated")
            updates = operation.updates.model_dump(exclude_unset=True)
            nodes[operation.node_id] = ConceptNode.model_validate(
                {**current.model_dump(), **updates}
            )
            return

        if operation.op == "remove_node":
            if operation.node_id not in nodes or operation.node_id == graph.root_id:
                raise GraphConflict("cannot remove the graph root or an unknown node")
            if not nodes[operation.node_id].editable:
                raise GraphConflict("node is locked and cannot be removed")
            del nodes[operation.node_id]
            for edge_id, edge in list(edges.items()):
                if edge.source == operation.node_id or edge.target == operation.node_id:
                    del edges[edge_id]
            return

        if operation.op == "add_edge":
            if operation.edge is None:
                raise GraphConflict("add_edge requires an edge")
            if operation.edge.source not in nodes or operation.edge.target not in nodes:
                raise GraphConflict("edge endpoints must exist")
            if operation.edge.source == operation.edge.target:
                raise GraphConflict("self-loop edges are not allowed")
            if operation.edge.id in edges:
                raise GraphConflict("edge already exists")
            edges[operation.edge.id] = operation.edge
            return

        if operation.op == "remove_edge":
            edge_id = operation.edge.id if operation.edge is not None else operation.node_id
            if not edge_id or edge_id not in edges:
                raise GraphConflict("unknown edge")
            del edges[edge_id]

def _compare_relation(source: ConceptNode, target: ConceptNode) -> tuple[str, int]:
    """Return a simple, explainable priority for a cross-graph pair."""

    if source.node_type == "problem" and target.node_type in {"method", "idea"}:
        return "method_transfer", 5
    if target.node_type == "problem" and source.node_type in {"method", "idea"}:
        return "method_transfer", 5
    if source.node_type == "problem" or target.node_type == "problem":
        return "shared_problem", 4
    if source.node_type in {"method", "idea"} and target.node_type in {"method", "idea"}:
        return "cross_domain_candidate", 3
    shared = _label_terms(source.label) & _label_terms(target.label)
    if shared:
        return "cross_domain_candidate", 2
    if source.node_type != target.node_type:
        return "cross_domain_candidate", 1
    return "cross_domain_candidate", 0


def _label_terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", value.lower())
        if token not in {"概念", "方法", "问题", "机制", "相关"}
    }


graph_service = GraphService()
