from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock

from app.research_schemas import (
    ConceptEdge,
    ConceptGraph,
    GraphMetadataUpdate,
    ConceptNode,
    GraphOperation,
    GraphPatch,
    GraphPatchCreate,
)


class GraphNotFound(KeyError):
    pass


class GraphConflict(ValueError):
    pass


class GraphService:
    """Versioned in-memory graph store used by the first research MVP."""

    def __init__(self) -> None:
        self._graphs: dict[str, ConceptGraph] = {}
        self._patches: dict[str, GraphPatch] = {}
        self._lock = RLock()

    def save(self, graph: ConceptGraph) -> ConceptGraph:
        with self._lock:
            # Store a validated copy so callers cannot mutate the in-memory
            # graph behind the versioning/patch mechanism.
            stored = ConceptGraph.model_validate(graph.model_dump())
            self._graphs[stored.id] = stored
            return stored.model_copy(deep=True)

    def get(self, graph_id: str) -> ConceptGraph:
        with self._lock:
            graph = self._graphs.get(graph_id)
            if graph is None:
                raise GraphNotFound(graph_id)
            return graph.model_copy(deep=True)

    def list(self, project_id=None) -> list[ConceptGraph]:
        """Return graph snapshots for the graph picker in the workspace."""

        with self._lock:
            graphs = [
                graph
                for graph in self._graphs.values()
                if project_id is None or graph.project_id == project_id
            ]
            return [graph.model_copy(deep=True) for graph in graphs]

    def list_patches(self, graph_id: str) -> list[GraphPatch]:
        with self._lock:
            if graph_id not in self._graphs:
                raise GraphNotFound(graph_id)
            patches = [patch for patch in self._patches.values() if patch.graph_id == graph_id]
            patches.sort(key=lambda item: item.created_at)
            return [patch.model_copy(deep=True) for patch in patches]

    def update_metadata(self, graph_id: str, payload: GraphMetadataUpdate) -> ConceptGraph:
        with self._lock:
            graph = self._graphs.get(graph_id)
            if graph is None:
                raise GraphNotFound(graph_id)
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
            self._graphs[graph_id] = validated
            return validated.model_copy(deep=True)

    def clear(self) -> None:
        with self._lock:
            self._graphs.clear()
            self._patches.clear()

    def create_patch(self, graph_id: str, payload: GraphPatchCreate) -> GraphPatch:
        with self._lock:
            graph = self._graphs.get(graph_id)
            if graph is None:
                raise GraphNotFound(graph_id)

            expected_version = payload.base_version or graph.version
            patch = GraphPatch(
                graph_id=graph_id,
                base_version=expected_version,
                operations=payload.operations,
                reason=payload.reason,
                actor=payload.actor,
                status="proposed",
            )

            # Validate against a copy before persisting a proposal. This
            # catches stale versions and invalid operations at proposal time,
            # while keeping the real graph untouched for agent patches.
            self._validate_patch_locked(graph, patch)
            if payload.actor == "user":
                self._apply_patch_locked(graph, patch)
                patch.status = "applied"
            self._patches[patch.id] = patch
            return patch.model_copy(deep=True)

    def apply_patch(self, graph_id: str, patch_id: str) -> GraphPatch:
        with self._lock:
            graph = self._graphs.get(graph_id)
            patch = self._patches.get(patch_id)
            if graph is None:
                raise GraphNotFound(graph_id)
            if patch is None or patch.graph_id != graph_id:
                raise GraphNotFound(patch_id)
            if patch.status != "proposed":
                raise GraphConflict(f"patch {patch_id} is already {patch.status}")
            self._apply_patch_locked(graph, patch)
            patch.status = "applied"
            return patch.model_copy(deep=True)

    def reject_patch(self, graph_id: str, patch_id: str) -> GraphPatch:
        with self._lock:
            patch = self._patches.get(patch_id)
            if patch is None or patch.graph_id != graph_id:
                raise GraphNotFound(patch_id)
            if patch.status != "proposed":
                raise GraphConflict(f"patch {patch_id} is already {patch.status}")
            patch.status = "rejected"
            return patch.model_copy(deep=True)

    def _apply_patch_locked(self, graph: ConceptGraph, patch: GraphPatch) -> None:
        if graph.version != patch.base_version:
            raise GraphConflict(
                f"graph version changed: expected {patch.base_version}, current {graph.version}"
            )

        # Apply to an isolated candidate first. If any operation fails, the
        # stored graph remains byte-for-byte unchanged (transaction-like
        # behavior for the in-memory MVP).
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
        """Validate a patch without changing the stored graph."""

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
            # Re-validate after merging; model_copy(update=...) bypasses
            # Pydantic validation and would otherwise permit malformed values.
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


graph_service = GraphService()
