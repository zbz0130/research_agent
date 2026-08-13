const healthEl = document.querySelector("#health");
const apiKeysEl = document.querySelector("#api-keys");
const apiKeyForm = document.querySelector("#api-key-form");
const apiKeyMessageEl = document.querySelector("#api-key-message");
const saveApiKeysButton = document.querySelector("#save-api-keys");
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
const graphLifecycleNoteEl = document.querySelector("#graph-lifecycle-note");
const analysisProviderEl = document.querySelector("#analysis-provider");
const paperCountEl = document.querySelector("#paper-count");
const evidenceLedgerEl = document.querySelector("#evidence-ledger");
const ledgerCoverageEl = document.querySelector("#ledger-coverage");
const ledgerMessageEl = document.querySelector("#ledger-message");
const ledgerClaimsEl = document.querySelector("#ledger-claims");
const nodeForm = document.querySelector("#node-form");
const graphActionsEl = document.querySelector("#graph-actions");
const graphMessageEl = document.querySelector("#graph-message");
const agentProposeButton = document.querySelector("#agent-propose");
const graphAgentForm = document.querySelector("#graph-agent-form");
const graphAgentRequestInput = document.querySelector("#graph-agent-request");
const graphAgentSubmit = document.querySelector("#graph-agent-submit");
const graphAgentMessageEl = document.querySelector("#graph-agent-message");
const graphMetaForm = document.querySelector("#graph-meta-form");
const graphNameInput = document.querySelector("#graph-name");
const graphRootInput = document.querySelector("#graph-root");
const innovationCardEl = document.querySelector("#innovation-card");
const innovationsEl = document.querySelector("#innovations");
const noveltyNoteEl = document.querySelector("#novelty-note");
const experimentPlanForm = document.querySelector("#experiment-plan-form");
const experimentIdeaInput = document.querySelector("#experiment-idea");
const experimentTitleInput = document.querySelector("#experiment-title");
const experimentBaselineInput = document.querySelector("#experiment-baseline");
const experimentPlanSubmit = document.querySelector("#experiment-plan-submit");
const experimentPlanClearButton = document.querySelector("#experiment-plan-clear");
const experimentPlanMessageEl = document.querySelector("#experiment-plan-message");
const experimentPlanResultEl = document.querySelector("#experiment-plan-result");
const researchBriefCardEl = document.querySelector("#research-brief-card");
const researchBriefEl = document.querySelector("#research-brief");
const patchCardEl = document.querySelector("#patch-card");
const patchesEl = document.querySelector("#patches");
const ideaCheckForm = document.querySelector("#idea-check-form");
const ideaCheckInput = document.querySelector("#idea-check-input");
const ideaMaxPapersInput = document.querySelector("#idea-max-papers");
const ideaCheckSubmit = document.querySelector("#idea-check-submit");
const ideaCheckMessageEl = document.querySelector("#idea-check-message");
const ideaCheckResultEl = document.querySelector("#idea-check-result");
const graphCompareForm = document.querySelector("#graph-compare-form");
const graphComparePickerEl = document.querySelector("#graph-compare-picker");
const graphCompareNodesInput = document.querySelector("#graph-compare-nodes");
const graphCompareFocusInput = document.querySelector("#graph-compare-focus");
const graphCompareSubmit = document.querySelector("#graph-compare-submit");
const graphCompareMessageEl = document.querySelector("#graph-compare-message");
const graphCompareResultEl = document.querySelector("#graph-compare-result");
const graphGalleryForm = document.querySelector("#graph-gallery-form");
const graphGalleryPickerEl = document.querySelector("#graph-gallery-picker");
const graphGalleryNodesInput = document.querySelector("#graph-gallery-nodes");
const graphGallerySubmit = document.querySelector("#graph-gallery-submit");
const graphGalleryMessageEl = document.querySelector("#graph-gallery-message");
const graphGalleryEl = document.querySelector("#graph-gallery");
const analysisGraphSaveActionsEl = document.querySelector("#analysis-graph-save-actions");
const analysisGraphSaveStatusEl = document.querySelector("#analysis-graph-save-status");
const saveAnalysisGraphButton = document.querySelector("#save-analysis-graph");
const analysisOverviewActionsEl = document.querySelector("#analysis-overview-actions");
const createOverviewButton = document.querySelector("#create-overview");
const overviewStateTagEl = document.querySelector("#overview-state-tag");
const overviewStageTitleEl = document.querySelector("#overview-stage-title");
const overviewStatusMessageEl = document.querySelector("#overview-status-message");
const overviewProgressLabelEl = document.querySelector("#overview-progress-label");
const overviewCountsEl = document.querySelector("#overview-counts");
const overviewProgressBarEl = document.querySelector("#overview-progress-bar");
const overviewRetryButton = document.querySelector("#overview-retry");
const overviewSaveLaterButton = document.querySelector("#overview-save-later");
const overviewSaveButton = document.querySelector("#overview-save");
const overviewActionMessageEl = document.querySelector("#overview-action-message");
const overviewGraphTitleEl = document.querySelector("#overview-graph-title");
const overviewCanvasEl = document.querySelector("#overview-canvas");
const overviewInspectorEl = document.querySelector("#overview-inspector");
const overviewFitButton = document.querySelector("#overview-fit");
const overviewToggleEdgesButton = document.querySelector("#overview-toggle-edges");
const overviewLegendEl = document.querySelector("#overview-legend");
const overviewLegendNoteEl = document.querySelector("#overview-legend-note");
const overviewWarningsEl = document.querySelector("#overview-warnings");
const overviewHistorySelectEl = document.querySelector("#overview-history-select");
const overviewHistoryRefreshButton = document.querySelector("#overview-history-refresh");
const overviewHistoryStatusEl = document.querySelector("#overview-history-status");
const overviewSaveDialog = document.querySelector("#overview-save-dialog");
const overviewDialogConfirmButton = document.querySelector("#overview-dialog-confirm");
const overviewDialogLaterButton = document.querySelector("#overview-dialog-later");
const deleteCurrentGraphButton = document.querySelector("#delete-current-graph");
const graphSaveDialog = document.querySelector("#graph-save-dialog");
const saveGraphDialogConfirmButton = document.querySelector("#save-graph-dialog-confirm");
const saveGraphDialogLaterButton = document.querySelector("#save-graph-dialog-later");
const graphDeleteDialog = document.querySelector("#graph-delete-dialog");
const graphDeleteDialogTitleEl = document.querySelector("#graph-delete-dialog-title");
const graphDeleteDialogConfirmButton = document.querySelector("#delete-graph-dialog-confirm");
const graphDeleteDialogCancelButton = document.querySelector("#delete-graph-dialog-cancel");
const apiBaseForm = document.querySelector("#api-base-form");
const apiBaseInput = document.querySelector("#api-base-url");
const apiBaseStatusEl = document.querySelector("#api-base-status");
const apiBaseMessageEl = document.querySelector("#api-base-message");
const resetApiBaseButton = document.querySelector("#reset-api-base");
const modelSettingsForm = document.querySelector("#model-settings-form");
const modelProviderInput = document.querySelector("#explanation-provider");
const modelNameInput = document.querySelector("#explanation-model");
const modelBaseUrlInput = document.querySelector("#explanation-base-url");
const modelSettingsStatusEl = document.querySelector("#model-settings-status");
const modelSettingsMessageEl = document.querySelector("#model-settings-message");
const desktopRuntimeStatusEl = document.querySelector("#desktop-runtime-status");
const providerRuntimeSlotsEl = document.querySelector("#provider-runtime-slots");
const providerRuntimeMessageEl = document.querySelector("#provider-runtime-message");
const routeLinks = [...document.querySelectorAll("[data-route-link]")];
const appViews = [...document.querySelectorAll("[data-view]")];

const API_BASE_STORAGE_KEY = "wishforge.api_base_url";
const routes = {
  workspace: { title: "研究工作台" },
  "concept-graphs": { title: "概念图" },
  "research-overview": { title: "研究方向图" },
  innovations: { title: "创新与查重" },
  experiments: { title: "实验方案" },
  settings: { title: "设置" },
};

