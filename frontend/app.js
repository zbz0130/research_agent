const healthEl = document.querySelector("#health");
const apiKeysEl = document.querySelector("#api-keys");
const projectsEl = document.querySelector("#projects");
const projectForm = document.querySelector("#project-form");
const projectMessageEl = document.querySelector("#form-message");
const analysisForm = document.querySelector("#analysis-form");
const analysisSubmit = document.querySelector("#analysis-submit");
const analysisMessageEl = document.querySelector("#analysis-message");
const explanationEl = document.querySelector("#explanation");
const papersEl = document.querySelector("#papers");
const graphEl = document.querySelector("#graph");
const graphVersionEl = document.querySelector("#graph-version");
const graphPickerEl = document.querySelector("#graph-picker");
const analysisProviderEl = document.querySelector("#analysis-provider");
const paperCountEl = document.querySelector("#paper-count");
const nodeForm = document.querySelector("#node-form");
const graphActionsEl = document.querySelector("#graph-actions");
const graphMessageEl = document.querySelector("#graph-message");
const agentProposeButton = document.querySelector("#agent-propose");
const graphMetaForm = document.querySelector("#graph-meta-form");
const graphNameInput = document.querySelector("#graph-name");
const innovationCardEl = document.querySelector("#innovation-card");
const innovationsEl = document.querySelector("#innovations");
const noveltyNoteEl = document.querySelector("#novelty-note");
const patchCardEl = document.querySelector("#patch-card");
const patchesEl = document.querySelector("#patches");

const state = {
  analysisId: null,
  graphId: null,
  graph: null,
  pendingPatches: new Map(),
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);
}

function safeExternalUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch (error) {
    return null;
  }
}

const displayLabels = {
  academic: "学术来源",
  demo: "示例资料",
  official: "官方资料",
  community: "社区信号",
  open_access: "开放全文",
  abstract_only: "仅有摘要",
  metadata_only: "仅有元数据",
  unknown: "来源类型未知",
  supports: "支持线索",
  contradicts: "反驳线索",
  qualified_support: "有条件支持",
  background: "背景线索",
  unclear: "关系未核验",
  unverified: "未人工核验",
  reviewed: "已人工核验",
};

function displayLabel(value) {
  return displayLabels[value] || value || "未知";
}

function setHealth(text, ok) {
  healthEl.textContent = text;
  healthEl.className = `status-pill ${ok ? "status-ok" : "status-error"}`;
}

async function loadHealth() {
  try {
    const response = await fetch("/api/v1/health");
    if (!response.ok) throw new Error("health check failed");
    const data = await response.json();
    setHealth(`${data.service} · ${data.version}`, true);
  } catch (error) {
    setHealth("API 不可用", false);
  }
}

function renderApiKeys(slots) {
  apiKeysEl.innerHTML = slots.map((slot) => `
    <div class="setting-row">
      <div>
        <h3>${escapeHtml(slot.label)}</h3>
        <p><span class="provider-name">${escapeHtml(slot.provider)}</span> · <code>${escapeHtml(slot.environment_variable)}</code></p>
      </div>
      <span class="tag ${slot.configured ? "tag-configured" : "tag-missing"}">
        ${slot.configured ? `已配置 ${escapeHtml(slot.masked || "")}` : "未配置"}
      </span>
    </div>
  `).join("");
}

async function loadApiKeys() {
  try {
    const response = await fetch("/api/v1/settings/api-keys");
    if (!response.ok) throw new Error("settings request failed");
    const data = await response.json();
    renderApiKeys(data.slots);
  } catch (error) {
    apiKeysEl.innerHTML = '<p class="empty error-text">配置状态读取失败，请确认 API 正在运行。</p>';
  }
}

function renderProjects(projects) {
  if (projects.length === 0) {
    projectsEl.innerHTML = '<p class="empty">还没有项目。</p>';
    return;
  }
  projectsEl.innerHTML = projects.map((project) => `
    <div class="project-row">
      <div>
        <h3>${escapeHtml(project.name)}</h3>
        <p>${escapeHtml(project.research_question)}</p>
      </div>
      <span class="tag">${escapeHtml(project.status)}</span>
    </div>
  `).join("");
}

