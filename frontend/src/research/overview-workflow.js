export function createTopicAnalysisPayload(topic) {
  const concept = String(topic || "").trim();
  if (!concept) throw new Error("研究方向不能为空");
  return {
    concept,
    level: "research",
    audience: "researcher",
    max_papers: 12,
    language: "zh-CN",
  };
}

export function createResearchOverviewPayload() {
  return {
    max_directions: 8,
    max_depth: 3,
    papers_per_direction: 8,
    max_total_papers: 80,
  };
}

export function completedAnalysisHasPapers(job) {
  return job?.status === "completed" && Boolean(job?.result?.papers?.length);
}

export function overviewGenerationSucceeded(job) {
  return ["succeeded", "partial"].includes(job?.status) && Boolean(job?.result?.graph?.nodes?.length);
}

export function overviewGenerationFinished(job) {
  return ["succeeded", "partial", "failed", "interrupted"].includes(job?.status);
}