function normalizeApiBaseUrl(value) {
  const candidate = String(value ?? "").trim().replace(/\/+$/, "");
  if (!candidate) return "";
  if (!/^https?:\/\//i.test(candidate)) return null;
  try {
    const parsed = new URL(candidate);
    if (!["http:", "https:"].includes(parsed.protocol)) return null;
    return parsed.href.replace(/\/+$/, "");
  } catch (error) {
    return null;
  }
}

function readStoredApiBaseUrl() {
  try {
    return window.localStorage.getItem(API_BASE_STORAGE_KEY) || "";
  } catch (error) {
    return "";
  }
}

function resolveApiBaseUrl() {
  const runtimeConfig = window.WISHFORGE_RUNTIME_CONFIG || {};
  // The desktop shell owns the loopback sidecar URL. Ignore stale browser
  // preferences in that environment so requests cannot escape the App.
  if (runtimeConfig.desktop) {
    const sidecar = normalizeApiBaseUrl(runtimeConfig.apiBaseUrl || window.WISHFORGE_API_BASE_URL);
    return sidecar
      ? { value: sidecar, source: "桌面 sidecar" }
      : { value: "", source: "桌面 sidecar（等待启动）" };
  }
  const stored = normalizeApiBaseUrl(readStoredApiBaseUrl());
  if (stored) return { value: stored, source: "浏览器保存" };
  const deployed = normalizeApiBaseUrl(runtimeConfig.apiBaseUrl || window.WISHFORGE_API_BASE_URL);
  if (deployed) return { value: deployed, source: "页面配置" };
  return { value: "", source: "当前页面同源" };
}

let apiBaseConfiguration = resolveApiBaseUrl();

function apiUrl(path) {
  const requestPath = String(path || "");
  if (/^https?:\/\//i.test(requestPath) || !apiBaseConfiguration.value) return requestPath;
  return `${apiBaseConfiguration.value}${requestPath.startsWith("/") ? requestPath : `/${requestPath}`}`;
}

function apiFetch(path, options) {
  return window.fetch(apiUrl(path), options);
}

function setApiBaseMessage(text, kind = "") {
  apiBaseMessageEl.textContent = text;
  apiBaseMessageEl.className = `form-message ${kind}`;
}

function renderApiBaseConfiguration() {
  apiBaseInput.value = apiBaseConfiguration.value;
  const desktop = Boolean(window.WishForgeDesktop?.isDesktop || window.WISHFORGE_RUNTIME_CONFIG?.desktop);
  apiBaseInput.readOnly = desktop;
  apiBaseInput.setAttribute("aria-readonly", String(desktop));
  apiBaseInput.title = desktop ? "桌面 App 自动使用本地 sidecar 地址" : "";
  apiBaseForm.classList.toggle("is-desktop-managed", desktop);
  apiBaseStatusEl.textContent = apiBaseConfiguration.value
    ? `${apiBaseConfiguration.source} · 已设置`
    : "当前页面同源";
  apiBaseStatusEl.className = `tag ${apiBaseConfiguration.value ? "tag-configured" : "tag-missing"}`;
}

function renderDesktopRuntimeStatus() {
  if (!desktopRuntimeStatusEl) return;
  const desktop = Boolean(window.WishForgeDesktop?.isDesktop || window.WISHFORGE_RUNTIME_CONFIG?.desktop);
  desktopRuntimeStatusEl.className = `desktop-runtime-status ${desktop ? "is-desktop" : "is-browser"}`;
  if (desktop) {
    const runtime = window.WISHFORGE_RUNTIME_CONFIG || {};
    desktopRuntimeStatusEl.innerHTML = `<span class="desktop-runtime-dot" aria-hidden="true"></span><div><strong>桌面 App 已连接</strong><span>本地 FastAPI sidecar · ${escapeHtml(runtime.apiBaseUrl || "正在分配地址")}</span></div>`;
  } else {
    desktopRuntimeStatusEl.innerHTML = '<span class="desktop-runtime-dot" aria-hidden="true"></span><div><strong>浏览器开发模式</strong><span>使用当前页面或设置中的本地后端地址</span></div>';
  }
}

function setStoredApiBaseUrl(value) {
  try {
    if (value) {
      window.localStorage.setItem(API_BASE_STORAGE_KEY, value);
    } else {
      window.localStorage.removeItem(API_BASE_STORAGE_KEY);
    }
    return true;
  } catch (error) {
    return false;
  }
}

function currentRoute() {
  const route = window.location.hash.replace(/^#/, "").split(/[/?]/, 1)[0];
  return routes[route] ? route : "workspace";
}

function renderRoute(route = currentRoute()) {
  const activeRoute = routes[route] ? route : "workspace";
  appViews.forEach((view) => {
    const isActive = view.dataset.view === activeRoute;
    view.classList.toggle("is-active", isActive);
    view.setAttribute("aria-hidden", String(!isActive));
  });
  routeLinks.forEach((link) => {
    const isActive = link.dataset.routeLink === activeRoute;
    link.classList.toggle("is-active", isActive);
    if (isActive) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
  document.title = `${routes[activeRoute].title} · 许愿机 / WishForge`;
  if (activeRoute === "research-overview") {
    if (!state.overviewHistoryLoaded && !state.overviewHistoryLoading) {
      loadOverviewHistory({ autoOpen: true }).catch(() => {});
    }
    window.requestAnimationFrame(() => {
      state.overviewRenderer?.resize();
      state.overviewRenderer?.fit();
    });
  } else if (activeRoute === "concept-graphs") {
    window.requestAnimationFrame(() => {
      state.conceptGraphRenderer?.resize();
      state.conceptGraphRenderer?.fit();
    });
  }
}

function navigateTo(route, selector = "") {
  const nextRoute = routes[route] ? route : "workspace";
  if (window.location.hash === `#${nextRoute}`) {
    renderRoute(nextRoute);
  } else {
    window.location.hash = nextRoute;
    renderRoute(nextRoute);
  }
  if (selector) {
    window.requestAnimationFrame(() => {
      document.querySelector(selector)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
}

const state = {
  analysisId: null,
  analysisResult: null,
  graphId: null,
  graph: null,
  graphs: [],
  analysisGraphSaveState: null,
  graphSavePromptedForAnalysis: null,
  graphSaveDialogAction: null,
  pendingGraphDeletion: null,
  pendingPatches: new Map(),
  experimentPlan: null,
  ideaCheck: null,
  conceptGraphRenderer: null,
  conceptGraphSelectedNodeId: null,
  overviewId: null,
  overviewAnalysisId: null,
  overviewJob: null,
  overviewGraph: null,
  overviewRenderer: null,
  overviewPollTimer: null,
  overviewSavePromptedForId: null,
  overviewSelectedNodeId: null,
  overviewLowConfidenceVisible: true,
  overviewJobs: [],
  overviewHistoryLoaded: false,
  overviewHistoryLoading: false,
  graphGalleryRenderers: new Map(),
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

function graphSaveState(graph = state.graph, result = state.analysisResult) {
  const explicitValues = [
    graph?.save_state,
    graph?.save_status,
    result?.graph_save_state,
    result?.graph_save_status,
  ];
  const explicit = explicitValues.find((value) => value === "transient" || value === "saved");
  if (explicit) return explicit;
  if (
    state.analysisGraphSaveState
    && result?.graph?.id
    && graph?.id === result.graph.id
  ) {
    return state.analysisGraphSaveState;
  }
  if (graph?.id && state.graphs.some((item) => item.id === graph.id)) return "saved";
  return null;
}

function isTransientAnalysisGraph(result = state.analysisResult, graph = state.graph) {
  if (!result?.graph || !graph || result.graph.id !== graph.id) return false;
  return graphSaveState(graph, result) === "transient";
}

function isSavedGraph(graph = state.graph) {
  return Boolean(graph && graphSaveState(graph, state.analysisResult) === "saved");
}

function renderGraphLifecycleControls(graph = state.graph) {
  const transient = Boolean(graph && graphSaveState(graph, state.analysisResult) === "transient");
  nodeForm?.classList.toggle("hidden", !graph);
  graphActionsEl?.classList.toggle("hidden", !graph);
  graphAgentForm?.classList.toggle("hidden", !graph);
  graphLifecycleNoteEl?.classList.toggle("hidden", !transient);
  if (graphLifecycleNoteEl) {
    graphLifecycleNoteEl.textContent = transient
      ? "这是分析历史中的临时概念图：可直接编辑并审核 Agent 提案；只有确认保存后才会进入图库。"
      : "";
  }
}

function extractGraphFromResponse(payload) {
  if (!payload || typeof payload !== "object") return null;
  const candidates = [payload.graph, payload.saved_graph, payload.result];
  for (const candidate of candidates) {
    if (candidate && typeof candidate === "object" && Array.isArray(candidate.nodes)) return candidate;
  }
  if (Array.isArray(payload.nodes) && payload.root_id) return payload;
  return null;
}

function setAnalysisGraphSaveState(value, graph = state.graph) {
  if (value !== "transient" && value !== "saved") return;
  state.analysisGraphSaveState = value;
  if (graph && typeof graph === "object") graph.save_state = value;
  if (state.analysisResult && typeof state.analysisResult === "object") {
    state.analysisResult.graph_save_state = value;
    if (state.analysisResult.graph && typeof state.analysisResult.graph === "object") {
      state.analysisResult.graph.save_state = value;
    }
  }
  renderAnalysisGraphSaveControls();
}

function renderAnalysisGraphSaveControls() {
  if (!analysisGraphSaveActionsEl || !analysisGraphSaveStatusEl || !saveAnalysisGraphButton) return;
  const isAnalysisGraph = Boolean(
    state.analysisId
    && state.analysisResult?.graph?.id
    && state.graph?.id === state.analysisResult.graph.id,
  );
  const saveState = isAnalysisGraph ? graphSaveState(state.graph, state.analysisResult) : null;
  analysisGraphSaveActionsEl.classList.toggle("hidden", !isAnalysisGraph || !saveState);
  saveAnalysisGraphButton.classList.toggle("hidden", saveState !== "transient");
  saveAnalysisGraphButton.disabled = false;
  if (saveState === "saved") {
    analysisGraphSaveStatusEl.textContent = "这张图已保存到概念图库；历史分析快照仍会保留。";
  } else if (saveState === "transient") {
    analysisGraphSaveStatusEl.textContent = "这张图暂时保留在分析历史中，保存后可以在概念图库继续编辑。";
  } else {
    analysisGraphSaveStatusEl.textContent = "";
  }
}

function showDialog(dialog) {
  if (!dialog) return;
  if (typeof dialog.showModal === "function") {
    if (!dialog.open) dialog.showModal();
    window.requestAnimationFrame(() => dialog.querySelector("[autofocus]")?.focus());
    return;
  }
  dialog.setAttribute("open", "");
  dialog.classList.add("is-open");
  window.requestAnimationFrame(() => dialog.querySelector("[autofocus]")?.focus());
}

function closeDialog(dialog) {
  if (!dialog) return;
  if (typeof dialog.close === "function" && dialog.open) {
    dialog.close();
    return;
  }
  dialog.removeAttribute("open");
  dialog.classList.remove("is-open");
}

function openGraphSaveDialog() {
  if (!isTransientAnalysisGraph()) return;
  state.graphSaveDialogAction = null;
  showDialog(graphSaveDialog);
}

function deferGraphSave() {
  if (!isTransientAnalysisGraph()) {
    closeDialog(graphSaveDialog);
    return;
  }
  state.graphSaveDialogAction = "later";
  closeDialog(graphSaveDialog);
  renderAnalysisGraphSaveControls();
  setAnalysisMessage("概念图暂不保存；它仍保留在本次分析历史中。", "");
}

async function saveAnalysisGraph() {
  if (!state.analysisId || !isTransientAnalysisGraph()) return null;
  const graph = state.graph || state.analysisResult?.graph;
  const body = { expected_version: graph?.version ?? undefined };
  if (graph?.name) body.name = graph.name;
  saveAnalysisGraphButton.disabled = true;
  setAnalysisMessage("正在保存概念图…", "");
  try {
    const response = await apiFetch(
      `/api/v1/analyses/${encodeURIComponent(state.analysisId)}/graph/save`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    if (!response.ok) throw new Error(await response.text());
    const payload = await response.json();
    const savedGraph = extractGraphFromResponse(payload);
    if (savedGraph) {
      state.graph = savedGraph;
      state.graphId = savedGraph.id || state.graphId;
      if (state.analysisResult) state.analysisResult.graph = savedGraph;
      renderGraph(savedGraph);
    } else {
      const savedGraphId = payload.saved_graph_id || payload.graph_id || payload.id;
      if (savedGraphId) state.graphId = savedGraphId;
    }
    setAnalysisGraphSaveState("saved", state.graph);
    await loadGraphPicker(state.graphId);
    setAnalysisMessage("概念图已保存到概念图库。", "");
    setGraphMessage("概念图已保存；现在可以继续编辑或删除整图。", "");
    return payload;
  } finally {
    saveAnalysisGraphButton.disabled = false;
    renderAnalysisGraphSaveControls();
  }
}

function openGraphDeleteDialog(graph, source = "current") {
  if (!graph?.id) return;
  state.pendingGraphDeletion = {
    id: graph.id,
    version: Number.isFinite(Number(graph.version)) ? Number(graph.version) : null,
    name: graph.name || "未命名概念图",
    source,
  };
  if (graphDeleteDialogTitleEl) graphDeleteDialogTitleEl.textContent = `删除“${graph.name || "未命名概念图"}”？`;
  if (graphDeleteDialogConfirmButton) graphDeleteDialogConfirmButton.disabled = false;
  showDialog(graphDeleteDialog);
}

function closeGraphDeleteDialog() {
  closeDialog(graphDeleteDialog);
  state.pendingGraphDeletion = null;
}

function resetGraphViewAfterDeletion() {
  state.graphId = null;
  state.graph = null;
  state.pendingPatches.clear();
  state.conceptGraphRenderer?.destroy();
  state.conceptGraphRenderer = null;
  graphVersionEl.textContent = "v—";
  graphPickerEl.classList.add("hidden");
  graphPickerEl.innerHTML = "";
  graphEl.className = "graph-placeholder";
  graphEl.textContent = "在工作台完成分析后会生成概念关系图。";
  graphLifecycleNoteEl?.classList.add("hidden");
  if (graphLifecycleNoteEl) graphLifecycleNoteEl.textContent = "";
  nodeForm.classList.add("hidden");
  graphActionsEl.classList.add("hidden");
  graphAgentForm.classList.add("hidden");
  graphMetaForm.classList.add("hidden");
  deleteCurrentGraphButton?.classList.add("hidden");
  renderPatches();
}

function removeGalleryGraphCard(graphId) {
  state.graphGalleryRenderers.get(String(graphId))?.destroy();
  state.graphGalleryRenderers.delete(String(graphId));
  [...graphGalleryEl.querySelectorAll("[data-gallery-graph-id]")].forEach((card) => {
    if (card.dataset.galleryGraphId === graphId) card.remove();
  });
  if (!graphGalleryEl.querySelector("[data-gallery-graph-id]") && !graphGalleryEl.querySelector(".warning-box")) {
    graphGalleryEl.innerHTML = '<p class="empty">还没有已保存的概念图。</p>';
  }
}

async function handleGraphDeleted(graphId) {
  const analysisGraphMatches = state.analysisResult?.graph?.id === graphId;
  const deletedGraph = state.graph?.id === graphId ? state.graph : state.analysisResult?.graph;
  state.graphs = state.graphs.filter((graph) => graph.id !== graphId);
  removeGalleryGraphCard(graphId);
  if (analysisGraphMatches && deletedGraph) {
    // Keep the historical snapshot available for a later save, even though it
    // no longer appears in the saved graph gallery.
    state.graph = deletedGraph;
    state.graphId = graphId;
    setAnalysisGraphSaveState("transient", deletedGraph);
    renderGraph(deletedGraph);
    setGraphMessage("已从概念图库删除；历史分析快照仍保留，可稍后再次保存。", "");
  } else if (state.graph?.id === graphId) {
    resetGraphViewAfterDeletion();
  }
  const remaining = await loadGraphPicker(analysisGraphMatches ? null : state.graphId);
  if (!analysisGraphMatches && remaining.length) {
    state.graphId = remaining[0].id;
    await refreshGraph();
  }
  if (!remaining.length && !analysisGraphMatches) resetGraphViewAfterDeletion();
}

async function deleteGraphById() {
  const pending = state.pendingGraphDeletion;
  if (!pending) return;
  if (graphDeleteDialogConfirmButton) graphDeleteDialogConfirmButton.disabled = true;
  setGraphGalleryMessage("正在删除整张概念图…", "");
  setGraphMessage("正在删除整张概念图…", "");
  try {
    const query = pending.version ? `?expected_version=${encodeURIComponent(pending.version)}` : "";
    const response = await apiFetch(`/api/v1/graphs/${encodeURIComponent(pending.id)}${query}`, { method: "DELETE" });
    if (!response.ok) {
      if (response.status === 409) await loadGraphPicker(state.graphId);
      throw new Error(await response.text());
    }
    const deletedId = pending.id;
    closeGraphDeleteDialog();
    await handleGraphDeleted(deletedId);
    setGraphGalleryMessage("概念图已删除；历史分析中的图快照仍然保留。", "");
    setGraphMessage("概念图已删除；历史分析中的图快照仍然保留。", "");
  } catch (error) {
    if (graphDeleteDialogConfirmButton) graphDeleteDialogConfirmButton.disabled = false;
    setGraphGalleryMessage(`删除失败：${error.message}`, "error-text");
    setGraphMessage(`删除失败：${error.message}`, "error-text");
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
  qualifies: "有条件支持",
  qualified_support: "有条件支持",
  background: "背景线索",
  unclear: "关系未核验",
  unverified: "未人工核验",
  reviewed: "已人工核验",
  needs_review: "待人工核验",
  dismissed: "已忽略",
  cross_domain_candidate: "跨领域候选",
  shared_problem: "共同问题",
  method_transfer: "方法迁移候选",
  initial: "首轮",
  feedback: "摘要反馈",
  not_checked: "未单独检查",
  indirect_metadata: "由论文元数据间接发现",
  checked: "已检查",
  unavailable: "检查不可用",
  no_direct_match_in_scope: "当前范围未发现直接匹配",
  matched: "发现匹配线索",
  model_generated: "模型生成",
  heuristic: "启发式生成",
  community_signal: "社区信号转化",
  paper_future_work: "论文限制线索",
  synthesis: "综合候选",
  abstract_signal: "摘要级线索",
  abstract_only: "仅依据摘要",
  full_text_verified: "全文已核验",
  supported: "已有证据关联",
  partially_supported: "部分支持",
  contradicted: "存在反驳线索",
  hypothesis: "待验证假设",
  definition: "定义",
  mechanism: "机制",
  evolution: "演变",
  limitation: "限制",
  method_limitation: "方法局限",
  failure_mode: "失败模式",
  tradeoff: "性能权衡",
  applicability_boundary: "适用边界",
  evaluation_limitation: "评估局限",
  theoretical_limit: "理论极限",
  result: "结果",
  context: "背景",
  future_work: "未来工作",
  related_concept: "相关概念",
  research_gap: "研究空白",
  core: "核心术语",
  foundational: "基础术语",
  recent: "近期术语",
  method_family: "方法族",
  application: "应用场景",
  limitations: "限制与未来工作",
  comparison: "方法对比",
  strong: "强匹配",
  moderate: "中等匹配",
  weak: "弱匹配",
  model_quote: "模型原句已定位",
  model_hint_validated: "模型提示经系统校验",
  automatic_match: "系统自动匹配",
  manual: "人工判定",
  abstract: "摘要",
  full_text: "全文",
  metadata: "元数据",
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
    const response = await apiFetch("/api/v1/health");
    if (!response.ok) throw new Error("health check failed");
    const data = await response.json();
    setHealth(`${data.service} · ${data.version}`, true);
  } catch (error) {
    setHealth("API 不可用", false);
  }
}

apiBaseForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (window.WishForgeDesktop?.isDesktop || window.WISHFORGE_RUNTIME_CONFIG?.desktop) {
    setApiBaseMessage("桌面 App 会自动管理本地 sidecar 地址，无需手动修改。", "");
    return;
  }
  const rawValue = apiBaseInput.value.trim();
  const normalized = normalizeApiBaseUrl(rawValue);
  if (rawValue && !normalized) {
    setApiBaseMessage("请输入完整的 http:// 或 https:// 后端地址，或清空后使用当前页面同源。", "error-text");
    return;
  }
  const stored = setStoredApiBaseUrl(normalized || "");
  apiBaseConfiguration = normalized
    ? { value: normalized, source: stored ? "浏览器保存" : "当前会话" }
    : resolveApiBaseUrl();
  renderApiBaseConfiguration();
  setApiBaseMessage(
    normalized
      ? `已切换到 ${apiBaseConfiguration.value}；正在刷新连接状态。`
      : "已恢复默认后端地址；正在刷新连接状态。",
    "",
  );
  loadHealth();
  loadProjects();
  loadApiKeys();
  loadModelSettings();
});

resetApiBaseButton.addEventListener("click", () => {
  if (window.WishForgeDesktop?.isDesktop || window.WISHFORGE_RUNTIME_CONFIG?.desktop) {
    setApiBaseMessage("桌面 App 会自动管理本地 sidecar 地址。", "");
    return;
  }
  const stored = setStoredApiBaseUrl("");
  apiBaseConfiguration = resolveApiBaseUrl();
  renderApiBaseConfiguration();
  setApiBaseMessage(
    stored ? "已清除浏览器保存的地址，恢复为默认连接。" : "无法写入浏览器存储，已在当前会话恢复默认连接。",
    stored ? "" : "error-text",
  );
  loadHealth();
  loadProjects();
  loadApiKeys();
  loadModelSettings();
});

function renderApiKeys(slots) {
  const detailsBySlot = {
    paper_search: {
      icon: "⌕",
      description: "用于论文检索、相关工作发现和 prior-art 查重。",
      scope: "学术资料服务",
    },
    community_search: {
      icon: "◌",
      description: "用于探索性社区信号；是否实际调用取决于后端连接器。",
      scope: "社区讨论服务",
    },
    explanation_model: {
      icon: "✦",
      description: "用于概念解释、节点解释、研究简报和假设整理。",
      scope: "语言模型服务",
    },
    experiment_runner: {
      icon: "▣",
      description: "预留给未来实验执行器；第一版仅生成可审阅的方案草案。",
      scope: "实验执行服务",
    },
  };
  apiKeysEl.innerHTML = slots.map((slot) => `
    ${(() => {
      const detail = detailsBySlot[slot.id] || {
        icon: "•",
        description: "为该服务单独配置凭据。",
        scope: "独立服务",
      };
      const inputId = `api-key-${slot.id}`;
      const ready = slot.configured || slot.credential_required === false;
      return `
        <article class="service-card api-key-row ${ready ? "is-configured" : "is-unconfigured"}" data-api-key-slot="${escapeHtml(slot.id)}">
          <div class="service-card-heading">
            <span class="service-card-icon" aria-hidden="true">${escapeHtml(detail.icon)}</span>
            <div class="service-card-title">
              <div class="setting-title-line">
                <div>
                  <p class="service-card-scope">${escapeHtml(detail.scope)}</p>
                  <h3>${escapeHtml(slot.label)}</h3>
                </div>
                <span class="service-status ${ready ? "is-configured" : "is-unconfigured"}">
                  <span aria-hidden="true" class="service-status-dot"></span>
                  ${slot.credential_required === false ? "公共接口 · 无需密钥" : slot.configured ? `已连接 ${escapeHtml(slot.masked || "")}` : "等待连接"}
                </span>
              </div>
              <p>${escapeHtml(detail.description)}</p>
              <p class="service-provider"><span class="provider-name">${escapeHtml(slot.provider)}</span><code>${escapeHtml(slot.environment_variable)}</code></p>
            </div>
          </div>
          ${slot.credential_required === false ? `
          <div class="service-card-control">
            <p class="settings-note">当前 Provider 可直接使用；无需填写 <code>${escapeHtml(slot.environment_variable)}</code>。</p>
          </div>` : `<div class="service-card-control">
            <label for="${escapeHtml(inputId)}">${slot.configured ? "更新服务密钥" : "连接服务密钥"}</label>
            <div class="service-key-row">
              <input
                id="${escapeHtml(inputId)}"
                type="password"
                class="api-key-input"
                data-api-key-input="${escapeHtml(slot.id)}"
                autocomplete="new-password"
                spellcheck="false"
                placeholder="${slot.configured ? "输入新密钥以替换（留空保持不变）" : "粘贴该用途的 API Key"}"
                aria-label="${escapeHtml(slot.label)} API Key"
              />
              <button type="button" class="secondary api-key-clear" data-api-key-clear="${escapeHtml(slot.id)}">断开</button>
            </div>
          </div>`}
        </article>
      `;
    })()}
  `).join("");
}

function setApiKeyMessage(text, kind = "") {
  apiKeyMessageEl.textContent = text;
  apiKeyMessageEl.className = `form-message ${kind}`;
}

async function loadApiKeys() {
  try {
    const response = await apiFetch("/api/v1/settings/api-keys");
    if (!response.ok) throw new Error("settings request failed");
    const data = await response.json();
    let slots = Array.isArray(data.slots) ? data.slots : [];
    // The desktop shell only returns status/masking information from Windows
    // Credential Manager. Secret values never travel back into this page.
    if (window.WishForgeDesktop?.isDesktop) {
      const statuses = await Promise.all(slots.map(async (slot) => {
        try {
          return await window.WishForgeDesktop.getCredentialStatus(slot.id);
        } catch (error) {
          return null;
        }
      }));
      slots = slots.map((slot, index) => {
        const status = statuses[index];
        return status ? {
          ...slot,
          configured: Boolean(status.configured),
          masked: status.masked || slot.masked || null,
          storage: "windows_credential_manager",
        } : slot;
      });
      data.storage = "windows_credential_manager";
    }
    renderApiKeys(slots);
    apiKeyForm.dataset.storage = data.storage || "environment";
  } catch (error) {
    apiKeysEl.innerHTML = '<p class="empty error-text">配置状态读取失败，请确认 API 正在运行。</p>';
  }
}

function setModelSettingsMessage(text, kind = "") {
  modelSettingsMessageEl.textContent = text;
  modelSettingsMessageEl.className = `form-message ${kind}`;
}

function renderModelSettings(settings) {
  modelProviderInput.value = settings.explanation_provider || "openai";
  modelNameInput.value = settings.explanation_model || "";
  modelBaseUrlInput.value = settings.explanation_base_url || "";
  const storageLabel = settings.storage === "runtime_memory" ? "当前进程覆盖" : "环境配置";
  modelSettingsStatusEl.textContent = `${storageLabel} · ${settings.demo_mode ? "Demo 开启" : "正式 Provider"}`;
  modelSettingsStatusEl.className = `tag ${settings.storage === "runtime_memory" ? "tag-configured" : "tag-missing"}`;
}

const providerSlotDetails = {
  paper_search: { icon: "⌕", hint: "用于 arXiv、Semantic Scholar 等学术资料检索。" },
  community_search: { icon: "◌", hint: "用于 X、知乎、Reddit 等探索性讨论信号。" },
  explanation_model: { icon: "✦", hint: "用于概念解释、论文节点摘要和研究简报。" },
  experiment_runner: { icon: "▣", hint: "预留给实验执行器；当前只生成方案，不执行代码。" },
};

function setProviderRuntimeMessage(text, kind = "") {
  if (!providerRuntimeMessageEl) return;
  providerRuntimeMessageEl.textContent = text;
  providerRuntimeMessageEl.className = `form-message ${kind}`;
}

function renderProviderRuntimeSlots(slots) {
  if (!providerRuntimeSlotsEl) return;
  if (!Array.isArray(slots) || !slots.length) {
    providerRuntimeSlotsEl.innerHTML = '<p class="empty">后端尚未返回用途配置。</p>';
    return;
  }
  providerRuntimeSlotsEl.innerHTML = slots.map((slot) => {
    const detail = providerSlotDetails[slot.id] || { icon: "•", hint: "独立 Provider 配置。" };
    const credentialNote = slot.credential_required === false
      ? "公共或本地 Provider，无需 API Key"
      : slot.credential_configured ? "API Key 已配置（密钥单独存储）" : "需要配置对应用途的 API Key";
    return `
      <article class="provider-runtime-slot" data-provider-slot="${escapeHtml(slot.id)}">
        <div class="provider-runtime-slot-heading">
          <span class="service-card-icon" aria-hidden="true">${escapeHtml(detail.icon)}</span>
          <div><h3>${escapeHtml(slot.label)}</h3><p>${escapeHtml(detail.hint)}</p></div>
          <span class="tag ${slot.enabled ? "tag-configured" : "tag-missing"}">${slot.enabled ? "已启用" : "已关闭"}</span>
        </div>
        <div class="provider-runtime-form-grid">
          <label>Provider<input data-provider-field="provider" value="${escapeHtml(slot.provider || "")}" maxlength="100" /></label>
          <label>模型名称<input data-provider-field="model" value="${escapeHtml(slot.model || "")}" maxlength="200" placeholder="可留空" /></label>
          <label class="provider-base-url-field">Base URL<input data-provider-field="base_url" value="${escapeHtml(slot.base_url || "")}" type="url" placeholder="https://…/v1" /></label>
        </div>
        <div class="provider-runtime-slot-actions">
          <label class="provider-enabled-toggle"><input data-provider-field="enabled" type="checkbox" ${slot.enabled ? "checked" : ""} /> 启用此用途</label>
          <span class="settings-note">${escapeHtml(credentialNote)}</span>
          <button type="button" data-provider-action="test" class="secondary">测试连接</button>
          <button type="button" data-provider-action="save">保存此配置</button>
          <span class="provider-slot-message form-message" role="status"></span>
        </div>
      </article>`;
  }).join("");
}

async function updateProviderRuntimeSlot(slotId, payload) {
  const response = await apiFetch(`/api/v1/settings/providers/${encodeURIComponent(slotId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function providerSlotPayload(card) {
  const field = (name) => card.querySelector(`[data-provider-field="${name}"]`);
  return {
    provider: field("provider")?.value.trim() || "",
    model: field("model")?.value.trim() || null,
    base_url: field("base_url")?.value.trim() || null,
    enabled: Boolean(field("enabled")?.checked),
  };
}

async function testProviderRuntimeSlot(slotId) {
  const response = await apiFetch(`/api/v1/settings/providers/${encodeURIComponent(slotId)}/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ probe: false }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

providerRuntimeSlotsEl?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-provider-action]");
  if (!button) return;
  const card = button.closest("[data-provider-slot]");
  if (!card) return;
  const slotId = card.dataset.providerSlot;
  const message = card.querySelector(".provider-slot-message");
  const setMessage = (text, kind = "") => {
    if (message) { message.textContent = text; message.className = `provider-slot-message form-message ${kind}`; }
  };
  button.disabled = true;
  try {
    if (button.dataset.providerAction === "save") {
      const data = await updateProviderRuntimeSlot(slotId, providerSlotPayload(card));
      renderProviderRuntimeSlots(data.slots);
      setProviderRuntimeMessage("用途配置已保存；没有提交任何 API Key。", "");
    } else {
      const result = await testProviderRuntimeSlot(slotId);
      setMessage(`${result.ok ? "配置可用" : "需要处理"}：${result.message}`, result.ok ? "" : "error-text");
    }
  } catch (error) {
    setMessage(`操作失败：${error.message}`, "error-text");
  } finally {
    button.disabled = false;
  }
});

async function loadModelSettings() {
  try {
    const response = await apiFetch("/api/v1/settings/runtime");
    if (!response.ok) throw new Error("runtime settings request failed");
    const data = await response.json();
    renderModelSettings(data);
    renderProviderRuntimeSlots(data.slots);
  } catch (error) {
    modelSettingsStatusEl.textContent = "后端不可用";
    modelSettingsStatusEl.className = "tag tag-missing";
    setModelSettingsMessage("无法读取模型路由配置，请先检查后端 API 地址。", "error-text");
  }
}

modelSettingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const provider = modelProviderInput.value;
  const model = modelNameInput.value.trim();
  const baseUrl = modelBaseUrlInput.value.trim();
  if (!model || !baseUrl) {
    setModelSettingsMessage("Provider、模型名称和 Base URL 都需要填写。", "error-text");
    return;
  }
  const saveButton = document.querySelector("#save-model-settings");
  saveButton.disabled = true;
  setModelSettingsMessage("正在保存模型路由…");
  try {
    // Persist non-secret routing preferences alongside the desktop app. The
    // sidecar request below remains necessary so this running session takes
    // effect immediately; the secret itself is still handled separately by
    // Windows Credential Manager.
    if (window.WishForgeDesktop?.isDesktop) {
      await window.WishForgeDesktop.saveRuntimeSettings({
        provider,
        model,
        baseUrl,
      });
    }
    const response = await apiFetch("/api/v1/settings/runtime", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        explanation_provider: provider,
        explanation_model: model,
        explanation_base_url: baseUrl,
      }),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || "runtime settings update failed");
    }
    renderModelSettings(await response.json());
    setModelSettingsMessage(window.WishForgeDesktop?.isDesktop
      ? "模型路由已保存到桌面 App，并已同步到当前 sidecar。"
      : "模型路由已保存；后续分析会使用当前进程配置。", "");
  } catch (error) {
    setModelSettingsMessage(`保存失败：${error.message}`, "error-text");
  } finally {
    saveButton.disabled = false;
  }
});

async function updateApiKeys(payload) {
  const response = await apiFetch("/api/v1/settings/api-keys", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

apiKeyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {};
  apiKeysEl.querySelectorAll("[data-api-key-input]").forEach((input) => {
    const value = input.value.trim();
    if (value) payload[input.dataset.apiKeyInput] = value;
  });
  if (!Object.keys(payload).length) {
    setApiKeyMessage("没有新的密钥需要保存；留空会保持现有值。", "");
    return;
  }
  saveApiKeysButton.disabled = true;
  setApiKeyMessage(window.WishForgeDesktop?.isDesktop
    ? "正在保存到系统凭据库并更新 sidecar…"
    : "正在更新当前进程配置…");
  try {
    if (window.WishForgeDesktop?.isDesktop) {
      for (const [slot, value] of Object.entries(payload)) {
        await window.WishForgeDesktop.setCredential(slot, value);
      }
    }
    const data = await updateApiKeys(payload);
    await loadApiKeys();
    apiKeyForm.dataset.storage = window.WishForgeDesktop?.isDesktop
      ? "windows_credential_manager"
      : (data.storage || "runtime_memory");
    setApiKeyMessage(window.WishForgeDesktop?.isDesktop
      ? "已保存到 Windows Credential Manager，并同步到本次 sidecar 会话。"
      : "已保存。密钥只保存在当前 API 进程内，响应中不会返回明文。", "");
  } catch (error) {
    setApiKeyMessage(`保存失败：${error.message}`, "error-text");
  } finally {
    saveApiKeysButton.disabled = false;
  }
});

apiKeysEl.addEventListener("click", async (event) => {
  const clearButton = event.target.closest("[data-api-key-clear]");
  if (!clearButton) return;
  const slot = clearButton.dataset.apiKeyClear;
  clearButton.disabled = true;
  setApiKeyMessage(window.WishForgeDesktop?.isDesktop
    ? "正在从系统凭据库和 sidecar 会话中清除…"
    : "正在清除当前进程中的该密钥…");
  try {
    if (window.WishForgeDesktop?.isDesktop) {
      await window.WishForgeDesktop.setCredential(slot, "");
    }
    const data = await updateApiKeys({ [slot]: "" });
    await loadApiKeys();
    apiKeyForm.dataset.storage = window.WishForgeDesktop?.isDesktop
      ? "windows_credential_manager"
      : (data.storage || "runtime_memory");
    setApiKeyMessage(window.WishForgeDesktop?.isDesktop
      ? "已从 Windows Credential Manager 和当前 sidecar 会话清除。"
      : "已清除该用途的当前进程密钥。", "");
  } catch (error) {
    setApiKeyMessage(`清除失败：${error.message}`, "error-text");
  }
});

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
    const response = await apiFetch("/api/v1/projects");
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
  stopOverviewPolling();
  state.overviewId = null;
  state.overviewJob = null;
  state.analysisId = null;
  state.analysisResult = null;
  state.overviewAnalysisId = null;
  state.graphId = null;
  state.graph = null;
  state.graphs = [];
  state.analysisGraphSaveState = null;
  state.graphSaveDialogAction = null;
  state.pendingGraphDeletion = null;
  state.pendingPatches.clear();
  destroyGraphGalleryRenderers();
  state.conceptGraphRenderer?.destroy();
  state.conceptGraphRenderer = null;
  state.overviewSavePromptedForId = null;
  closeDialog(graphSaveDialog);
  closeDialog(overviewSaveDialog);
  closeDialog(graphDeleteDialog);
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
  graphLifecycleNoteEl?.classList.add("hidden");
  if (graphLifecycleNoteEl) graphLifecycleNoteEl.textContent = "";
  nodeForm.classList.add("hidden");
  graphActionsEl.classList.add("hidden");
  graphAgentForm.classList.add("hidden");
  graphAgentRequestInput.value = "";
  graphAgentMessageEl.textContent = "";
  graphMetaForm.classList.add("hidden");
  graphNameInput.value = "";
  graphRootInput.innerHTML = "";
  analysisGraphSaveActionsEl?.classList.add("hidden");
  analysisOverviewActionsEl?.classList.add("hidden");
  if (createOverviewButton) createOverviewButton.disabled = false;
  saveAnalysisGraphButton && (saveAnalysisGraphButton.disabled = false);
  deleteCurrentGraphButton?.classList.add("hidden");
  innovationCardEl.classList.add("hidden");
  innovationsEl.innerHTML = "";
  noveltyNoteEl.textContent = "";
  evidenceLedgerEl.classList.add("hidden");
  ledgerCoverageEl.textContent = "未生成";
  ledgerMessageEl.textContent = "";
  ledgerClaimsEl.innerHTML = "";
  researchBriefCardEl.classList.add("hidden");
  researchBriefEl.innerHTML = "";
  state.experimentPlan = null;
  experimentPlanResultEl.classList.add("hidden");
  experimentPlanResultEl.innerHTML = "";
  setExperimentPlanMessage("", "");
  renderPatches();
  graphGalleryEl.innerHTML = '<p class="empty">正在读取概念图列表…</p>';
  setGraphGalleryMessage("", "");
  resetOverviewView();
  renderOverviewHistory();
}