async function loadProjects() {
  try {
    const response = await fetch("/api/v1/projects");
    if (!response.ok) throw new Error("project request failed");
    renderProjects(await response.json());
  } catch (error) {
    projectsEl.innerHTML = '<p class="empty error-text">项目加载失败，请确认 API 正在运行。</p>';
  }
}

function setAnalysisMessage(text, kind = "") {
  analysisMessageEl.textContent = text;
  analysisMessageEl.className = `form-message ${kind}`;
}

function resetAnalysisView() {
  state.analysisId = null;
  state.graphId = null;
  state.graph = null;
  state.pendingPatches.clear();
  analysisProviderEl.textContent = "分析中…";
  paperCountEl.textContent = "0 篇";
  graphVersionEl.textContent = "v—";
  graphPickerEl.classList.add("hidden");
  graphPickerEl.innerHTML = "";
  explanationEl.className = "result-placeholder";
  explanationEl.textContent = "正在准备新的分析结果…";
  papersEl.innerHTML = '<p class="empty">正在检索和整理资料…</p>';
  graphEl.className = "graph-placeholder";
  graphEl.textContent = "正在构建概念图…";
  nodeForm.classList.add("hidden");
  graphActionsEl.classList.add("hidden");
  graphMetaForm.classList.add("hidden");
  graphNameInput.value = "";
  innovationCardEl.classList.add("hidden");
  innovationsEl.innerHTML = "";
  noveltyNoteEl.textContent = "";
  renderPatches();
}

