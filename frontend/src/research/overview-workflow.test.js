import assert from "node:assert/strict";
import test from "node:test";

import {
  completedAnalysisHasPapers,
  createResearchOverviewPayload,
  createTopicAnalysisPayload,
  overviewGenerationSucceeded,
} from "./overview-workflow.js";

test("one-click research always requests the bounded researcher workflow", () => {
  assert.deepEqual(createTopicAnalysisPayload("  agent memory  "), {
    concept: "agent memory",
    level: "research",
    audience: "researcher",
    max_papers: 12,
    language: "zh-CN",
  });
  assert.throws(() => createTopicAnalysisPayload("   "), /不能为空/);
});

test("overview generation keeps direction, depth and paper budgets bounded", () => {
  assert.deepEqual(createResearchOverviewPayload(), {
    max_directions: 8,
    max_depth: 3,
    papers_per_direction: 8,
    max_total_papers: 80,
  });
});

test("workflow success requires real papers and a non-empty graph", () => {
  assert.equal(completedAnalysisHasPapers({ status: "completed", result: { papers: [{}] } }), true);
  assert.equal(completedAnalysisHasPapers({ status: "completed", result: { papers: [] } }), false);
  assert.equal(overviewGenerationSucceeded({ status: "partial", result: { graph: { nodes: [{}] } } }), true);
  assert.equal(overviewGenerationSucceeded({ status: "succeeded", result: { graph: { nodes: [] } } }), false);
});