function renderExplanation(result) {
  const explanation = result.explanation;
  const warnings = (result.warnings || []).map((item) => friendlyAnalysisWarning(item));
  const modelOutputWarnings = explanation.model_output_warnings || [];
  const paperById = new Map((result.papers || []).map((paper) => [paper.id, paper]));
  const evolutionItems = explanation.evolution_items || [];
  const researchLimitations = explanation.research_limitations || [];
  const usesStructuredClaims = Boolean(
    (explanation.claims || []).length
    || (explanation.scope_warnings || []).length
    || (explanation.research_gap_candidates || []).length
    || (explanation.reproducibility_checks || []).length
  );
  const limitationHtml = researchLimitations.length
    ? `<div class="structured-note-list">${researchLimitations.map((item) => `
        <article class="structured-note limitation-note">
          <strong>${escapeHtml(item.text)}</strong>
          <p>${escapeHtml(item.target)}${item.condition ? ` · 条件：${escapeHtml(item.condition)}` : ""}</p>
          <small>${escapeHtml(displayLabel(item.limitation_kind))} · 后果：${escapeHtml(item.consequence)} · ${escapeHtml((item.evidence_ids || []).length)} 条摘要证据</small>
        </article>
      `).join("")}</div>`
    : `<ul>${(!usesStructuredClaims ? (explanation.limitations || []) : []).map((item) => `<li>${escapeHtml(item)}</li>`).join("") || "<li>当前摘要没有提供满足条件的明确研究局限。</li>"}</ul>`;
  const evolutionHtml = evolutionItems.length
    ? `<ol class="evolution-timeline">${evolutionItems.map((item) => {
        const sources = (item.paper_ids || []).map((paperId) => {
          const paper = paperById.get(paperId);
          if (!paper) return "";
          const sourceUrl = safeExternalUrl(paper.url);
          const label = escapeHtml(paper.title);
          return sourceUrl
            ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">${label} ↗</a>`
            : `<span>${label}</span>`;
        }).filter(Boolean).join("");
        return `<li>
          <span class="timeline-year">${escapeHtml(item.year || "年份未知")}</span>
          <div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.summary)}</p>
          <small>${sources || "未关联可打开的论文来源"} · ${escapeHtml((item.evidence_ids || []).length)} 条摘要证据</small></div>
        </li>`;
      }).join("")}</ol>`
    : `<ol>${(explanation.evolution || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("") || "<li>暂无足够资料</li>"}</ol>`;
  explanationEl.innerHTML = `
    ${warnings.length ? `<div class="warning-box"><strong>需要注意</strong><ul>${warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
    ${modelOutputWarnings.length ? `<div class="model-output-note"><strong>模型输出修复记录</strong><ul>${modelOutputWarnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
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
        ${evolutionHtml}
      </div>
      <div class="explanation-section">
        <p class="section-label">相关概念</p>
        <div class="chip-list">${(explanation.related_concepts || []).map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("") || "<span class=\"muted\">暂无</span>"}</div>
      </div>
    </section>
    <section class="explanation-section">
      <p class="section-label">当前研究的局限性</p>
      ${limitationHtml}
    </section>
    ${(explanation.research_gap_candidates || []).length ? `
      <section class="explanation-section">
        <p class="section-label">研究空白候选（待扩大检索）</p>
        <ul>${explanation.research_gap_candidates.map((item) => `<li>${escapeHtml(item.text)}<small class="ledger-scope">${escapeHtml(item.scope)}</small></li>`).join("")}</ul>
      </section>` : ""}
    ${(explanation.reproducibility_checks || []).length ? `
      <section class="explanation-section">
        <p class="section-label">复现检查</p>
        <ul>${explanation.reproducibility_checks.map((item) => `<li>${escapeHtml(item.text)} <span class="tag">${escapeHtml(item.check_type)}</span></li>`).join("")}</ul>
      </section>` : ""}
    ${(explanation.scope_warnings || []).length ? `
      <section class="explanation-section scope-warning-section">
        <p class="section-label">本次调研范围提醒</p>
        <ul>${explanation.scope_warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </section>` : ""}
    <p class="evidence-link-note">本次解释关联 ${escapeHtml((explanation.evidence_ids || []).length)} 张证据卡；摘要级证据仍需人工核对全文。</p>
  `;
}

function friendlyAnalysisWarning(value) {
  const warning = String(value || "");
  if (
    warning.includes("validation errors for ExplanationResult")
    || warning.includes("reproducibility_checks.")
    || warning.includes("pydantic.dev")
  ) {
    return "解释模型返回的结构化字段格式不符合约定，该次旧结果已使用规则回退；重新分析后系统会逐条修复可选字段并保留其他有效内容。";
  }
  return warning;
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
  const queryItems = result.retrieval_queries?.length
    ? result.retrieval_queries.map((item) => `<span class="query-angle"><b>${escapeHtml(displayLabel(item.phase || "initial"))} · ${escapeHtml(displayLabel(item.purpose))}</b>${escapeHtml(item.query)}</span>`).join("")
    : (result.search_terms || []).map((item) => `<span class="query-angle">${escapeHtml(item)}</span>`).join("");
  const timingItems = (result.stage_timings || []).map((item) =>
    `<span>${escapeHtml(item.label)} ${(Number(item.duration_ms || 0) / 1000).toFixed(1)}s</span>`
  ).join("");
  const retrievalSummary = result.search_terms?.length || timingItems
    ? `<div class="retrieval-summary"><strong>本次检索范围：</strong>${escapeHtml(result.retrieval_scope || "摘要和元数据")}
        ${queryItems ? `<div class="query-angle-list">${queryItems}</div>` : ""}
        ${timingItems ? `<div class="timing-list"><strong>阶段耗时：</strong>${timingItems}<span>总计 ${(Number(result.total_duration_ms || 0) / 1000).toFixed(1)}s</span></div>` : ""}
        <div class="paper-list-actions"><button type="button" class="secondary" data-paper-action="expand">展开全部论文</button><button type="button" class="secondary" data-paper-action="collapse">收起全部论文</button></div>
      </div>`
    : "";
  papersEl.innerHTML = retrievalSummary + result.papers.map((paper) => {
    const sourceUrl = safeExternalUrl(paper.url);
    const abstract = paper.abstract || "暂无摘要";
    const preview = abstract.length > 320 ? `${abstract.slice(0, 320).trim()}…` : abstract;
    const paperEvidence = evidenceByPaper.get(paper.id) || [];
    return `
    <article class="paper-row">
      <div class="paper-main">
        <div class="paper-title-line">
          <h3>${escapeHtml(paper.title)}</h3>
          <span class="tag ${paper.source_kind === "demo" ? "tag-missing" : "tag-configured"}">${escapeHtml(displayLabel(paper.source_kind))}</span>
        </div>
        <p class="paper-meta">${escapeHtml((paper.authors || []).slice(0, 3).join(", ") || "作者未提供")} · ${escapeHtml(paper.year || "年份未知")} · ${escapeHtml(paper.venue || paper.source)} · ${escapeHtml(displayLabel(paper.access_type))}</p>
        <p class="paper-abstract paper-abstract-preview">${escapeHtml(preview)}</p>
        <details class="paper-details">
          <summary>展开完整摘要与 ${escapeHtml(paperEvidence.length)} 条分类证据</summary>
          <p class="paper-abstract paper-abstract-full">${escapeHtml(abstract)}</p>
          ${paperEvidence.map((item) => {
            const evidenceTypes = item.evidence_types?.length
              ? item.evidence_types
              : [item.evidence_type || "context"];
            const reviewStatus = item.verification_status === "reviewed"
              ? `已人工核验${item.reviewed_by ? ` · ${item.reviewed_by}` : ""}`
              : "摘要候选 · 未人工核验";
            return `
              <div class="evidence-item">
                <span class="evidence-label">${evidenceTypes.map((type) => escapeHtml(displayLabel(type))).join(" + ")} · ${escapeHtml(reviewStatus)}</span>
                <p>${escapeHtml(item.excerpt)}</p>
                <small>${escapeHtml(item.location || item.locator?.kind || "摘要")} · ${escapeHtml(item.claim)}</small>
                ${item.review_note ? `<small class="review-note">核验记录：${escapeHtml(item.review_note)}</small>` : ""}
              </div>
            `;
          }).join("")}
        </details>
      </div>
      ${sourceUrl ? `<a class="source-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">打开来源 ↗</a>` : ""}
    </article>
  `;
  }).join("");
}

function renderEvidenceLedger(result) {
  const ledger = result.evidence_ledger;
  if (!ledger) {
    evidenceLedgerEl.classList.add("hidden");
    ledgerClaimsEl.innerHTML = "";
    return;
  }
  evidenceLedgerEl.classList.remove("hidden");
  const linkCoverage = Math.round(Number(ledger.link_coverage ?? ledger.coverage ?? 0) * 100);
  const verifiedCoverage = Math.round(Number(ledger.verified_coverage || 0) * 100);
  const directCoverage = Math.round(Number(ledger.direct_support_coverage || 0) * 100);
  const qualifiedCoverage = Math.round(Number(ledger.qualified_coverage || 0) * 100);
  ledgerCoverageEl.textContent = `摘要关联 ${linkCoverage}% · 系统判为直接支持 ${directCoverage}% · 有条件支持 ${qualifiedCoverage}% · 人工确认 ${verifiedCoverage}%`;
  ledgerMessageEl.textContent = (ledger.warnings || []).join(" ") || "每条主张都可以展开查看关联证据。";
  const evidenceById = new Map((result.evidence || []).map((item) => [item.id, item]));
  const paperById = new Map((result.papers || []).map((item) => [item.id, item]));
  const renderClaim = (claim) => {
    const links = (claim.evidence_links || []).map((link) => {
      const card = evidenceById.get(link.evidence_id);
      const paper = card ? paperById.get(card.paper_id) : null;
      const sourceUrl = safeExternalUrl(paper?.url || card?.source_url);
      const reviewMeta = link.verification_status === "reviewed"
        ? `已由 ${link.reviewed_by || "研究者"} 核验${link.reviewed_at ? ` · ${new Date(link.reviewed_at).toLocaleString()}` : ""}`
        : "尚未人工确认";
      return `<li class="ledger-link">
        <div class="ledger-link-tags">
          <span class="tag">${escapeHtml(displayLabel(link.relation || "background"))}</span>
          <span class="tag">${escapeHtml(displayLabel(link.match_strength || "weak"))}</span>
          <span class="tag">${escapeHtml(displayLabel(link.evidence_scope || "unknown"))}</span>
          <span class="tag ${link.verification_status === "reviewed" ? "tag-configured" : "tag-missing"}">${escapeHtml(displayLabel(link.verification_status || "unverified"))}</span>
        </div>
        <p>${escapeHtml(card?.excerpt || card?.claim || link.evidence_id)}</p>
        <small>${escapeHtml(paper?.title || card?.paper_id || "来源未知")} · ${escapeHtml(displayLabel(link.origin || "automatic_match"))} · ${escapeHtml(link.note || "")}</small>
        ${sourceUrl ? `<a class="inline-source-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">打开论文来源 ↗</a>` : ""}
        ${link.review_note ? `<small class="review-note">核验记录：${escapeHtml(link.review_note)} · ${escapeHtml(reviewMeta)}</small>` : `<small>${escapeHtml(reviewMeta)}</small>`}
        <div class="evidence-review-actions" aria-label="人工核验此主张与证据的关系">
          <button type="button" class="secondary" data-evidence-review="supports" data-claim-id="${escapeHtml(claim.id)}" data-evidence-id="${escapeHtml(link.evidence_id)}">支持</button>
          <button type="button" class="secondary" data-evidence-review="qualifies" data-claim-id="${escapeHtml(claim.id)}" data-evidence-id="${escapeHtml(link.evidence_id)}">有条件</button>
          <button type="button" class="secondary" data-evidence-review="contradicts" data-claim-id="${escapeHtml(claim.id)}" data-evidence-id="${escapeHtml(link.evidence_id)}">反驳</button>
          <button type="button" class="secondary" data-evidence-review="background" data-claim-id="${escapeHtml(claim.id)}" data-evidence-id="${escapeHtml(link.evidence_id)}">仅背景</button>
        </div>
      </li>`;
    }).join("");
    const statusClass = ["supported", "partially_supported"].includes(claim.status) ? "tag-configured" : "tag-missing";
    return `
      <details class="ledger-claim ${escapeHtml(claim.status || "unverified")}" data-has-evidence="${links ? "true" : "false"}">
        <summary class="ledger-claim-heading">
          <span class="tag">${escapeHtml(displayLabel(claim.claim_type || "definition"))}</span>
          <span class="ledger-claim-preview">${escapeHtml(claim.text)}</span>
          <span class="tag ${statusClass}">${escapeHtml(displayLabel(claim.status || "unverified"))}</span>
        </summary>
        <div class="ledger-claim-body">
          <p>${escapeHtml(claim.text)}</p>
          ${claim.scope ? `<small class="ledger-scope">${escapeHtml(claim.scope)}</small>` : ""}
          ${links ? `<ul class="ledger-links">${links}</ul>` : `<p class="warning-inline">缺少达到匹配阈值的摘要证据。${escapeHtml(claim.next_action || "需要人工核验")}</p>`}
        </div>
      </details>
    `;
  };
  const grouped = new Map();
  (ledger.claims || []).forEach((claim) => {
    const items = grouped.get(claim.claim_type) || [];
    items.push(claim);
    grouped.set(claim.claim_type, items);
  });
  const groupsHtml = [...grouped.entries()].map(([claimType, claims], index) => `
    <details class="ledger-group" ${index === 0 ? "open" : ""}>
      <summary><span>${escapeHtml(displayLabel(claimType))}</span><small>${claims.length} 条主张 · ${claims.filter((claim) => claim.evidence_links?.length).length} 条有摘要关联 · ${claims.filter((claim) => claim.evidence_links?.some((link) => link.verification_status === "reviewed")).length} 条已人工确认</small></summary>
      <div class="ledger-group-content">${claims.map(renderClaim).join("")}</div>
    </details>
  `).join("");
  ledgerClaimsEl.innerHTML = `
    <div class="ledger-toolbar">
      <button type="button" class="secondary" data-ledger-action="expand">展开全部</button>
      <button type="button" class="secondary" data-ledger-action="collapse">收起全部</button>
      <button type="button" class="secondary" data-ledger-action="missing" aria-pressed="false">只看无摘要关联</button>
    </div>
    ${groupsHtml || '<p class="empty">当前没有可展示的主张。</p>'}
  `;
}

papersEl.addEventListener("click", (event) => {
  const button = event.target.closest("[data-paper-action]");
  if (!button) return;
  const shouldOpen = button.dataset.paperAction === "expand";
  papersEl.querySelectorAll("details.paper-details").forEach((details) => {
    details.open = shouldOpen;
  });
});

ledgerClaimsEl.addEventListener("click", async (event) => {
  const reviewButton = event.target.closest("[data-evidence-review]");
  if (reviewButton) {
    if (!state.analysisId) {
      setAnalysisMessage("当前分析任务 ID 不可用，无法保存核验记录。", "error-text");
      return;
    }
    const reviewNote = window.prompt("请写下核验依据或适用条件（至少 2 个字）：");
    if (reviewNote === null) return;
    if (reviewNote.trim().length < 2) {
      setAnalysisMessage("核验记录至少需要 2 个字。", "error-text");
      return;
    }
    reviewButton.disabled = true;
    try {
      const response = await apiFetch(
        `/api/v1/analyses/${encodeURIComponent(state.analysisId)}/claims/${encodeURIComponent(reviewButton.dataset.claimId)}/evidence/${encodeURIComponent(reviewButton.dataset.evidenceId)}/review`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            relation: reviewButton.dataset.evidenceReview,
            review_note: reviewNote.trim(),
            reviewed_by: "本地研究者",
          }),
        },
      );
      if (!response.ok) throw new Error(await response.text());
      const job = await response.json();
      renderAnalysis(job.result);
      setAnalysisMessage("人工核验记录已保存。", "success-text");
    } catch (error) {
      reviewButton.disabled = false;
      setAnalysisMessage(`保存核验记录失败：${error.message}`, "error-text");
    }
    return;
  }
  const button = event.target.closest("[data-ledger-action]");
  if (!button) return;
  const action = button.dataset.ledgerAction;
  if (["expand", "collapse"].includes(action)) {
    const shouldOpen = action === "expand";
    ledgerClaimsEl.querySelectorAll("details").forEach((details) => {
      details.open = shouldOpen;
    });
    return;
  }
  if (action === "missing") {
    const active = button.getAttribute("aria-pressed") !== "true";
    button.setAttribute("aria-pressed", String(active));
    button.textContent = active ? "显示全部主张" : "只看无摘要关联";
    ledgerClaimsEl.querySelectorAll(".ledger-claim").forEach((claim) => {
      claim.classList.toggle("is-filtered-out", active && claim.dataset.hasEvidence === "true");
    });
    ledgerClaimsEl.querySelectorAll(".ledger-group").forEach((group) => {
      const hasMissing = [...group.querySelectorAll(".ledger-claim")]
        .some((claim) => claim.dataset.hasEvidence === "false");
      group.classList.toggle("is-filtered-out", active && !hasMissing);
      if (active && hasMissing) group.open = true;
    });
  }
});

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
      <div class="innovation-actions">
        <button type="button" class="secondary experiment-from-candidate" data-experiment-candidate="${escapeHtml([candidate.title, candidate.problem, candidate.mechanism].filter(Boolean).join("；"))}">生成实验方案</button>
      </div>
    </article>
  `).join("");
  noveltyNoteEl.textContent = result.novelty_note || "当前没有可用的新颖性范围说明。";
}

const experimentStatusLabels = {
  draft: "草案",
  needs_review: "待审阅",
  approved: "已批准（未执行）",
  rejected: "已拒绝",
  not_started: "尚未执行",
};

function experimentStatusLabel(value) {
  return experimentStatusLabels[value] || displayLabel(value) || "未知";
}

function setExperimentPlanMessage(text, kind = "") {
  experimentPlanMessageEl.textContent = text;
  experimentPlanMessageEl.className = `form-message ${kind}`;
}

function renderExperimentList(items, renderItem, emptyText = "暂无") {
  if (!Array.isArray(items) || !items.length) return `<p class="empty">${escapeHtml(emptyText)}</p>`;
  return `<div class="experiment-item-list">${items.map(renderItem).join("")}</div>`;
}

function renderExperimentPlan(plan) {
  state.experimentPlan = plan;
  experimentPlanResultEl.classList.remove("hidden");
  const variables = plan.variables || [];
  const controls = plan.controls || [];
  const metrics = plan.metrics || [];
  const ablation = plan.ablation || [];
  const outcomes = plan.expected_outcomes || [];
  const failures = plan.failure_criteria || plan.risks || [];
  const resources = plan.resource_estimate || plan.resources || {};
  const provenance = plan.provenance || [];
  const approvalStatus = plan.approval_status || "draft";
  const executionStatus = plan.execution_status || "not_started";
  const reviewNote = plan.review_note || "";

  const renderVariable = (item) => `
    <article class="experiment-item">
      <div class="experiment-item-heading"><strong>${escapeHtml(item.name)}</strong><span class="tag">${escapeHtml(item.role || "independent")}</span></div>
      ${item.description ? `<p>${escapeHtml(item.description)}</p>` : ""}
      ${item.levels?.length || item.values?.length ? `<small>取值：${escapeHtml((item.levels || item.values || []).join("、"))}</small>` : ""}
      ${item.measurement ? `<small>测量：${escapeHtml(item.measurement)}</small>` : ""}
    </article>`;
  const renderControl = (item) => `
    <article class="experiment-item">
      <div class="experiment-item-heading"><strong>${escapeHtml(item.name)}</strong><span class="tag">${escapeHtml(item.control_type || item.type || "constant")}</span></div>
      ${item.description ? `<p>${escapeHtml(item.description)}</p>` : ""}
      ${item.rationale ? `<small>原因：${escapeHtml(item.rationale)}</small>` : ""}
    </article>`;
  const renderMetric = (item) => `
    <article class="experiment-item">
      <div class="experiment-item-heading"><strong>${escapeHtml(item.name)}</strong>${item.primary ? '<span class="tag tag-configured">主指标</span>' : ""}</div>
      ${item.description ? `<p>${escapeHtml(item.description)}</p>` : ""}
      <small>方向：${escapeHtml(item.direction || "monitor")}${item.unit ? ` · 单位：${escapeHtml(item.unit)}` : ""}${item.aggregation ? ` · 聚合：${escapeHtml(item.aggregation)}` : ""}</small>
    </article>`;
  const renderAblation = (item) => `
    <article class="experiment-item">
      <div class="experiment-item-heading"><strong>${escapeHtml(item.component)}</strong><span class="tag">${escapeHtml(item.ablation_type || item.type || "remove")}</span></div>
      <p>${escapeHtml(item.variant || "移除该组件")}</p>
      ${item.rationale ? `<small>原因：${escapeHtml(item.rationale)}</small>` : ""}
      ${item.expected_effect ? `<small>预期影响：${escapeHtml(item.expected_effect)}</small>` : ""}
    </article>`;
  const renderOutcome = (item) => `
    <article class="experiment-item">
      <div class="experiment-item-heading"><strong>${escapeHtml(item.scenario)}</strong><span class="tag">${escapeHtml(item.confidence || "low")}</span></div>
      <p>${escapeHtml(item.prediction)}</p>
      ${item.metric || item.threshold !== undefined ? `<small>指标：${escapeHtml(item.metric || "未指定")}${item.threshold !== undefined && item.threshold !== null ? ` · 阈值：${escapeHtml(item.threshold)}` : ""}</small>` : ""}
    </article>`;
  const renderFailure = (item) => `
    <article class="experiment-item failure-item">
      <div class="experiment-item-heading"><strong>${escapeHtml(item.condition)}</strong><span class="tag tag-missing">${escapeHtml(item.severity || "major")}</span></div>
      <p>${escapeHtml(item.action || "暂停并人工复核")}</p>
    </article>`;

  experimentPlanResultEl.innerHTML = `
    <div class="experiment-plan-heading">
      <div>
        <p class="section-label">方案草案</p>
        <h3>${escapeHtml(plan.title || "未命名实验方案")}</h3>
        <small class="experiment-plan-id">ID：${escapeHtml(plan.id || "未保存")}</small>
      </div>
      <div class="experiment-plan-status">
        <span class="tag ${approvalStatus === "approved" ? "tag-configured" : approvalStatus === "rejected" ? "tag-missing" : "tag-beta"}">审阅：${escapeHtml(experimentStatusLabel(approvalStatus))}</span>
        <span class="tag tag-missing">执行：${escapeHtml(experimentStatusLabel(executionStatus))}</span>
      </div>
    </div>
    ${(plan.warnings || []).length ? `<div class="warning-box"><strong>边界提醒</strong><ul>${plan.warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
    <div class="experiment-section-grid">
      <section class="experiment-section">
        <p class="section-label">研究假设</p>
        <p>${escapeHtml(plan.hypothesis || "暂无")}</p>
      </section>
      <section class="experiment-section">
        <p class="section-label">对照基线</p>
        <p>${escapeHtml(plan.baseline || "暂无")}</p>
      </section>
    </div>
    <section class="experiment-section"><p class="section-label">变量</p>${renderExperimentList(variables, renderVariable)}</section>
    <section class="experiment-section"><p class="section-label">控制项</p>${renderExperimentList(controls, renderControl)}</section>
    <section class="experiment-section"><p class="section-label">评估指标</p>${renderExperimentList(metrics, renderMetric)}</section>
    <section class="experiment-section"><p class="section-label">消融 / 对比</p>${renderExperimentList(ablation, renderAblation)}</section>
    <section class="experiment-section"><p class="section-label">预期结果（事前假设）</p>${renderExperimentList(outcomes, renderOutcome)}</section>
    <section class="experiment-section"><p class="section-label">失败判据</p>${renderExperimentList(failures, renderFailure)}</section>
    <section class="experiment-section">
      <p class="section-label">资源估计</p>
      <dl class="experiment-resource-grid">
        <div><dt>计算</dt><dd>${escapeHtml(resources.compute || "未指定")}</dd></div>
        <div><dt>时间</dt><dd>${escapeHtml(resources.time_estimate_hours ?? resources.wall_clock_hours ?? "未指定")} 小时</dd></div>
        <div><dt>GPU</dt><dd>${escapeHtml(resources.gpu_hours ?? "未指定")} 小时</dd></div>
        <div><dt>显存</dt><dd>${escapeHtml(resources.memory_gb ?? "未指定")} GB</dd></div>
        <div><dt>存储</dt><dd>${escapeHtml(resources.storage_gb ?? "未指定")} GB</dd></div>
        <div><dt>人员</dt><dd>${escapeHtml(resources.personnel_hours ?? "未指定")} 小时</dd></div>
      </dl>
      ${resources.notes ? `<p class="resource-note">${escapeHtml(resources.notes)}</p>` : ""}
    </section>
    <section class="experiment-section"><p class="section-label">验证步骤</p>${renderExperimentList(plan.validation_steps, (step) => `<article class="experiment-step">${escapeHtml(step)}</article>`, "暂无验证步骤")}</section>
    ${provenance.length ? `<section class="experiment-section"><p class="section-label">来源与溯源</p>${renderExperimentList(provenance, (item) => `<article class="experiment-item"><div class="experiment-item-heading"><strong>${escapeHtml(item.source)}</strong><span class="tag">${escapeHtml(item.verification_status || "unverified")}</span></div><small>${escapeHtml(item.notes || item.source_type || "用户输入")}</small></article>`)}</section>` : ""}
    <section class="experiment-review">
      <div class="experiment-review-heading">
        <div>
          <p class="section-label">人工审阅</p>
          <p class="settings-note">批准不会启动实验；执行状态会保持“尚未执行”。</p>
        </div>
        ${reviewNote ? `<span class="tag">${escapeHtml(reviewNote)}</span>` : ""}
      </div>
      <textarea rows="2" maxlength="3000" data-experiment-review-note placeholder="可选：写下审阅意见，例如先做小规模预实验">${escapeHtml(reviewNote)}</textarea>
      <div class="experiment-review-actions">
        <button type="button" data-experiment-review-status="approved">批准方案</button>
        <button type="button" class="secondary" data-experiment-review-status="needs_review">退回修改</button>
        <button type="button" class="secondary danger-button" data-experiment-review-status="rejected">拒绝方案</button>
      </div>
    </section>
  `;
}

async function createExperimentPlan(payload) {
  const response = await apiFetch("/api/v1/experiments/plans", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function reviewExperimentPlan(planId, status, note) {
  const response = await apiFetch(`/api/v1/experiments/plans/${encodeURIComponent(planId)}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, note: note || "", reviewer: "user" }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function fillExperimentIdea(idea) {
  const value = String(idea || "").trim();
  if (!value) return;
  experimentIdeaInput.value = value;
  if (!experimentTitleInput.value.trim()) experimentTitleInput.value = `验证：${value.slice(0, 80)}`;
  setExperimentPlanMessage("已填入候选想法；你可以修改后再生成方案。", "");
  navigateTo("experiments", "#experiment-card");
  window.requestAnimationFrame(() => experimentIdeaInput.focus());
}

experimentPlanForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const idea = experimentIdeaInput.value.trim();
  if (idea.length < 3) {
    setExperimentPlanMessage("请至少输入 3 个字符的研究想法。", "error-text");
    return;
  }
  const payload = { idea };
  const title = experimentTitleInput.value.trim();
  const baseline = experimentBaselineInput.value.trim();
  if (title) payload.title = title;
  if (baseline) payload.baseline = baseline;
  experimentPlanSubmit.disabled = true;
  experimentPlanResultEl.classList.add("hidden");
  setExperimentPlanMessage("正在整理实验假设与验证边界…");
  try {
    const plan = await createExperimentPlan(payload);
    renderExperimentPlan(plan);
    setExperimentPlanMessage("实验方案草案已生成；请审阅后再决定是否进入后续执行流程。", "");
  } catch (error) {
    setExperimentPlanMessage(`生成失败：${error.message}`, "error-text");
  } finally {
    experimentPlanSubmit.disabled = false;
  }
});