function renderExplanation(result) {
  const explanation = result.explanation;
  const warnings = result.warnings || [];
  explanationEl.innerHTML = `
    ${warnings.length ? `<div class="warning-box"><strong>需要注意</strong><ul>${warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
    <section class="explanation-section featured-explanation">
      <p class="section-label">一句话理解</p>
      <p class="one-sentence">${escapeHtml(explanation.one_sentence)}</p>
    </section>
    <section class="explanation-section">
      <p class="section-label">直觉类比</p>
      <p>${escapeHtml(explanation.intuitive)}</p>
    </section>
    <section class="explanation-section">
      <p class="section-label">技术机制</p>
      <p>${escapeHtml(explanation.technical)}</p>
    </section>
    <section class="explanation-columns">
      <div class="explanation-section">
        <p class="section-label">演变过程</p>
        <ol>${(explanation.evolution || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("") || "<li>暂无足够资料</li>"}</ol>
      </div>
      <div class="explanation-section">
        <p class="section-label">相关概念</p>
        <div class="chip-list">${(explanation.related_concepts || []).map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("") || "<span class=\"muted\">暂无</span>"}</div>
      </div>
    </section>
    <section class="explanation-section">
      <p class="section-label">限制与边界</p>
      <ul>${(explanation.limitations || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("") || "<li>暂无</li>"}</ul>
    </section>
    <p class="evidence-link-note">本次解释关联 ${escapeHtml((explanation.evidence_ids || []).length)} 张证据卡；摘要级证据仍需人工核对全文。</p>
  `;
}

function renderPapers(result) {
  paperCountEl.textContent = `${result.papers.length} 篇`;
  if (!result.papers.length) {
    papersEl.innerHTML = '<p class="empty">当前模式没有检索论文。</p>';
    return;
  }
  const evidenceByPaper = new Map();
  (result.evidence || []).forEach((item) => {
    const items = evidenceByPaper.get(item.paper_id) || [];
    items.push(item);
    evidenceByPaper.set(item.paper_id, items);
  });
  const retrievalSummary = result.search_terms?.length
    ? `<div class="retrieval-summary"><strong>本次检索范围：</strong>${escapeHtml(result.retrieval_scope || "摘要和元数据")}
        <br /><strong>检索词：</strong>${result.search_terms.map(escapeHtml).join(" · ")}</div>`
    : "";
  papersEl.innerHTML = retrievalSummary + result.papers.map((paper) => {
    const sourceUrl = safeExternalUrl(paper.url);
    return `
    <article class="paper-row">
      <div class="paper-main">
        <div class="paper-title-line">
          <h3>${escapeHtml(paper.title)}</h3>
          <span class="tag ${paper.source_kind === "demo" ? "tag-missing" : "tag-configured"}">${escapeHtml(displayLabel(paper.source_kind))}</span>
        </div>
        <p class="paper-meta">${escapeHtml((paper.authors || []).slice(0, 3).join(", ") || "作者未提供")} · ${escapeHtml(paper.year || "年份未知")} · ${escapeHtml(paper.venue || paper.source)} · ${escapeHtml(displayLabel(paper.access_type))}</p>
        <p class="paper-abstract">${escapeHtml(paper.abstract || "暂无摘要")}</p>
        ${(evidenceByPaper.get(paper.id) || []).map((item) => `
          <div class="evidence-item">
            <span class="evidence-label">摘要片段 · ${escapeHtml(displayLabel(item.relation || "background"))} · ${escapeHtml(item.confidence)}</span>
            <p>${escapeHtml(item.excerpt)}</p>
            <small>${escapeHtml(item.location || item.locator?.kind || "摘要")} · ${escapeHtml(displayLabel(item.verification_status || "unverified"))} · ${escapeHtml(item.claim)}</small>
          </div>
        `).join("")}
      </div>
      ${sourceUrl ? `<a class="source-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">打开来源 ↗</a>` : ""}
    </article>
  `;
  }).join("");
}

function renderInnovations(result) {
  const candidates = result.innovation_candidates || [];
  if (!candidates.length) {
    innovationCardEl.classList.add("hidden");
    innovationsEl.innerHTML = "";
    noveltyNoteEl.textContent = "";
    return;
  }
  innovationCardEl.classList.remove("hidden");
  innovationsEl.innerHTML = candidates.map((candidate) => `
    <article class="innovation-row">
      <div class="innovation-heading">
        <div>
          <h3>${escapeHtml(candidate.title)}</h3>
          <p class="paper-meta">新颖性层级 ${escapeHtml(candidate.novelty_level)} · 置信度 ${escapeHtml(candidate.confidence)} · 可行性 ${escapeHtml(candidate.feasibility)}</p>
        </div>
        <span class="tag tag-missing">未验证</span>
      </div>
      <dl class="innovation-details">
        <div><dt>要解决的问题</dt><dd>${escapeHtml(candidate.problem)}</dd></div>
        <div><dt>可能机制</dt><dd>${escapeHtml(candidate.mechanism)}</dd></div>
        <div><dt>为什么想到它</dt><dd>${escapeHtml(candidate.rationale)}</dd></div>
      </dl>
      ${candidate.nearest_work?.length ? `<p class="innovation-nearest"><strong>最近资料：</strong>${candidate.nearest_work.map(escapeHtml).join("；")}</p>` : ""}
      <div class="validation-box"><strong>建议的最小验证</strong><ol>${(candidate.validation_steps || []).map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol></div>
      ${candidate.warning ? `<p class="warning-inline">${escapeHtml(candidate.warning)}</p>` : ""}
    </article>
  `).join("");
  noveltyNoteEl.textContent = result.novelty_note || "当前没有可用的新颖性范围说明。";
}

function graphDepths(graph) {
  const parentByNode = {};
  graph.edges.filter((edge) => ["is_a", "part_of"].includes(edge.relation)).forEach((edge) => {
    parentByNode[edge.target] = edge.source;
  });
  const depths = {};
  const depthOf = (nodeId, seen = new Set()) => {
    if (nodeId === graph.root_id || seen.has(nodeId)) return 0;
    // Non-hierarchical relations still belong below the root in the compact
    // first-version renderer. They are shown as relations, not mistaken for
    // additional roots.
    if (!parentByNode[nodeId]) return 1;
    seen.add(nodeId);
    return 1 + depthOf(parentByNode[nodeId], seen);
  };
  graph.nodes.forEach((node) => { depths[node.id] = depthOf(node.id); });
  return depths;
}

function renderGraph(graph) {
  state.graph = graph;
  state.graphId = graph.id;
  graphVersionEl.textContent = `v${graph.version}`;
  graphPickerEl.classList.remove("hidden");
  graphPickerEl.value = graph.id;
  nodeForm.classList.remove("hidden");
  graphActionsEl.classList.remove("hidden");
  graphMetaForm.classList.remove("hidden");
  graphNameInput.value = graph.name || "";
  const depths = graphDepths(graph);
  const relationsByTarget = {};
  graph.edges.forEach((edge) => {
    const relations = relationsByTarget[edge.target] || [];
    relations.push(edge.relation);
    relationsByTarget[edge.target] = relations;
  });
  const nodes = [...graph.nodes].sort((a, b) => (depths[a.id] - depths[b.id]) || a.label.localeCompare(b.label));
  graphEl.innerHTML = nodes.map((node) => `
    <div class="graph-node node-${escapeHtml(node.node_type)}" style="--depth:${Math.min(depths[node.id], 4)}">
      <div class="node-content">
        <div>
          <span class="node-type">${escapeHtml(node.node_type)}</span>
          <h3>${escapeHtml(node.label)}</h3>
          <p>${escapeHtml(node.summary || "暂无说明")}</p>
        </div>
        <div class="node-actions">
          ${node.editable ? `<button type="button" class="node-edit" data-node-id="${escapeHtml(node.id)}">编辑</button>` : ""}
          <button type="button" class="node-explain" data-node-explain="${escapeHtml(node.id)}">AI解释</button>
        </div>
      </div>
      ${relationsByTarget[node.id] ? `<small class="node-relation">${escapeHtml(relationsByTarget[node.id].join(" · "))}</small>` : ""}
    </div>
  `).join("");
}

function setGraphMessage(text, kind = "") {
  graphMessageEl.textContent = text;
  graphMessageEl.className = `form-message ${kind}`;
}

async function refreshGraph() {
  if (!state.graphId) return;
  const graphResponse = await fetch(`/api/v1/graphs/${encodeURIComponent(state.graphId)}`);
  if (!graphResponse.ok) throw new Error("graph request failed");
  renderGraph(await graphResponse.json());
  const patchesResponse = await fetch(`/api/v1/graphs/${encodeURIComponent(state.graphId)}/patches`);
  if (patchesResponse.ok) {
    const patches = await patchesResponse.json();
    state.pendingPatches = new Map(
      patches.filter((patch) => patch.status === "proposed").map((patch) => [patch.id, patch]),
    );
    renderPatches();
  }
  await loadGraphPicker(state.graphId);
}

async function loadGraphPicker(selectedId = state.graphId) {
  const response = await fetch("/api/v1/graphs");
  if (!response.ok) return;
  const graphs = await response.json();
  if (!graphs.length) {
    graphPickerEl.classList.add("hidden");
    return;
  }
  graphPickerEl.classList.remove("hidden");
  graphPickerEl.innerHTML = graphs.map((graph) =>
    `<option value="${escapeHtml(graph.id)}">${escapeHtml(graph.name)} · v${escapeHtml(graph.version)}</option>`,
  ).join("");
  if (selectedId && graphs.some((graph) => graph.id === selectedId)) graphPickerEl.value = selectedId;
}

graphPickerEl.addEventListener("change", async () => {
  state.graphId = graphPickerEl.value;
  try {
    await refreshGraph();
  } catch (error) {
    setGraphMessage(`概念图加载失败：${error.message}`, "error-text");
  }
});

async function applyUserPatch(operations, reason) {
  if (!state.graphId) return;
  const response = await fetch(`/api/v1/graphs/${encodeURIComponent(state.graphId)}/patches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      operations,
      reason,
      actor: "user",
      base_version: state.graph?.version ?? null,
    }),
  });
  if (!response.ok) {
    if (response.status === 409) await refreshGraph();
    throw new Error(await response.text());
  }
  await refreshGraph();
}

