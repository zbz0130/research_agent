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

test("problem and method nodes remain circular and grow with branch heat", () => {
  for (const role of ["problem", "method"]) {
    const cool = nodeAppearance(
      { role, visual: { radius: 28, heat_score: 0 } },
      { root_id: "topic" },
    );
    const hot = nodeAppearance(
      { role, visual: { radius: 58, heat_score: 1 } },
      { root_id: "topic" },
    );
    assert.equal(cool.width, cool.height);
    assert.equal(hot.width, hot.height);
    assert.ok(hot.width > cool.width);
  }
});

test("research graph labels use dark text on every node role", () => {
  for (const role of ["root", "direction", "paper", "problem", "method", "idea", "concept"]) {
    const appearance = nodeAppearance(
      { role, year: 2025, visual: { recency_score: 1, heat_score: 1 } },
      { root_id: "topic" },
    );
    assert.equal(appearance.foreground, "#111827");
  }
});