experimentPlanClearButton.addEventListener("click", () => {
  state.experimentPlan = null;
  experimentPlanResultEl.classList.add("hidden");
  experimentPlanResultEl.innerHTML = "";
  setExperimentPlanMessage("已清空当前方案结果。", "");
});

experimentPlanResultEl.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-experiment-review-status]");
  if (!button || !state.experimentPlan?.id) return;
  const status = button.dataset.experimentReviewStatus;
  const note = experimentPlanResultEl.querySelector("[data-experiment-review-note]")?.value.trim() || "";
  const buttons = experimentPlanResultEl.querySelectorAll("[data-experiment-review-status]");
  buttons.forEach((item) => { item.disabled = true; });
  setExperimentPlanMessage("正在保存人工审阅状态…");
  try {
    const plan = await reviewExperimentPlan(state.experimentPlan.id, status, note);
    renderExperimentPlan(plan);
    setExperimentPlanMessage(`已记录审阅状态：${experimentStatusLabel(plan.approval_status)}。执行状态仍为“${experimentStatusLabel(plan.execution_status)}”。`, "");
  } catch (error) {
    buttons.forEach((item) => { item.disabled = false; });
    setExperimentPlanMessage(`审阅失败：${error.message}`, "error-text");
  }
});

function handleExperimentCandidateClick(event) {
  const button = event.target.closest("[data-experiment-candidate]");
  if (!button) return;
  fillExperimentIdea(button.dataset.experimentCandidate);
}

