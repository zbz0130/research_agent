import assert from "node:assert/strict";
import test from "node:test";

import { graphEdgeVisible, graphNodeMatchesFilter } from "./graph-renderer.js";
import { nodeAppearance } from "./graph-metrics.js";

test("node search and role filters are combined", () => {
  const node = {
    label: "PagedAttention",
    explanation: "使用分页方式管理 KV cache",
    method_summary: "减少显存碎片",
  };

  assert.equal(graphNodeMatchesFilter(node, "method", { query: "kv cache", roles: ["method"] }), true);
  assert.equal(graphNodeMatchesFilter(node, "concept", { query: "kv cache", roles: ["method"] }), false);
  assert.equal(graphNodeMatchesFilter(node, "method", { query: "扩散模型", roles: ["method"] }), false);
});

test("low confidence visibility remains independent from endpoint filtering", () => {
  assert.equal(graphEdgeVisible({ confidence: "low", endpointsVisible: true, lowConfidenceVisible: false }), false);
  assert.equal(graphEdgeVisible({ confidence: "high", endpointsVisible: true, lowConfidenceVisible: false }), true);
  assert.equal(graphEdgeVisible({ confidence: "high", endpointsVisible: false, lowConfidenceVisible: true }), false);
});

test("paper leaves are circular and grow only within a readable range", () => {
  const appearance = nodeAppearance(
    { role: "paper", year: 2025, visual: { recency_score: 1 } },
    { root_id: "topic" },
  );

  assert.equal(appearance.width, appearance.height);
  assert.ok(appearance.width >= 42 && appearance.width <= 74);
});