function renderPatches() {
  const patches = [...state.pendingPatches.values()];
  if (!patches.length) {
    patchCardEl.classList.add("hidden");
    patchesEl.innerHTML = '<p class="empty">还没有待审核的提案。</p>';
    return;
  }
  patchCardEl.classList.remove("hidden");
  patchesEl.innerHTML = patches.map((patch) => `
    <article class="patch-row">
      <div>
        <div class="paper-title-line">
          <h3>提案 ${escapeHtml(patch.id.slice(0, 8))}</h3>
          <span class="tag tag-beta">v${escapeHtml(patch.base_version)} → 待应用</span>
        </div>
        <p>${escapeHtml(patch.reason)}</p>
        <ul>${(patch.operations || []).map((operation) => `<li>${escapeHtml(describeOperation(operation))}</li>`).join("")}</ul>
      </div>
      <div class="patch-actions">
        <button type="button" data-patch-action="apply" data-patch-id="${escapeHtml(patch.id)}">批准</button>
        <button type="button" class="secondary" data-patch-action="reject" data-patch-id="${escapeHtml(patch.id)}">拒绝</button>
      </div>
    </article>
  `).join("");
}

function describeOperation(operation) {
  if (operation.op === "add_node") return `新增节点：${operation.node?.label || "未命名"}`;
  if (operation.op === "update_node") return `修改节点：${operation.node_id || "未知"}`;
  if (operation.op === "remove_node") return `删除节点：${operation.node_id || "未知"}`;
  if (operation.op === "add_edge") return `新增关系：${operation.edge?.source || "?"} → ${operation.edge?.target || "?"}`;
  if (operation.op === "remove_edge") return `删除关系：${operation.edge?.id || operation.node_id || "未知"}`;
  return operation.op || "未知操作";
}

