import test from "node:test";
import assert from "node:assert/strict";

import { graphLayoutOptions, hasCompleteSavedPositions } from "./graph-layout.js";

test("null graph coordinates do not select the preset layout", () => {
  const graph = {
    graph_kind: "research_direction",
    root_id: "root",
    nodes: [
      { id: "root", visual: { x: null, y: null } },
      { id: "paper", visual: { x: null, y: null } },
    ],
  };

  assert.equal(hasCompleteSavedPositions(graph), false);
  assert.equal(graphLayoutOptions(graph).name, "breadthfirst");
});

test("complete finite graph coordinates restore the preset layout", () => {
  const graph = {
    graph_kind: "concept_network",
    nodes: [
      { id: "root", visual: { x: 10, y: 20 } },
      { id: "method", visual: { x: "30", y: "40" } },
    ],
  };

  assert.equal(hasCompleteSavedPositions(graph), true);
  assert.equal(graphLayoutOptions(graph).name, "preset");
});