innovationCardEl.addEventListener("click", handleExperimentCandidateClick);
ideaCheckResultEl.addEventListener("click", handleExperimentCandidateClick);
researchBriefCardEl.addEventListener("click", handleExperimentCandidateClick);

function renderResearchBrief(result) {
  const brief = result.research_brief;
  if (!brief) {
    researchBriefCardEl.classList.add("hidden");
    researchBriefEl.innerHTML = "";
    return;
  }
  researchBriefCardEl.classList.remove("hidden");
  const runs = brief.agent_runs || [];
  const statusText = {
    completed: "完成",
    failed: "失败",
    skipped: "跳过",
    running: "运行中",
    queued: "排队",
  };
  const roleText = {
    community: "社区 Agent",
    model_brainstorm: "脑暴 Agent",
    future_work: "论文 Future Work Agent",
    synthesis: "综合 Agent",
  };
  const renderCandidate = (candidate) => `
    <article class="brief-candidate">
      <div class="brief-candidate-heading">
        <h4>${escapeHtml(candidate.title)}</h4>
        <span class="tag tag-missing">${escapeHtml(displayLabel(candidate.source_type || "unverified"))} · ${escapeHtml(displayLabel(candidate.arxiv_status || "not_checked"))}</span>
      </div>
      <p>${escapeHtml(candidate.problem || candidate.rationale || "暂无说明")}</p>
      <small>${escapeHtml(candidate.warning || "需要人工核验")}</small>
      <div class="innovation-actions"><button type="button" class="secondary experiment-from-candidate" data-experiment-candidate="${escapeHtml([candidate.title, candidate.problem, candidate.mechanism].filter(Boolean).join("；"))}">生成实验方案</button></div>
    </article>
  `;
  researchBriefEl.innerHTML = `
    ${(brief.warnings || []).length ? `<div class="warning-box"><strong>研究边界</strong><ul>${brief.warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
    <p class="brief-synthesis">${escapeHtml(brief.synthesis || "暂无综合说明")}</p>
    <div class="agent-run-list">
      ${runs.map((run) => `
        <div class="agent-run-row">
          <div><strong>${escapeHtml(roleText[run.role] || run.role)}</strong><small>${escapeHtml(run.provider || "未标注 Provider")}</small></div>
          <span class="tag ${run.status === "completed" ? "tag-configured" : "tag-missing"}">${escapeHtml(statusText[run.status] || run.status)} · ${escapeHtml(run.summary || "暂无摘要")}</span>
        </div>
      `).join("")}
    </div>
    <div class="brief-columns">
      <section>
        <p class="section-label">社区痛点（非科学证据）</p>
        ${(brief.community_signals || []).map((signal) => `
          <article class="brief-signal"><strong>${escapeHtml(signal.title)}</strong><span>${escapeHtml(signal.platform)} · ${escapeHtml(signal.pain_point || signal.summary)}</span><small>${escapeHtml(signal.open_question || "暂无开放问题")}</small></article>
        `).join("") || '<p class="empty">没有社区信号。</p>'}
      </section>
      <section>
        <p class="section-label">论文限制 / Future Work 线索</p>
        ${(brief.future_work_signals || []).map((signal) => `
          <article class="brief-signal"><strong>${escapeHtml(signal.paper_title)}</strong><span>${escapeHtml(displayLabel(signal.section))} · ${escapeHtml(signal.claim)}</span><small>${escapeHtml(signal.excerpt || "暂无摘录")}</small></article>
        `).join("") || '<p class="empty">当前摘要中没有可提取的后续工作线索。</p>'}
      </section>
    </div>
    <section class="brief-candidates">
      <p class="section-label">综合候选（仍需核验）</p>
      ${(brief.innovation_candidates || []).map(renderCandidate).join("") || '<p class="empty">没有综合候选。</p>'}
    </section>
    <p class="brief-coverage">证据覆盖：${escapeHtml(JSON.stringify(brief.coverage || {}))} · arXiv 范围状态：${escapeHtml(brief.arxiv_status || "not_checked")}</p>
  `;
}

const noveltyLabels = {
  L0: "L0 · 直接已有工作",
  L1: "L1 · 核心方法高度相似",
  L2: "L2 · 组件或组合相似",
  L3: "L3 · 问题相近但机制不同",
  L4: "L4 · 当前范围未发现直接等价",
};

function setIdeaCheckMessage(text, kind = "") {
  ideaCheckMessageEl.textContent = text;
  ideaCheckMessageEl.className = `form-message ${kind}`;
}

function renderIdeaCheck(result) {
  state.ideaCheck = result;
  const novelty = result.novelty || {};
  const papers = result.papers || [];
  const relatedWork = result.related_work_summaries || [];
  const alternatives = result.alternative_ideas || [];
  ideaCheckResultEl.classList.remove("hidden");
  ideaCheckResultEl.innerHTML = `
    ${(result.warnings || []).length ? `<div class="warning-box"><strong>判断边界</strong><ul>${result.warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
    <div class="idea-verdict">
      <div>
        <p class="section-label">当前检索结论</p>
        <h3>${escapeHtml(noveltyLabels[result.similarity_level] || result.similarity_level || "未分级")}</h3>
        <p>${escapeHtml(result.current_conclusion || result.similarity_reason || "暂无结论")}</p>
      </div>
      <span class="tag tag-missing">置信度 ${escapeHtml(result.confidence || novelty.confidence || "low")}</span>
    </div>
    <dl class="idea-meta">
      <div><dt>匹配理由</dt><dd>${escapeHtml(result.similarity_reason || novelty.reason || "暂无")}</dd></div>
      <div><dt>检索范围</dt><dd>${escapeHtml(novelty.scope_note || result.search_scope || "标题、摘要和元数据")}</dd></div>
      <div><dt>arXiv 状态</dt><dd>${escapeHtml(displayLabel(result.arxiv_status || "not_checked"))}（没有单独查询不能当作排除证明）</dd></div>
      <div><dt>人工状态</dt><dd>${escapeHtml(displayLabel(result.manual_review_status || "needs_review"))}</dd></div>
    </dl>
    <div class="innovation-actions idea-review-actions">
      <button type="button" class="secondary" data-idea-review="reviewed">标记已核验</button>
      <button type="button" class="secondary" data-idea-review="dismissed">标记为忽略</button>
      <span class="form-message" data-idea-review-message></span>
    </div>
    ${papers.length ? `<div class="idea-papers"><p class="section-label">最相关资料（摘要级）</p>${papers.slice(0, 5).map((paper) => `
      <div class="idea-paper-row"><strong>${escapeHtml(paper.title)}</strong><span>${escapeHtml(paper.year || "年份未知")} · ${escapeHtml(displayLabel(paper.source_kind || "academic"))}</span></div>
    `).join("")}</div>` : `<p class="empty">没有返回论文，建议补充英文术语后重试。</p>`}
    ${relatedWork.length ? `<div class="idea-related-work"><p class="section-label">别人是怎么做的（摘要级易懂说明）</p>${relatedWork.slice(0, 5).map((item) => `
      <article class="idea-related-row">
        <div class="paper-title-line"><h3>${escapeHtml(item.paper_title)}</h3><span class="tag tag-missing">${escapeHtml(displayLabel(item.summary_level || "abstract_only"))}</span></div>
        <p>${escapeHtml(item.plain_language_summary)}</p>
        <dl class="idea-meta"><div><dt>核心机制线索</dt><dd>${escapeHtml(item.core_mechanism)}</dd></div><div><dt>与想法的重叠</dt><dd>${escapeHtml(item.overlap_with_idea)}</dd></div><div><dt>可能差异</dt><dd>${escapeHtml(item.possible_difference)}</dd></div></dl>
      </article>
    `).join("")}</div>` : ""}
    ${alternatives.length ? `<div class="idea-alternatives"><p class="section-label">从当前想法改造出的候选</p>${alternatives.map((candidate) => `
      <article class="innovation-row"><h3>${escapeHtml(candidate.title)}</h3><p>${escapeHtml(candidate.rationale)}</p><div class="validation-box"><strong>最小验证</strong><ol>${(candidate.validation_steps || []).map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol></div><p class="warning-inline">${escapeHtml(candidate.warning || "未验证")}</p><div class="innovation-actions"><button type="button" class="secondary experiment-from-candidate" data-experiment-candidate="${escapeHtml([candidate.title, candidate.rationale].filter(Boolean).join("；"))}">生成实验方案</button></div></article>
    `).join("")}</div>` : ""}
    <div class="validation-box"><strong>建议下一步</strong><ol>${(result.validation_steps || []).map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol></div>
  `;
}

ideaCheckResultEl.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-idea-review]");
  if (!button || !state.ideaCheck?.id) return;
  const status = button.dataset.ideaReview;
  const message = ideaCheckResultEl.querySelector("[data-idea-review-message]");
  [...ideaCheckResultEl.querySelectorAll("[data-idea-review]")].forEach((item) => { item.disabled = true; });
  if (message) message.textContent = "正在保存人工核验状态…";
  try {
    const response = await apiFetch(`/api/v1/ideas/checks/${encodeURIComponent(state.ideaCheck.id)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, reviewer: "local-user" }),
    });
    if (!response.ok) throw new Error(await response.text());
    renderIdeaCheck(await response.json());
  } catch (error) {
    if (message) {
      message.textContent = `保存失败：${error.message}`;
      message.className = "form-message error-text";
    }
    [...ideaCheckResultEl.querySelectorAll("[data-idea-review]")].forEach((item) => { item.disabled = false; });
  }
});

async function checkIdea(idea, maxPapers) {
  const response = await apiFetch("/api/v1/ideas/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idea, max_papers: maxPapers, language: "zh-CN" }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

ideaCheckForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const idea = ideaCheckInput.value.trim();
  if (!idea) return;
  ideaCheckSubmit.disabled = true;
  ideaCheckResultEl.classList.add("hidden");
  setIdeaCheckMessage("正在检索相似工作…");
  try {
    const result = await checkIdea(idea, Number(ideaMaxPapersInput.value));
    renderIdeaCheck(result);
    setIdeaCheckMessage("查重完成；请打开匹配论文并人工核对。", "");
  } catch (error) {
    setIdeaCheckMessage(`查重失败：${error.message}`, "error-text");
  } finally {
    ideaCheckSubmit.disabled = false;
  }
});

function renderGraphInspector(node, relatedEdges = []) {
  const inspector = document.querySelector("#concept-graph-inspector");
  if (!inspector || !window.WishForgeGraph?.inspectorMarkup) return;
  state.conceptGraphSelectedNodeId = node?.id || null;
  const requestedGraphId = state.graphId;
  const requestedNodeId = node?.id || null;
  const evidenceById = new Map((state.analysisResult?.evidence || []).map((item) => [item.id, item]));
  const enriched = node ? {
    ...node,
    evidence_cards: (node.evidence_ids || []).map((id) => evidenceById.get(id)).filter(Boolean),
  } : node;
  inspector.innerHTML = window.WishForgeGraph.inspectorMarkup(enriched, relatedEdges)
    + (node ? `
      <div class="graph-inspector-actions">
        ${node.editable ? `<button type="button" class="secondary node-edit" data-node-id="${escapeHtml(node.id)}">编辑节点</button>` : ""}
        <button type="button" class="secondary node-explain" data-node-explain="${escapeHtml(node.id)}">生成 AI 解释提案</button>
      </div>
    ` : "");
  inspector.classList.remove("hidden");
  if (node && isSavedGraph(state.graph)) {
    apiFetch(`/api/v1/graphs/${encodeURIComponent(state.graphId)}/nodes/${encodeURIComponent(node.id)}`)
      .then(async (response) => (response.ok ? response.json() : null))
      .then((detail) => {
        if (!detail
          || state.graphId !== requestedGraphId
          || state.conceptGraphSelectedNodeId !== requestedNodeId) return;
        const currentInspector = document.querySelector("#concept-graph-inspector");
        if (!currentInspector) return;
        const detailedNode = {
          ...detail.node,
          evidence_cards: detail.evidence || [],
          source_papers: detail.papers || [],
          inspector_warnings: detail.warnings || [],
        };
        currentInspector.innerHTML = window.WishForgeGraph.inspectorMarkup(
          detailedNode, detail.related_edges || relatedEdges,
        ) + `
          <div class="graph-inspector-actions">
            ${detailedNode.editable ? `<button type="button" class="secondary node-edit" data-node-id="${escapeHtml(detailedNode.id)}">编辑节点</button>` : ""}
            <button type="button" class="secondary node-explain" data-node-explain="${escapeHtml(detailedNode.id)}">生成 AI 解释提案</button>
          </div>`;
      })
      .catch(() => {});
  }
}

function renderGraph(graph) {
  state.graph = graph;
  state.graphId = graph.id;
  graphVersionEl.textContent = `v${graph.version}`;
  const saved = isSavedGraph(graph);
  graphPickerEl.classList.toggle("hidden", !saved && !state.graphs.length);
  if (saved) graphPickerEl.value = graph.id;
  renderGraphLifecycleControls(graph);
  graphMetaForm.classList.remove("hidden");
  graphNameInput.value = graph.name || "";
  deleteCurrentGraphButton?.classList.toggle("hidden", graphSaveState(graph, state.analysisResult) !== "saved");
  renderAnalysisGraphSaveControls();
  graphRootInput.innerHTML = graph.nodes
    .map((node) => `<option value="${escapeHtml(node.id)}">${escapeHtml(node.label)}</option>`)
    .join("");
  graphRootInput.value = graph.root_id;
  if (!window.WishForgeGraph?.createGraphRenderer) {
    graphEl.innerHTML = '<p class="error-text">图形渲染模块未加载，请通过 Vite 开发服务器或构建后的桌面资源打开应用。</p>';
    return;
  }
  const inspectorId = "concept-graph-inspector";
  let canvas = graphEl.querySelector(".concept-graph-canvas");
  let inspector = graphEl.querySelector(`#${inspectorId}`);
  if (!canvas || !inspector) {
    state.conceptGraphRenderer?.destroy();
    state.conceptGraphRenderer = null;
    graphEl.className = "interactive-graph-shell";
    graphEl.innerHTML = `
      <div class="graph-toolbar concept-graph-toolbar">
        <label class="graph-filter-control">
          <span class="sr-only">搜索节点</span>
          <input type="search" data-concept-graph-search placeholder="搜索概念、方法或论文" autocomplete="off" />
        </label>
        <label class="graph-filter-control graph-role-control">
          <span class="sr-only">按节点类型筛选</span>
          <select data-concept-graph-role aria-label="按节点类型筛选">
            <option value="">全部节点</option>
            <option value="root">根节点</option>
            <option value="concept">概念</option>
            <option value="method">方法</option>
            <option value="problem">问题</option>
            <option value="direction">研究方向</option>
            <option value="paper">论文</option>
            <option value="idea">想法</option>
            <option value="note">注释</option>
          </select>
        </label>
        <button type="button" class="secondary" data-concept-graph-fit>适应画布</button>
        <button type="button" class="secondary" data-concept-graph-save-layout ${saved ? "" : "disabled"}>保存布局</button>
        <button type="button" class="secondary" data-concept-graph-low-confidence aria-pressed="true">隐藏低置信边</button>
        <span class="settings-note">滚轮缩放 · 空白处拖动 · 节点可拖拽</span>
      </div>
      <div class="concept-graph-layout">
        <div class="concept-graph-canvas" aria-label="概念关系图"></div>
        <aside id="${inspectorId}" class="graph-inspector compact-inspector">
          <div class="graph-inspector-empty"><span>◎</span><p>点击圆形节点查看解释、证据与关系。</p></div>
        </aside>
      </div>
    `;
    canvas = graphEl.querySelector(".concept-graph-canvas");
    inspector = graphEl.querySelector(`#${inspectorId}`);
    state.conceptGraphRenderer = window.WishForgeGraph.createGraphRenderer(canvas, {
      graph,
      kind: graph.graph_kind || "concept_network",
      onNodeSelect: renderGraphInspector,
    });
    const applyGraphFilter = () => {
      const query = graphEl.querySelector("[data-concept-graph-search]")?.value || "";
      const role = graphEl.querySelector("[data-concept-graph-role]")?.value || "";
      state.conceptGraphRenderer?.filter({ query, roles: role ? [role] : [] });
    };
    graphEl.querySelector("[data-concept-graph-search]")?.addEventListener("input", applyGraphFilter);
    graphEl.querySelector("[data-concept-graph-search]")?.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const role = graphEl.querySelector("[data-concept-graph-role]")?.value || "";
      const count = state.conceptGraphRenderer?.focusMatches({
        query: event.currentTarget.value,
        roles: role ? [role] : [],
      }) || 0;
      setGraphMessage(count ? `找到 ${count} 个匹配节点。` : "没有找到匹配节点。", count ? "" : "error-text");
    });
    graphEl.querySelector("[data-concept-graph-role]")?.addEventListener("change", applyGraphFilter);
    graphEl.querySelector("[data-concept-graph-fit]")?.addEventListener("click", () => state.conceptGraphRenderer?.fit());
    graphEl.querySelector("[data-concept-graph-save-layout]")?.addEventListener("click", async (event) => {
      if (!isSavedGraph(state.graph)) return;
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const response = await apiFetch(`/api/v1/graphs/${encodeURIComponent(state.graphId)}/layout`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            expected_version: state.graph.version,
            positions: state.conceptGraphRenderer.savePositions().map((item) => ({
              node_id: item.id, x: item.x, y: item.y,
            })),
            layout_algorithm: "preset",
          }),
        });
        if (!response.ok) throw new Error(await response.text());
        renderGraph(await response.json());
        setGraphMessage("布局已保存；重新打开图时会恢复节点位置。", "");
      } catch (error) {
        setGraphMessage(`布局保存失败：${error.message}`, "error-text");
      } finally {
        button.disabled = false;
      }
    });
    graphEl.querySelector("[data-concept-graph-low-confidence]")?.addEventListener("click", (event) => {
      const button = event.currentTarget;
      const visible = button.getAttribute("aria-pressed") !== "true";
      button.setAttribute("aria-pressed", String(visible));
      button.textContent = visible ? "隐藏低置信边" : "显示低置信边";
      state.conceptGraphRenderer?.setLowConfidenceVisible(visible);
    });
  } else {
    state.conceptGraphSelectedNodeId = null;
    state.conceptGraphRenderer?.update(graph, { kind: graph.graph_kind || "concept_network" });
    inspector.innerHTML = '<div class="graph-inspector-empty"><span>◎</span><p>点击圆形节点查看解释、证据与关系。</p></div>';
  }
  window.requestAnimationFrame(() => state.conceptGraphRenderer?.fit());
}