async function reviewPatch(patchId, action) {
  if (!state.graphId) return;
  const response = await fetch(
    `/api/v1/graphs/${encodeURIComponent(state.graphId)}/patches/${encodeURIComponent(patchId)}/${action}`,
    { method: "POST" },
  );
  if (!response.ok) {
    if (response.status === 409) await refreshGraph();
    throw new Error(await response.text());
  }
  const patch = await response.json();
  state.pendingPatches.delete(patchId);
  renderPatches();
  if (action === "apply") await refreshGraph();
}

patchesEl.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-patch-action]");
  if (!button) return;
  try {
    await reviewPatch(button.dataset.patchId, button.dataset.patchAction);
  } catch (error) {
    window.alert(`提案处理失败：${error.message}`);
  }
});

async function proposeAgentPatch() {
  if (!state.graph || !state.graphId) return;
  const hasAttention = state.graph.nodes.some((node) => /attention|注意力/i.test(node.label));
  const label = hasAttention ? "FlashAttention" : "待验证的跨领域方法";
  if (state.graph.nodes.some((node) => node.label === label)) {
    setGraphMessage("图中已经有这个节点，可以先编辑或继续分析。", "error-text");
    return;
  }
  const nodeId = `agent-${Date.now()}`;
  const edgeId = `agent-edge-${Date.now()}`;
  const response = await fetch(`/api/v1/graphs/${encodeURIComponent(state.graphId)}/patches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      actor: "agent",
      base_version: state.graph.version,
      reason: "根据当前概念与论文线索提议补充一个待核验方法节点",
      operations: [
        {
          op: "add_node",
          node: {
            id: nodeId,
            label,
            summary: "候选节点：需要进一步检索和人工确认其与当前概念的关系。",
            node_type: "idea",
            evidence_ids: [],
            editable: true,
          },
        },
        {
          op: "add_edge",
          edge: { id: edgeId, source: state.graph.root_id, target: nodeId, relation: "related_to", evidence_ids: [] },
        },
      ],
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  const patch = await response.json();
  state.pendingPatches.set(patch.id, patch);
  renderPatches();
  setGraphMessage("Agent 已生成提案，请在下方预览后批准或拒绝。", "");
}

agentProposeButton.addEventListener("click", () => {
  agentProposeButton.disabled = true;
  proposeAgentPatch()
    .catch((error) => setGraphMessage(`提案生成失败：${error.message}`, "error-text"))
    .finally(() => { agentProposeButton.disabled = false; });
});

graphMetaForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.graphId || !state.graph) return;
  const name = graphNameInput.value.trim();
  if (!name) return;
  const response = await fetch(`/api/v1/graphs/${encodeURIComponent(state.graphId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, base_version: state.graph.version }),
  });
  if (!response.ok) {
    if (response.status === 409) await refreshGraph();
    window.alert(`概念图名称保存失败：${await response.text()}`);
    return;
  }
  renderGraph(await response.json());
  await loadGraphPicker(state.graphId);
  setGraphMessage("概念图名称已保存。", "");
});

