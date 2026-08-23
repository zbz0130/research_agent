import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAddEdgeOperation,
  buildAddNodeOperations,
  buildRemoveEdgeOperation,
  buildRemoveNodeOperation,
} from "./graph-editor.js";

const graph = {
  root_id: "root",
  nodes: [
    { id: "root", label: "Agent Memory", editable: true },
    { id: "paper-a", label: "Paper A", editable: false },
    { id: "user-a", label: "用户问题", editable: true },
  ],
  edges: [{ id: "edge-a", source: "root", target: "paper-a" }],
};

test("adding a node always creates a connected user-authored pair of operations", () => {
  const operations = buildAddNodeOperations({
    id: "user-new",
    edgeId: "edge-new",
    label: "长期记忆污染",
    nodeType: "problem",
    parentId: "root",
  });
  assert.equal(operations.length, 2);
  assert.equal(operations[0].node.node_type, "problem");
  assert.equal(operations[1].edge.source, "root");
  assert.equal(operations[1].edge.target, "user-new");
  assert.equal(operations[1].edge.source_kind, "user");
});

test("manual edges reject self loops and normalize unsupported relations", () => {
  assert.throws(() => buildAddEdgeOperation({ id: "e", sourceId: "root", targetId: "root" }), /不同/);
  const operation = buildAddEdgeOperation({
    id: "e2", sourceId: "root", targetId: "user-a", relation: "invented",
  });
  assert.equal(operation.edge.relation, "related_to");
});

test("root and evidence-locked nodes cannot be deleted", () => {
  assert.throws(() => buildRemoveNodeOperation(graph, "root"), /根节点/);
  assert.throws(() => buildRemoveNodeOperation(graph, "paper-a"), /证据保护/);
  assert.deepEqual(buildRemoveNodeOperation(graph, "user-a"), { op: "remove_node", node_id: "user-a" });
});

test("only an existing edge can be removed", () => {
  assert.deepEqual(buildRemoveEdgeOperation(graph, "edge-a"), { op: "remove_edge", node_id: "edge-a" });
  assert.throws(() => buildRemoveEdgeOperation(graph, "missing"), /不存在/);
});