function setGraphMessage(text, kind = "") {
  graphMessageEl.textContent = text;
  graphMessageEl.className = `form-message ${kind}`;
}

async function refreshGraph() {
  if (!state.graphId) return;
  const transientAnalysis = Boolean(
    state.analysisId
    && state.analysisResult?.graph?.id === state.graphId
    && graphSaveState(state.analysisResult.graph, state.analysisResult) === "transient"
  );
  const graphPath = transientAnalysis
    ? `/api/v1/analyses/${encodeURIComponent(state.analysisId)}/graph`
    : `/api/v1/graphs/${encodeURIComponent(state.graphId)}`;
  const graphResponse = await apiFetch(graphPath);
  if (!graphResponse.ok) throw new Error("graph request failed");
  renderGraph(await graphResponse.json());
  if (transientAnalysis) {
    const patchesResponse = await apiFetch(
      `/api/v1/analyses/${encodeURIComponent(state.analysisId)}/graph/patches`,
    );
    const patches = patchesResponse.ok ? await patchesResponse.json() : [];
    state.pendingPatches = new Map(
      patches.filter((patch) => patch.status === "proposed").map((patch) => [patch.id, patch]),
    );
    renderPatches();
    await loadGraphPicker(null);
    return;
  }
  const patchesResponse = await apiFetch(`/api/v1/graphs/${encodeURIComponent(state.graphId)}/patches`);
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
  const response = await apiFetch("/api/v1/graphs");
  if (!response.ok) return [];
  const graphs = await response.json();
  state.graphs = graphs;
  const previousCompareSelection = new Set(
    [...graphComparePickerEl.selectedOptions].map((option) => option.value),
  );
  const previousGallerySelection = new Set(
    [...graphGalleryPickerEl.selectedOptions].map((option) => option.value),
  );
  if (!graphs.length) {
    destroyGraphGalleryRenderers();
    graphPickerEl.classList.add("hidden");
    graphComparePickerEl.innerHTML = '<option disabled>完成分析后这里会出现概念图</option>';
    graphGalleryPickerEl.innerHTML = '<option disabled>完成分析后这里会出现概念图</option>';
    if (!graphGalleryEl.querySelector("[data-gallery-graph-id]")) {
      graphGalleryEl.innerHTML = '<p class="empty">还没有已保存的概念图。</p>';
    }
    deleteCurrentGraphButton?.classList.add("hidden");
    renderAnalysisGraphSaveControls();
    return graphs;
  }
  graphPickerEl.classList.remove("hidden");
  graphPickerEl.innerHTML = graphs.map((graph) =>
    `<option value="${escapeHtml(graph.id)}">${escapeHtml(graph.name)} · v${escapeHtml(graph.version)}</option>`,
  ).join("");
  if (selectedId && graphs.some((graph) => graph.id === selectedId)) graphPickerEl.value = selectedId;
  graphComparePickerEl.innerHTML = graphs.map((graph) =>
    `<option value="${escapeHtml(graph.id)}">${escapeHtml(graph.name)} · v${escapeHtml(graph.version)}</option>`,
  ).join("");
  [...graphComparePickerEl.options].forEach((option) => {
    option.selected = previousCompareSelection.has(option.value) || option.value === selectedId;
  });
  graphGalleryPickerEl.innerHTML = graphs.map((graph) =>
    `<option value="${escapeHtml(graph.id)}">${escapeHtml(graph.name)} · v${escapeHtml(graph.version)}</option>`,
  ).join("");
  [...graphGalleryPickerEl.options].forEach((option) => {
    option.selected = previousGallerySelection.has(option.value) || option.value === selectedId;
  });
  if (state.graph?.id) {
    deleteCurrentGraphButton?.classList.toggle("hidden", graphSaveState(state.graph, state.analysisResult) !== "saved");
  }
  renderAnalysisGraphSaveControls();
  return graphs;
}

graphPickerEl.addEventListener("change", async () => {
  state.graphId = graphPickerEl.value;
  try {
    await refreshGraph();
  } catch (error) {
    setGraphMessage(`概念图加载失败：${error.message}`, "error-text");
  }
});

function setGraphCompareMessage(text, kind = "") {
  graphCompareMessageEl.textContent = text;
  graphCompareMessageEl.className = `form-message ${kind}`;
}

function renderGraphCompare(result) {
  graphCompareResultEl.classList.remove("hidden");
  const connections = result.connections || [];
  graphCompareResultEl.innerHTML = `
    ${(result.warnings || []).length ? `<div class="warning-box"><strong>使用前请注意</strong><ul>${result.warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
    ${connections.length ? `<div class="cross-connection-list">${connections.map((connection) => `
      <article class="cross-connection-row">
        <div class="paper-title-line"><h3>${escapeHtml(connection.relation || "cross_domain_candidate")}</h3><span class="tag tag-missing">${escapeHtml(connection.confidence || "low")} · 未验证</span></div>
        <p class="cross-connection-path">${escapeHtml(connection.source_node_id)} → ${escapeHtml(connection.target_node_id)}</p>
        <p>${escapeHtml(connection.idea)}</p>
        <div class="validation-box"><strong>验证步骤</strong><ol>${(connection.validation_steps || []).map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol></div>
      </article>
    `).join("")}</div>` : '<p class="empty">没有生成跨图候选。可以扩大节点选择或调整比较焦点。</p>'}
  `;
}

graphCompareForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const graphIds = [...graphComparePickerEl.selectedOptions].map((option) => option.value);
  if (graphIds.length < 2) {
    setGraphCompareMessage("请至少选择两棵概念图。", "error-text");
    return;
  }
  const nodeIds = graphCompareNodesInput.value
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  graphCompareSubmit.disabled = true;
  graphCompareResultEl.classList.add("hidden");
  setGraphCompareMessage("正在比较图谱中的机制和问题…");
  try {
    const response = await apiFetch("/api/v1/graphs/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        graph_ids: graphIds,
        node_ids: nodeIds,
        focus: graphCompareFocusInput.value.trim() || "找出可以互相借鉴的机制，并给出最小验证实验",
      }),
    });
    if (!response.ok) throw new Error(await response.text());
    renderGraphCompare(await response.json());
    setGraphCompareMessage("跨图候选已生成；它不会自动改动原图。", "");
  } catch (error) {
    setGraphCompareMessage(`跨图比较失败：${error.message}`, "error-text");
  } finally {
    graphCompareSubmit.disabled = false;
  }
});

function setGraphGalleryMessage(text, kind = "") {
  graphGalleryMessageEl.textContent = text;
  graphGalleryMessageEl.className = `form-message ${kind}`;
}

function renderGraphGallery(graphs, warnings = []) {
  destroyGraphGalleryRenderers();
  if (!graphs.length) {
    graphGalleryEl.innerHTML = '<p class="empty">没有可显示的概念图。</p>';
    return;
  }
  graphGalleryEl.innerHTML = `
    ${warnings.length ? `<div class="warning-box"><strong>局部视图提示</strong><ul>${warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
    <div class="graph-gallery-grid">
      ${graphs.map((graph) => `
        <article class="graph-gallery-column" data-gallery-graph-id="${escapeHtml(graph.id)}">
          <div class="graph-gallery-heading">
            <div>
              <p class="section-label">${escapeHtml(graph.project_id ? "项目概念图" : "独立概念图")}</p>
              <h3>${escapeHtml(graph.name)}</h3>
            </div>
            <div class="graph-gallery-actions">
              <span class="tag">v${escapeHtml(graph.version)}</span>
              <button type="button" class="secondary graph-gallery-open" data-gallery-open="${escapeHtml(graph.id)}">打开编辑</button>
              <button type="button" class="secondary danger-button graph-gallery-delete" data-gallery-delete="${escapeHtml(graph.id)}" data-gallery-version="${escapeHtml(graph.version)}" data-gallery-name="${escapeHtml(graph.name)}">删除整图</button>
            </div>
          </div>
          <p class="graph-gallery-description">${escapeHtml(graph.description || "暂无描述")}</p>
          <div class="graph-gallery-real-canvas" data-gallery-canvas="${escapeHtml(graph.id)}" aria-label="${escapeHtml(graph.name)}关系图"></div>
        </article>
      `).join("")}
    </div>
  `;
  graphs.forEach((graph) => {
    const container = graphGalleryEl.querySelector(`[data-gallery-canvas="${CSS.escape(String(graph.id))}"]`);
    if (!container || !window.WishForgeGraph?.createGraphRenderer) return;
    const renderer = window.WishForgeGraph.createGraphRenderer(container, {
      graph,
      kind: graph.graph_kind || "concept_network",
      onNodeSelect: () => {},
    });
    state.graphGalleryRenderers.set(String(graph.id), renderer);
    window.requestAnimationFrame(() => renderer.fit());
  });
}

function destroyGraphGalleryRenderers() {
  state.graphGalleryRenderers.forEach((renderer) => renderer.destroy());
  state.graphGalleryRenderers.clear();
}

async function loadGalleryGraph(graphId, nodeIds) {
  if (nodeIds.length) {
    const query = encodeURIComponent(nodeIds.join(","));
    const response = await apiFetch(`/api/v1/graphs/${encodeURIComponent(graphId)}/subset?node_ids=${query}`);
    if (!response.ok) throw new Error(await response.text());
    return response.json().then((data) => data.graph);
  }
  const response = await apiFetch(`/api/v1/graphs/${encodeURIComponent(graphId)}`);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

graphGalleryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const graphIds = [...graphGalleryPickerEl.selectedOptions].map((option) => option.value);
  if (!graphIds.length) {
    setGraphGalleryMessage("请至少选择一张概念图。", "error-text");
    return;
  }
  const nodeIds = graphGalleryNodesInput.value.split(",").map((value) => value.trim()).filter(Boolean);
  graphGallerySubmit.disabled = true;
  setGraphGalleryMessage("正在读取并排视图…");
  try {
    const settled = await Promise.allSettled(graphIds.map((graphId) => loadGalleryGraph(graphId, nodeIds)));
    const graphs = [];
    const warnings = nodeIds.length ? ["这是按节点 ID 生成的临时裁剪视图；源图没有被修改。"] : [];
    settled.forEach((item, index) => {
      if (item.status === "fulfilled") {
        graphs.push(item.value);
      } else {
        warnings.push(`图 ${graphIds[index].slice(0, 8)} 加载失败，已跳过：${item.reason?.message || item.reason || "未知错误"}`);
      }
    });
    if (!graphs.length) throw new Error(warnings[warnings.length - 1] || "没有可显示的概念图");
    renderGraphGallery(graphs, warnings);
    setGraphGalleryMessage(`已显示 ${graphs.length} 张概念图。`, "");
  } catch (error) {
    setGraphGalleryMessage(`多图视图加载失败：${error.message}`, "error-text");
  } finally {
    graphGallerySubmit.disabled = false;
  }
});

graphGalleryEl.addEventListener("click", async (event) => {
  const deleteButton = event.target.closest("[data-gallery-delete]");
  if (deleteButton) {
    openGraphDeleteDialog({
      id: deleteButton.dataset.galleryDelete,
      version: deleteButton.dataset.galleryVersion,
      name: deleteButton.dataset.galleryName || "未命名概念图",
    }, "gallery");
    return;
  }
  const openButton = event.target.closest("[data-gallery-open]");
  if (!openButton) return;
  const graphId = openButton.dataset.galleryOpen;
  graphPickerEl.value = graphId;
  try {
    await refreshGraph();
    navigateTo("concept-graphs", ".graph-card");
  } catch (error) {
    setGraphGalleryMessage(`切换概念图失败：${error.message}`, "error-text");
  }
});

saveAnalysisGraphButton?.addEventListener("click", openGraphSaveDialog);
saveGraphDialogConfirmButton?.addEventListener("click", async () => {
  state.graphSaveDialogAction = "save";
  if (saveGraphDialogConfirmButton) saveGraphDialogConfirmButton.disabled = true;
  try {
    await saveAnalysisGraph();
    closeDialog(graphSaveDialog);
  } catch (error) {
    state.graphSaveDialogAction = null;
    if (saveGraphDialogConfirmButton) saveGraphDialogConfirmButton.disabled = false;
    setAnalysisMessage(`概念图保存失败：${error.message}`, "error-text");
    setGraphMessage(`概念图保存失败：${error.message}`, "error-text");
  }
});
saveGraphDialogLaterButton?.addEventListener("click", deferGraphSave);
graphSaveDialog?.addEventListener("cancel", (event) => {
  event.preventDefault();
  deferGraphSave();
});
graphSaveDialog?.addEventListener("close", () => {
  if (!state.graphSaveDialogAction) {
    deferGraphSave();
    return;
  }
  state.graphSaveDialogAction = null;
  if (saveGraphDialogConfirmButton) saveGraphDialogConfirmButton.disabled = false;
});
graphSaveDialog?.addEventListener("click", (event) => {
  if (event.target.closest("[data-dialog-close='graph-save']")) deferGraphSave();
});
graphSaveDialog?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.defaultPrevented) return;
  // The action-sheet buttons intentionally use `type=button` so closing the
  // native dialog never silently chooses an action.  Make the recommended
  // save action the keyboard default explicitly.
  if (event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLInputElement) return;
  event.preventDefault();
  saveGraphDialogConfirmButton?.click();
});