graphEl.addEventListener("click", async (event) => {
  const explainButton = event.target.closest("[data-node-explain]");
  if (explainButton && state.graph) {
    const nodeId = explainButton.dataset.nodeExplain;
    try {
      const response = await fetch(
        `/api/v1/graphs/${encodeURIComponent(state.graphId)}/nodes/${encodeURIComponent(nodeId)}/explanation-patch`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ audience: "beginner", language: "zh-CN" }),
        },
      );
      if (!response.ok) throw new Error(await response.text());
      const patch = await response.json();
      state.pendingPatches.set(patch.id, patch);
      renderPatches();
      setGraphMessage("Agent 已生成节点解释提案，请批准后写入说明。", "");
    } catch (error) {
      setGraphMessage(`节点解释生成失败：${error.message}`, "error-text");
    }
    return;
  }
  const button = event.target.closest("[data-node-id]");
  if (!button || !state.graph) return;
  const node = state.graph.nodes.find((item) => item.id === button.dataset.nodeId);
  if (!node) return;
  const label = window.prompt("节点名称", node.label || "");
  if (label === null || !label.trim()) return;
  const summary = window.prompt(`修改“${label.trim()}”的说明`, node.summary || "");
  if (summary === null) return;
  try {
    await applyUserPatch(
      [{ op: "update_node", node_id: node.id, updates: { label: label.trim(), summary } }],
      "用户手动修改节点名称和说明",
    );
  } catch (error) {
    window.alert("节点修改失败：" + error.message);
  }
});

nodeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const label = document.querySelector("#node-label").value.trim();
  const summary = document.querySelector("#node-summary").value.trim();
  if (!label || !state.graph) return;
  const id = `user-${Date.now()}`;
  try {
    await applyUserPatch(
      [
        { op: "add_node", node: { id, label, summary, node_type: "note", evidence_ids: [], editable: true } },
        { op: "add_edge", edge: { id: `edge-${Date.now()}`, source: state.graph.root_id, target: id, relation: "related_to", evidence_ids: [] } },
      ],
      "用户手动新增概念节点",
    );
    nodeForm.reset();
  } catch (error) {
    window.alert("新增节点失败：" + error.message);
  }
});

async function pollAnalysis(id) {
  const response = await fetch(`/api/v1/analyses/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error("analysis request failed");
  const job = await response.json();
  setAnalysisMessage(`${job.message} · ${job.progress}%`);
  if (job.status === "completed") {
    analysisSubmit.disabled = false;
    renderAnalysis(job.result);
    return;
  }
  if (job.status === "failed") {
    analysisSubmit.disabled = false;
    setAnalysisMessage(`分析失败：${job.error || "未知错误"}`, "error-text");
    return;
  }
  window.setTimeout(() => pollAnalysis(id).catch((error) => {
    analysisSubmit.disabled = false;
    setAnalysisMessage("无法读取分析进度：" + error.message, "error-text");
  }), 700);
}

function renderAnalysis(result) {
  analysisProviderEl.textContent = result.provider;
  renderExplanation(result);
  renderPapers(result);
  renderInnovations(result);
  renderGraph(result.graph);
  loadGraphPicker(result.graph.id).catch(() => {});
  state.pendingPatches.clear();
  renderPatches();
}

analysisForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  resetAnalysisView();
  analysisSubmit.disabled = true;
  setAnalysisMessage("正在创建分析任务…");
  try {
    const response = await fetch("/api/v1/analyses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        concept: document.querySelector("#concept").value,
        level: document.querySelector("#analysis-level").value,
        audience: document.querySelector("#audience").value,
        max_papers: Number(document.querySelector("#max-papers").value),
        language: "zh-CN",
      }),
    });
    if (!response.ok) throw new Error(await response.text());
    const job = await response.json();
    state.analysisId = job.id;
    await pollAnalysis(job.id);
  } catch (error) {
    analysisSubmit.disabled = false;
    setAnalysisMessage("创建分析失败：" + error.message, "error-text");
  }
});

projectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  projectMessageEl.textContent = "正在创建…";
  try {
    const response = await fetch("/api/v1/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: document.querySelector("#project-name").value,
        research_question: document.querySelector("#research-question").value,
      }),
    });
    if (!response.ok) throw new Error("create project failed");
    projectForm.reset();
    projectMessageEl.textContent = "项目已创建。";
    await loadProjects();
  } catch (error) {
    projectMessageEl.textContent = "创建失败，请检查 API 日志。";
  }
});

document.querySelector("#refresh").addEventListener("click", loadProjects);
document.querySelector("#refresh-settings").addEventListener("click", loadApiKeys);

loadHealth();
loadProjects();
loadApiKeys();