deleteCurrentGraphButton?.addEventListener("click", () => {
  if (state.graph) openGraphDeleteDialog(state.graph, "current");
});
graphDeleteDialogConfirmButton?.addEventListener("click", deleteGraphById);
graphDeleteDialogCancelButton?.addEventListener("click", closeGraphDeleteDialog);
graphDeleteDialog?.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeGraphDeleteDialog();
});
graphDeleteDialog?.addEventListener("click", (event) => {
  if (event.target.closest("[data-dialog-close='graph-delete']")) closeGraphDeleteDialog();
});

async function applyUserPatch(operations, reason) {
  if (!state.graphId) return;
  const transient = isTransientAnalysisGraph();
  const endpoint = transient
    ? `/api/v1/analyses/${encodeURIComponent(state.analysisId)}/graph/patches`
    : `/api/v1/graphs/${encodeURIComponent(state.graphId)}/patches`;
  const response = await apiFetch(endpoint, {
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
        ${patch.source_request ? `<p class="settings-note">原始请求：${escapeHtml(patch.source_request)}</p>` : ""}
        <ul>${(patch.operations || []).map((operation) => `<li>${escapeHtml(describeOperation(operation))}</li>`).join("")}</ul>
        ${(patch.warnings || []).length ? `<div class="warning-box"><ul>${patch.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></div>` : ""}
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
  const transient = isTransientAnalysisGraph();
  const prefix = transient
    ? `/api/v1/analyses/${encodeURIComponent(state.analysisId)}/graph`
    : `/api/v1/graphs/${encodeURIComponent(state.graphId)}`;
  const response = await apiFetch(
    `${prefix}/patches/${encodeURIComponent(patchId)}/${action}`,
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
  const endpoint = isTransientAnalysisGraph()
    ? `/api/v1/analyses/${encodeURIComponent(state.analysisId)}/graph/patches`
    : `/api/v1/graphs/${encodeURIComponent(state.graphId)}/patches`;
  const response = await apiFetch(endpoint, {
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

graphAgentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.graphId || !state.graph) return;
  const request = graphAgentRequestInput.value.trim();
  if (!request) {
    graphAgentMessageEl.textContent = "请先写下想怎样修改概念图。";
    graphAgentMessageEl.className = "form-message error-text";
    return;
  }
  graphAgentSubmit.disabled = true;
  graphAgentMessageEl.textContent = "正在把自然语言请求转换成受限提案…";
  graphAgentMessageEl.className = "form-message";
  try {
    const endpoint = isTransientAnalysisGraph()
      ? `/api/v1/analyses/${encodeURIComponent(state.analysisId)}/graph/agent-patch`
      : `/api/v1/graphs/${encodeURIComponent(state.graphId)}/agent-patch`;
    const response = await apiFetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request, base_version: state.graph.version, max_operations: 4 }),
    });
    if (!response.ok) throw new Error(await response.text());
    const patch = await response.json();
    state.pendingPatches.set(patch.id, patch);
    renderPatches();
    graphAgentMessageEl.textContent = "提案已生成，请在下方预览后批准或拒绝。";
    graphAgentMessageEl.className = "form-message";
  } catch (error) {
    graphAgentMessageEl.textContent = `提案生成失败：${error.message}`;
    graphAgentMessageEl.className = "form-message error-text";
  } finally {
    graphAgentSubmit.disabled = false;
  }
});

graphMetaForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.graphId || !state.graph) return;
  const name = graphNameInput.value.trim();
  const rootId = graphRootInput.value;
  if (!name && !rootId) return;
  const transientAnalysis = isTransientAnalysisGraph();
  const endpoint = transientAnalysis
    ? `/api/v1/analyses/${encodeURIComponent(state.analysisId)}/graph`
    : `/api/v1/graphs/${encodeURIComponent(state.graphId)}`;
  const response = await apiFetch(endpoint, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name || undefined, root_id: rootId || undefined, base_version: state.graph.version }),
  });
  if (!response.ok) {
    if (response.status === 409) await refreshGraph();
    window.alert(`概念图名称保存失败：${await response.text()}`);
    return;
  }
  const updated = await response.json();
  if (transientAnalysis && state.analysisResult) {
    state.analysisResult.graph = updated;
    state.analysisResult.graph_save_state = "transient";
    state.analysisResult.saved_graph_id = null;
  }
  renderGraph(updated);
  if (!transientAnalysis) await loadGraphPicker(state.graphId);
  setGraphMessage(transientAnalysis ? "临时概念图设置已保存；保存图后可继续编辑节点。" : "概念图名称已保存。", "");
});

graphEl.addEventListener("click", async (event) => {
  const explainButton = event.target.closest("[data-node-explain]");
  if (explainButton && state.graph) {
    const nodeId = explainButton.dataset.nodeExplain;
    try {
      const prefix = isTransientAnalysisGraph()
        ? `/api/v1/analyses/${encodeURIComponent(state.analysisId)}/graph`
        : `/api/v1/graphs/${encodeURIComponent(state.graphId)}`;
      const response = await apiFetch(
        `${prefix}/nodes/${encodeURIComponent(nodeId)}/explanation-patch`,
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

const overviewStageLabels = {
  direction_planning: "规划一级研究方向",
  direction_research: "并行调研各研究方向",
  direction_expansion: "判断方向是否需要继续细分",
  paper_reading: "阅读论文摘要与可用章节",
  direction_validation: "核对论文归属与证据",
  graph_synthesis: "合成研究方向图",
  statistics_layout: "计算活跃度、新旧程度与布局",
  completed: "研究方向图已生成",
};

function setOverviewActionMessage(text, kind = "") {
  if (!overviewActionMessageEl) return;
  overviewActionMessageEl.textContent = text;
  overviewActionMessageEl.className = `form-message ${kind}`;
}

function overviewHistoryLabel(job) {
  const graph = overviewResult(job)?.graph;
  const title = graph?.name || `分析 ${String(job?.analysis_id || "").slice(0, 8) || "未知"}`;
  const status = {
    queued: "排队中",
    running: "生成中",
    partial: "部分完成",
    succeeded: "已完成",
    failed: "失败",
    interrupted: "已中断",
  }[job?.status] || job?.status || "未知状态";
  const timestamp = Date.parse(job?.updated_at || job?.created_at || "");
  const updated = Number.isFinite(timestamp)
    ? new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    }).format(new Date(timestamp))
    : "时间未知";
  return `${title} · ${status} · ${updated}`;
}

function renderOverviewHistory() {
  if (!overviewHistorySelectEl) return;
  const jobs = state.overviewJobs || [];
  if (!jobs.length) {
    overviewHistorySelectEl.innerHTML = '<option value="">暂无历史任务</option>';
    overviewHistorySelectEl.disabled = true;
    if (overviewHistoryStatusEl) overviewHistoryStatusEl.textContent = "暂无可恢复的研究方向图任务。";
    return;
  }
  overviewHistorySelectEl.innerHTML = `
    <option value="">选择一个历史任务</option>
    ${jobs.map((job) => `
    <option value="${escapeHtml(job.id)}">${escapeHtml(overviewHistoryLabel(job))}</option>
    `).join("")}
  `;
  overviewHistorySelectEl.disabled = false;
  overviewHistorySelectEl.value = jobs.some((job) => String(job.id) === String(state.overviewId))
    ? String(state.overviewId)
    : "";
  if (overviewHistoryStatusEl) {
    overviewHistoryStatusEl.textContent = `${jobs.length} 个历史任务；选择后可恢复图、进度和保存状态。`;
  }
}

function stopOverviewPolling() {
  if (state.overviewPollTimer) window.clearTimeout(state.overviewPollTimer);
  state.overviewPollTimer = null;
}

async function openOverviewJob(jobOrId, { promptSave = false } = {}) {
  const requestedId = String(typeof jobOrId === "object" ? jobOrId?.id : jobOrId || "");
  if (!requestedId) return null;
  stopOverviewPolling();
  const response = typeof jobOrId === "object"
    ? null
    : await apiFetch(`/api/v1/overviews/${encodeURIComponent(requestedId)}`);
  if (response && !response.ok) throw new Error(await response.text());
  const job = response ? await response.json() : jobOrId;
  if (!job?.id || String(job.id) !== requestedId) throw new Error("Overview 历史任务响应无效");
  state.overviewId = requestedId;
  state.overviewJob = job;
  state.overviewAnalysisId = String(job.analysis_id || "") || null;
  state.overviewSelectedNodeId = null;
  state.overviewSavePromptedForId = promptSave ? null : requestedId;
  renderOverviewHistory();
  renderOverviewStatus(job);
  const result = overviewResult(job);
  if (result?.graph) {
    state.overviewRenderer?.destroy();
    state.overviewRenderer = null;
    state.overviewLowConfidenceVisible = true;
    if (overviewToggleEdgesButton) {
      overviewToggleEdgesButton.setAttribute("aria-pressed", "true");
      overviewToggleEdgesButton.textContent = "隐藏低置信边";
    }
    renderOverviewGraph(result);
  } else {
    state.overviewGraph = null;
    state.overviewRenderer?.destroy();
    state.overviewRenderer = null;
    resetOverviewView({ preserveJobStatus: true });
    renderOverviewStatus(job);
  }
  if (["queued", "running"].includes(job.status)) {
    await pollOverview(requestedId);
  } else if (promptSave) {
    maybePromptOverviewSave(job);
  }
  return job;
}

async function loadOverviewHistory({ autoOpen = false } = {}) {
  if (state.overviewHistoryLoading) return state.overviewJobs;
  state.overviewHistoryLoading = true;
  overviewHistoryRefreshButton && (overviewHistoryRefreshButton.disabled = true);
  if (overviewHistoryStatusEl) overviewHistoryStatusEl.textContent = "正在读取历史任务…";
  try {
    const response = await apiFetch("/api/v1/overviews");
    if (!response.ok) throw new Error(await response.text());
    const payload = await response.json();
    const jobs = Array.isArray(payload) ? payload : Array.isArray(payload?.items) ? payload.items : [];
    state.overviewJobs = jobs;
    state.overviewHistoryLoaded = true;
    renderOverviewHistory();
    if (autoOpen && !state.overviewId && jobs.length) {
      await openOverviewJob(jobs[0], { promptSave: false });
    }
    return jobs;
  } catch (error) {
    state.overviewHistoryLoaded = false;
    if (overviewHistoryStatusEl) overviewHistoryStatusEl.textContent = `历史任务读取失败：${error.message}`;
    throw error;
  } finally {
    state.overviewHistoryLoading = false;
    if (overviewHistoryRefreshButton) overviewHistoryRefreshButton.disabled = false;
  }
}

function resetOverviewView({ preserveJobStatus = false } = {}) {
  if (!preserveJobStatus) {
    state.overviewId = null;
    state.overviewJob = null;
  }
  state.overviewGraph = null;
  state.overviewSelectedNodeId = null;
  state.overviewLowConfidenceVisible = true;
  state.overviewRenderer?.destroy();
  state.overviewRenderer = null;
  if (overviewStateTagEl) {
    overviewStateTagEl.textContent = "等待生成";
    overviewStateTagEl.className = "tag tag-beta";
  }
  if (overviewStageTitleEl) overviewStageTitleEl.textContent = "先在工作台完成一次文献或研究分析";
  if (overviewStatusMessageEl) overviewStatusMessageEl.textContent = "分析至少包含一篇有效论文后，点击 Overview 按钮开始生成。";
  if (overviewProgressLabelEl) overviewProgressLabelEl.textContent = "0%";
  if (overviewCountsEl) overviewCountsEl.textContent = "0 个方向 · 0 篇论文";
  if (overviewProgressBarEl) overviewProgressBarEl.style.width = "0%";
  overviewRetryButton?.classList.add("hidden");
  overviewSaveLaterButton?.classList.add("hidden");
  overviewSaveButton?.classList.add("hidden");
  if (overviewFitButton) overviewFitButton.disabled = true;
  if (overviewToggleEdgesButton) overviewToggleEdgesButton.disabled = true;
  if (overviewToggleEdgesButton) {
    overviewToggleEdgesButton.setAttribute("aria-pressed", "true");
    overviewToggleEdgesButton.textContent = "隐藏低置信边";
  }
  overviewLegendEl?.classList.add("hidden");
  overviewWarningsEl?.classList.add("hidden");
  if (overviewWarningsEl) overviewWarningsEl.innerHTML = "";
  if (overviewCanvasEl && !state.overviewRenderer) {
    overviewCanvasEl.innerHTML = '<div class="graph-canvas-placeholder"><span>⌁</span><p>生成后可缩放、平移和拖拽节点；点击节点可查看证据详情。</p></div>';
  }
  if (overviewInspectorEl) overviewInspectorEl.innerHTML = window.WishForgeGraph?.inspectorMarkup?.(null) || '<p class="empty">点击节点查看详情。</p>';
  setOverviewActionMessage("", "");
}

function overviewResult(job = state.overviewJob) {
  if (!job || typeof job !== "object") return null;
  if (job.result?.graph) return job.result;
  if (job.graph?.nodes) return { graph: job.graph, warnings: job.warnings || [], legend: job.legend || {} };
  return null;
}

function renderOverviewStatus(job) {
  const result = overviewResult(job);
  const progress = Math.min(100, Math.max(0, Number(job?.progress) || 0));
  const status = job?.status || "queued";
  const stage = job?.stage || "direction_planning";
  const statusLabels = {
    queued: "排队中",
    running: "生成中",
    partial: "部分完成",
    succeeded: "已完成",
    failed: "失败",
    interrupted: "已中断",
  };
  if (overviewStateTagEl) {
    overviewStateTagEl.textContent = statusLabels[status] || status;
    overviewStateTagEl.className = `tag ${["failed", "interrupted"].includes(status) ? "tag-missing" : ["succeeded", "partial"].includes(status) ? "tag-configured" : "tag-beta"}`;
  }
  if (overviewStageTitleEl) overviewStageTitleEl.textContent = overviewStageLabels[stage] || "正在生成研究方向图";
  if (overviewStatusMessageEl) {
    overviewStatusMessageEl.textContent = job?.error
      ? `生成未完成：${job.error}`
      : job?.message || "多 Agent 正在整理研究方向和论文证据。";
  }
  if (overviewProgressLabelEl) overviewProgressLabelEl.textContent = `${progress}%`;
  if (overviewProgressBarEl) overviewProgressBarEl.style.width = `${progress}%`;
  if (overviewCountsEl) {
    overviewCountsEl.textContent = `${Number(result?.direction_count) || 0} 个方向 · ${Number(result?.paper_count) || 0} 篇论文`;
  }
  const canRegenerate = ["failed", "interrupted", "partial"].includes(status);
  overviewRetryButton?.classList.toggle("hidden", !canRegenerate);
  if (overviewRetryButton) overviewRetryButton.textContent = status === "partial" ? "重新生成全部方向" : "重新生成";
  const hasGraph = Boolean(result?.graph?.nodes?.length);
  const saved = job?.save_state === "saved" || Boolean(job?.saved_graph_id);
  overviewSaveButton?.classList.toggle("hidden", !hasGraph || saved);
  overviewSaveLaterButton?.classList.toggle("hidden", !hasGraph || saved);
  if (saved && overviewSaveButton) overviewSaveButton.classList.add("hidden");
}

function renderOverviewWarnings(warnings = []) {
  if (!overviewWarningsEl) return;
  const unique = [...new Set(warnings.filter(Boolean))];
  overviewWarningsEl.classList.toggle("hidden", !unique.length);
  const failedAudits = (overviewResult()?.direction_audits || []).filter((audit) => audit.error);
  overviewWarningsEl.classList.toggle("hidden", !unique.length && !failedAudits.length);
  overviewWarningsEl.innerHTML = (!unique.length && !failedAudits.length) ? "" : `
    ${unique.length ? `<div class="warning-box"><strong>范围与证据提示</strong><ul>${unique.map((warning) => `<li>${escapeHtml(friendlyAnalysisWarning(warning))}</li>`).join("")}</ul></div>` : ""}
    ${failedAudits.length ? `<div class="warning-box"><strong>失败方向</strong><ul>${failedAudits.map((audit) => `
      <li>
        <span>${escapeHtml(audit.label)}：${escapeHtml(audit.error)}</span>
        <button type="button" class="secondary overview-retry-direction" data-overview-retry-direction="${escapeHtml(audit.direction_key)}">只重试这个方向</button>
      </li>
    `).join("")}</ul></div>` : ""}
  `;
  overviewWarningsEl.querySelectorAll("[data-overview-retry-direction]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!state.overviewId || !state.overviewGraph) return;
      button.disabled = true;
      try {
        const directionKey = button.dataset.overviewRetryDirection;
        const response = await apiFetch(
          `/api/v1/overviews/${encodeURIComponent(state.overviewId)}/directions/${encodeURIComponent(directionKey)}/retry`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ expected_version: state.overviewGraph.version }),
          },
        );
        if (!response.ok) throw new Error(await response.text());
        state.overviewJob = await response.json();
        renderOverviewStatus(state.overviewJob);
        renderOverviewGraph(overviewResult());
        setOverviewActionMessage("该失败方向已单独重试，其他成功方向保持不变。", "");
      } catch (error) {
        setOverviewActionMessage(`方向重试失败：${error.message}`, "error-text");
      } finally {
        button.disabled = false;
      }
    });
  });
}

function renderOverviewInspector(node, relatedEdges = []) {
  if (!overviewInspectorEl || !window.WishForgeGraph?.inspectorMarkup) return;
  state.overviewSelectedNodeId = node?.id || null;
  const result = overviewResult();
  const evidenceById = new Map([
    ...(state.analysisResult?.evidence || []),
    ...(result?.evidence || []),
  ].map((item) => [item.id, item]));
  const enriched = node ? {
    ...node,
    evidence_cards: (node.evidence_ids || []).map((id) => evidenceById.get(id)).filter(Boolean),
  } : node;
  overviewInspectorEl.innerHTML = window.WishForgeGraph.inspectorMarkup(enriched, relatedEdges, {
    allowExpand: (node?.role || node?.node_type) === "direction"
      && ["succeeded", "partial"].includes(state.overviewJob?.status),
  });
  const expandButton = overviewInspectorEl.querySelector("[data-overview-expand-node]");
  if (expandButton && node?.id) {
    expandButton.addEventListener("click", () => expandOverviewDirection(node.id));
  }
  const requestedOverviewId = state.overviewId;
  const requestedNodeId = node?.id || null;
  if (node?.id && state.overviewId) {
    apiFetch(`/api/v1/overviews/${encodeURIComponent(state.overviewId)}/nodes/${encodeURIComponent(node.id)}`)
      .then(async (response) => (response.ok ? response.json() : null))
      .then((detail) => {
        if (!detail
          || state.overviewId !== requestedOverviewId
          || state.overviewSelectedNodeId !== requestedNodeId) return;
        const detailedNode = {
          ...detail.node,
          evidence_cards: detail.evidence || [],
          source_papers: detail.papers || [],
          inspector_warnings: detail.warnings || [],
        };
        overviewInspectorEl.innerHTML = window.WishForgeGraph.inspectorMarkup(
          detailedNode,
          detail.related_edges || relatedEdges,
          {
            allowExpand: (detailedNode.role || detailedNode.node_type) === "direction"
              && ["succeeded", "partial"].includes(state.overviewJob?.status),
          },
        );
        overviewInspectorEl.querySelector("[data-overview-expand-node]")?.addEventListener(
          "click",
          () => expandOverviewDirection(detailedNode.id),
        );
      })
      .catch(() => {});
  }
}

function renderOverviewGraph(result) {
  const graph = result?.graph;
  if (!graph?.nodes?.length || !window.WishForgeGraph?.createGraphRenderer) return;
  state.overviewGraph = graph;
  if (overviewGraphTitleEl) overviewGraphTitleEl.textContent = graph.name || "研究方向与论文";
  if (!state.overviewRenderer) {
    overviewCanvasEl.innerHTML = "";
    state.overviewRenderer = window.WishForgeGraph.createGraphRenderer(overviewCanvasEl, {
      graph,
      kind: "research_direction",
      onNodeSelect: renderOverviewInspector,
    });
  } else {
    state.overviewRenderer.update(graph, { kind: "research_direction" });
  }
  state.overviewRenderer.setLowConfidenceVisible(state.overviewLowConfidenceVisible);
  if (typeof window !== "undefined") {
    window.WishForgeSmoke = Object.freeze({
      overviewNodePositions: () => state.overviewRenderer?.visibleNodeScreenPositions?.() || [],
    });
  }
  if (state.overviewSelectedNodeId) {
    const selectedNode = graph.nodes.find((node) => node.id === state.overviewSelectedNodeId);
    if (selectedNode) state.overviewRenderer.selectNode(selectedNode.id);
    else renderOverviewInspector(null);
  }
  if (overviewFitButton) overviewFitButton.disabled = false;
  if (overviewToggleEdgesButton) overviewToggleEdgesButton.disabled = false;
  overviewLegendEl?.classList.remove("hidden");
  const legend = result.legend || {};
  if (overviewLegendNoteEl) {
    overviewLegendNoteEl.textContent = [legend.heat_note, legend.recency_note]
      .filter(Boolean)
      .join(" ") || "热度只表示当前检索范围内的相对活跃度，不代表论文质量、正确性、创新性或全局影响力。";
  }
  renderOverviewWarnings([...(graph.warnings || []), ...(result.warnings || [])]);
  window.requestAnimationFrame(() => state.overviewRenderer?.fit());
}

function maybePromptOverviewSave(job) {
  if (!["succeeded", "partial"].includes(job?.status) || !overviewResult(job)?.graph) return;
  if (job.save_state === "saved" || state.overviewSavePromptedForId === String(job.id)) return;
  state.overviewSavePromptedForId = String(job.id);
  window.requestAnimationFrame(() => showDialog(overviewSaveDialog));
}

async function pollOverview(id) {
  if (!id || String(id) !== String(state.overviewId)) return;
  if (state.overviewPollTimer) window.clearTimeout(state.overviewPollTimer);
  const response = await apiFetch(`/api/v1/overviews/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error(await response.text());
  const job = await response.json();
  if (String(id) !== String(state.overviewId)) return;
  state.overviewJob = job;
  const historyIndex = state.overviewJobs.findIndex((item) => String(item.id) === String(job.id));
  if (historyIndex >= 0) state.overviewJobs.splice(historyIndex, 1, job);
  else state.overviewJobs.unshift(job);
  renderOverviewHistory();
  renderOverviewStatus(job);
  const result = overviewResult(job);
  if (result?.graph) renderOverviewGraph(result);
  if (["succeeded", "partial", "failed", "interrupted"].includes(job.status)) {
    state.overviewPollTimer = null;
    maybePromptOverviewSave(job);
    return;
  }
  state.overviewPollTimer = window.setTimeout(() => {
    pollOverview(id).catch((error) => {
      setOverviewActionMessage(`无法读取 Overview 进度：${error.message}`, "error-text");
      overviewRetryButton?.classList.remove("hidden");
    });
  }, 900);
}

async function createOverview({ force = false } = {}) {
  const usesRestoredHistory = Boolean(state.overviewJob && state.overviewAnalysisId);
  const analysisId = usesRestoredHistory ? state.overviewAnalysisId : state.analysisId;
  if (!analysisId) {
    navigateTo("workspace");
    setAnalysisMessage("请先完成一次文献解释或研究线索分析。", "error-text");
    return;
  }
  const canCreate = usesRestoredHistory || (
    Boolean(state.analysisResult)
    &&
    ["literature", "research"].includes(state.analysisResult.level)
    && (state.analysisResult.papers || []).length > 0
  );
  if (!canCreate) {
    setAnalysisMessage("研究方向图需要文献解释或研究线索结果，并且至少包含一篇论文。", "error-text");
    return;
  }
  if (state.overviewId && !force) {
    navigateTo("research-overview");
    window.requestAnimationFrame(() => state.overviewRenderer?.fit());
    return;
  }
  createOverviewButton && (createOverviewButton.disabled = true);
  overviewRetryButton && (overviewRetryButton.disabled = true);
  setOverviewActionMessage("正在创建 Overview 任务…", "");
  try {
    const response = await apiFetch(`/api/v1/analyses/${encodeURIComponent(analysisId)}/overview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force_regenerate: force }),
    });
    if (!response.ok) throw new Error(await response.text());
    const job = await response.json();
    state.overviewId = String(job.id);
    state.overviewAnalysisId = String(job.analysis_id || analysisId);
    state.overviewJob = job;
    const historyIndex = state.overviewJobs.findIndex((item) => String(item.id) === String(job.id));
    if (historyIndex >= 0) state.overviewJobs.splice(historyIndex, 1, job);
    else state.overviewJobs.unshift(job);
    state.overviewHistoryLoaded = true;
    renderOverviewHistory();
    state.overviewSavePromptedForId = null;
    if (createOverviewButton) createOverviewButton.textContent = "打开研究方向图";
    navigateTo("research-overview");
    renderOverviewStatus(job);
    const result = overviewResult(job);
    if (result?.graph) renderOverviewGraph(result);
    await pollOverview(state.overviewId);
  } catch (error) {
    setOverviewActionMessage(`研究方向图创建失败：${error.message}`, "error-text");
    setAnalysisMessage(`研究方向图创建失败：${error.message}`, "error-text");
    overviewRetryButton?.classList.remove("hidden");
  } finally {
    if (createOverviewButton) createOverviewButton.disabled = false;
    if (overviewRetryButton) overviewRetryButton.disabled = false;
  }
}

async function expandOverviewDirection(nodeId) {
  if (!state.overviewId || !state.overviewJob || !nodeId) return;
  const button = overviewInspectorEl?.querySelector("[data-overview-expand-node]");
  if (button) button.disabled = true;
  setOverviewActionMessage("正在调研并展开所选方向…", "");
  try {
    const response = await apiFetch(`/api/v1/overviews/${encodeURIComponent(state.overviewId)}/expand`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        node_id: nodeId,
        expected_version: overviewResult()?.graph?.version,
      }),
    });
    if (!response.ok) throw new Error(await response.text());
    const job = await response.json();
    state.overviewJob = job;
    renderOverviewStatus(job);
    const result = overviewResult(job);
    if (result?.graph) renderOverviewGraph(result);
    setOverviewActionMessage("方向已更新；请检查新增的子方向与论文。", "");
  } catch (error) {
    setOverviewActionMessage(`方向展开失败：${error.message}`, "error-text");
  } finally {
    if (button) button.disabled = false;
  }
}

async function saveOverview() {
  if (!state.overviewId || !state.overviewJob || !overviewResult()?.graph) return null;
  overviewSaveButton && (overviewSaveButton.disabled = true);
  overviewDialogConfirmButton && (overviewDialogConfirmButton.disabled = true);
  setOverviewActionMessage("正在保存研究方向图…", "");
  try {
    const graph = overviewResult().graph;
    const response = await apiFetch(`/api/v1/overviews/${encodeURIComponent(state.overviewId)}/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: graph.version, name: graph.name || undefined }),
    });
    if (!response.ok) throw new Error(await response.text());
    const payload = await response.json();
    state.overviewJob.save_state = payload.save_state || "saved";
    state.overviewJob.saved_graph_id = payload.saved_graph_id || payload.graph?.id || state.overviewJob.saved_graph_id;
    if (payload.graph) {
      state.overviewJob.result = { ...overviewResult(), graph: payload.graph };
      renderOverviewGraph(state.overviewJob.result);
    }
    const historyIndex = state.overviewJobs.findIndex((item) => String(item.id) === String(state.overviewJob.id));
    if (historyIndex >= 0) state.overviewJobs.splice(historyIndex, 1, state.overviewJob);
    renderOverviewHistory();
    renderOverviewStatus(state.overviewJob);
    await loadGraphPicker(state.overviewJob.saved_graph_id || null);
    closeDialog(overviewSaveDialog);
    setOverviewActionMessage("研究方向图已保存到统一图库。", "");
    return payload;
  } finally {
    if (overviewSaveButton) overviewSaveButton.disabled = false;
    if (overviewDialogConfirmButton) overviewDialogConfirmButton.disabled = false;
  }
}

createOverviewButton?.addEventListener("click", () => createOverview());
overviewRetryButton?.addEventListener("click", () => createOverview({ force: true }));
overviewFitButton?.addEventListener("click", () => state.overviewRenderer?.fit());
overviewToggleEdgesButton?.addEventListener("click", () => {
  state.overviewLowConfidenceVisible = !state.overviewLowConfidenceVisible;
  overviewToggleEdgesButton.setAttribute("aria-pressed", String(state.overviewLowConfidenceVisible));
  overviewToggleEdgesButton.textContent = state.overviewLowConfidenceVisible ? "隐藏低置信边" : "显示低置信边";
  state.overviewRenderer?.setLowConfidenceVisible(state.overviewLowConfidenceVisible);
});
overviewHistorySelectEl?.addEventListener("change", () => {
  const overviewId = overviewHistorySelectEl.value;
  if (!overviewId || String(overviewId) === String(state.overviewId)) return;
  overviewHistorySelectEl.disabled = true;
  setOverviewActionMessage("正在恢复历史研究方向图…", "");
  openOverviewJob(overviewId, { promptSave: false })
    .then(() => setOverviewActionMessage("历史研究方向图已恢复。", ""))
    .catch((error) => setOverviewActionMessage(`历史任务恢复失败：${error.message}`, "error-text"))
    .finally(() => { overviewHistorySelectEl.disabled = false; });
});
overviewHistoryRefreshButton?.addEventListener("click", () => {
  loadOverviewHistory({ autoOpen: !state.overviewId })
    .catch((error) => setOverviewActionMessage(`历史任务刷新失败：${error.message}`, "error-text"));
});
overviewSaveButton?.addEventListener("click", () => showDialog(overviewSaveDialog));
overviewSaveLaterButton?.addEventListener("click", () => {
  closeDialog(overviewSaveDialog);
  setOverviewActionMessage("研究方向图暂不保存；Overview 任务仍可继续查看。", "");
});
overviewDialogConfirmButton?.addEventListener("click", () => saveOverview().catch((error) => {
  setOverviewActionMessage(`保存失败：${error.message}`, "error-text");
}));
overviewDialogLaterButton?.addEventListener("click", () => {
  closeDialog(overviewSaveDialog);
  setOverviewActionMessage("研究方向图暂不保存；之后仍可点击保存。", "");
});
document.querySelector('[data-dialog-close="overview-save"]')?.addEventListener("click", () => {
  closeDialog(overviewSaveDialog);
  setOverviewActionMessage("研究方向图暂不保存；之后仍可点击保存。", "");
});
overviewSaveDialog?.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeDialog(overviewSaveDialog);
  setOverviewActionMessage("研究方向图暂不保存；之后仍可点击保存。", "");
});
overviewSaveDialog?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.defaultPrevented) return;
  if (event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLInputElement) return;
  event.preventDefault();
  overviewDialogConfirmButton?.click();
});

async function pollAnalysis(id) {
  const response = await apiFetch(`/api/v1/analyses/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error("analysis request failed");
  const job = await response.json();
  const createdAt = Date.parse(job.created_at || "");
  const elapsedSeconds = Number.isFinite(createdAt)
    ? Math.max(0, (Date.now() - createdAt) / 1000).toFixed(1)
    : null;
  setAnalysisMessage(`${job.message} · ${job.progress}%${elapsedSeconds ? ` · 已用 ${elapsedSeconds}s` : ""}`);
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
  state.analysisResult = result;
  state.analysisGraphSaveState =
    result.graph_save_state
    || result.graph_save_status
    || result.graph?.save_state
    || result.graph?.save_status
    || null;
  analysisProviderEl.textContent = result.provider;
  renderExplanation(result);
  renderPapers(result);
  renderEvidenceLedger(result);
  renderInnovations(result);
  renderResearchBrief(result);
  renderGraph(result.graph);
  loadGraphPicker(result.graph.id).catch(() => {});
  state.pendingPatches.clear();
  renderPatches();
  renderAnalysisGraphSaveControls();
  const canCreateOverview = ["literature", "research"].includes(result.level)
    && (result.papers || []).some((paper) => paper?.id && paper?.title);
  analysisOverviewActionsEl?.classList.toggle("hidden", !canCreateOverview);
  if (createOverviewButton) {
    createOverviewButton.disabled = false;
    createOverviewButton.textContent = state.overviewId
      ? "打开研究方向图"
      : "Overview / 研究方向图";
  }
  const shouldPrompt = ["literature", "research"].includes(result.level)
    && isTransientAnalysisGraph(result)
    && state.graphSavePromptedForAnalysis !== state.analysisId;
  if (shouldPrompt) {
    state.graphSavePromptedForAnalysis = state.analysisId;
    window.requestAnimationFrame(() => openGraphSaveDialog());
  }
}

analysisForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  resetAnalysisView();
  analysisSubmit.disabled = true;
  setAnalysisMessage("正在创建分析任务…");
  try {
    const response = await apiFetch("/api/v1/analyses", {
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
    const response = await apiFetch("/api/v1/projects", {
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
document.querySelector("#refresh-settings").addEventListener("click", () => {
  loadApiKeys();
  loadModelSettings();
});
window.addEventListener("hashchange", () => renderRoute());
routeLinks.forEach((link) => {
  link.addEventListener("click", () => {
    window.setTimeout(() => window.scrollTo({ top: 0, behavior: "smooth" }), 0);
  });
});

renderApiBaseConfiguration();
renderDesktopRuntimeStatus();
renderRoute();
if (currentRoute() !== "research-overview") {
  loadOverviewHistory({ autoOpen: false }).catch(() => {});
}
loadHealth();
loadProjects();
loadApiKeys();
loadModelSettings();
