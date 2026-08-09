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
const apiBaseForm = document.querySelector("#api-base-form");
const apiBaseInput = document.querySelector("#api-base-url");
const apiBaseStatusEl = document.querySelector("#api-base-status");
const apiBaseMessageEl = document.querySelector("#api-base-message");
const resetApiBaseButton = document.querySelector("#reset-api-base");
const routeLinks = [...document.querySelectorAll("[data-route-link]")];
const appViews = [...document.querySelectorAll("[data-view]")];

const API_BASE_STORAGE_KEY = "wishforge.api_base_url";
const routes = {
  workspace: { title: "研究工作台" },
  "concept-graphs": { title: "概念图" },
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
  const stored = normalizeApiBaseUrl(readStoredApiBaseUrl());
  if (stored) return { value: stored, source: "浏览器保存" };
  const runtimeConfig = window.WISHFORGE_RUNTIME_CONFIG || {};
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
  apiBaseStatusEl.textContent = apiBaseConfiguration.value
    ? `${apiBaseConfiguration.source} · 已设置`
    : "当前页面同源";
  apiBaseStatusEl.className = `tag ${apiBaseConfiguration.value ? "tag-configured" : "tag-missing"}`;
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
  graphId: null,
  graph: null,
  graphs: [],
  pendingPatches: new Map(),
  experimentPlan: null,
  ideaCheck: null,
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
  needs_review: "待人工核验",
  dismissed: "已忽略",
  cross_domain_candidate: "跨领域候选",
  shared_problem: "共同问题",
  method_transfer: "方法迁移候选",
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
  result: "结果",
  related_concept: "相关概念",
  research_gap: "研究空白",
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
});

resetApiBaseButton.addEventListener("click", () => {
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
      return `
        <article class="service-card api-key-row ${slot.configured ? "is-configured" : "is-unconfigured"}" data-api-key-slot="${escapeHtml(slot.id)}">
          <div class="service-card-heading">
            <span class="service-card-icon" aria-hidden="true">${escapeHtml(detail.icon)}</span>
            <div class="service-card-title">
              <div class="setting-title-line">
                <div>
                  <p class="service-card-scope">${escapeHtml(detail.scope)}</p>
                  <h3>${escapeHtml(slot.label)}</h3>
                </div>
                <span class="service-status ${slot.configured ? "is-configured" : "is-unconfigured"}">
                  <span aria-hidden="true" class="service-status-dot"></span>
                  ${slot.configured ? `已连接 ${escapeHtml(slot.masked || "")}` : "等待连接"}
                </span>
              </div>
              <p>${escapeHtml(detail.description)}</p>
              <p class="service-provider"><span class="provider-name">${escapeHtml(slot.provider)}</span><code>${escapeHtml(slot.environment_variable)}</code></p>
            </div>
          </div>
          <div class="service-card-control">
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
          </div>
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
    renderApiKeys(data.slots);
    apiKeyForm.dataset.storage = data.storage || "environment";
  } catch (error) {
    apiKeysEl.innerHTML = '<p class="empty error-text">配置状态读取失败，请确认 API 正在运行。</p>';
  }
}

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
  setApiKeyMessage("正在更新当前进程配置…");
  try {
    const data = await updateApiKeys(payload);
    renderApiKeys(data.slots);
    apiKeyForm.dataset.storage = data.storage || "runtime_memory";
    setApiKeyMessage("已保存。密钥只保存在当前 API 进程内，响应中不会返回明文。", "");
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
  setApiKeyMessage("正在清除当前进程中的该密钥…");
  try {
    const data = await updateApiKeys({ [slot]: "" });
    renderApiKeys(data.slots);
    apiKeyForm.dataset.storage = data.storage || "runtime_memory";
    setApiKeyMessage("已清除该用途的当前进程密钥。", "");
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
  state.analysisId = null;
  state.graphId = null;
  state.graph = null;
  state.graphs = [];
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
  graphAgentForm.classList.add("hidden");
  graphAgentRequestInput.value = "";
  graphAgentMessageEl.textContent = "";
  graphMetaForm.classList.add("hidden");
  graphNameInput.value = "";
  graphRootInput.innerHTML = "";
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
  ledgerCoverageEl.textContent = `证据关联 ${linkCoverage}% · 已核验 ${verifiedCoverage}% · ${ledger.linked_claim_count || 0}/${ledger.claims?.length || 0} 条主张`;
  ledgerMessageEl.textContent = (ledger.warnings || []).join(" ") || "每条主张都可以展开查看关联证据。";
  const evidenceById = new Map((result.evidence || []).map((item) => [item.id, item]));
  ledgerClaimsEl.innerHTML = (ledger.claims || []).map((claim) => {
    const links = (claim.evidence_links || []).map((link) => {
      const card = evidenceById.get(link.evidence_id);
      return `<li><span class="tag">${escapeHtml(displayLabel(link.relation || "background"))}</span> ${escapeHtml(card?.claim || link.evidence_id)}<small>${escapeHtml(link.note || "")}</small></li>`;
    }).join("");
    const statusClass = ["supported", "partially_supported"].includes(claim.status) ? "tag-configured" : "tag-missing";
    return `
      <article class="ledger-claim ${escapeHtml(claim.status || "unverified")}">
        <div class="ledger-claim-heading">
          <span class="tag">${escapeHtml(displayLabel(claim.claim_type || "definition"))}</span>
          <span class="tag ${statusClass}">${escapeHtml(displayLabel(claim.status || "unverified"))} · ${escapeHtml(claim.confidence || "low")}</span>
        </div>
        <p>${escapeHtml(claim.text)}</p>
        ${claim.scope ? `<small class="ledger-scope">${escapeHtml(claim.scope)}</small>` : ""}
        ${links ? `<ul class="ledger-links">${links}</ul>` : `<p class="warning-inline">${escapeHtml(claim.next_action || "需要人工核验")}</p>`}
      </article>
    `;
  }).join("") || '<p class="empty">当前没有可展示的主张。</p>';
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
  graphAgentForm.classList.remove("hidden");
  graphMetaForm.classList.remove("hidden");
  graphNameInput.value = graph.name || "";
  graphRootInput.innerHTML = graph.nodes
    .map((node) => `<option value="${escapeHtml(node.id)}">${escapeHtml(node.label)}</option>`)
    .join("");
  graphRootInput.value = graph.root_id;
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
  const graphResponse = await apiFetch(`/api/v1/graphs/${encodeURIComponent(state.graphId)}`);
  if (!graphResponse.ok) throw new Error("graph request failed");
  renderGraph(await graphResponse.json());
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
  if (!response.ok) return;
  const graphs = await response.json();
  state.graphs = graphs;
  const previousCompareSelection = new Set(
    [...graphComparePickerEl.selectedOptions].map((option) => option.value),
  );
  const previousGallerySelection = new Set(
    [...graphGalleryPickerEl.selectedOptions].map((option) => option.value),
  );
  if (!graphs.length) {
    graphPickerEl.classList.add("hidden");
    graphComparePickerEl.innerHTML = '<option disabled>完成分析后这里会出现概念图</option>';
    graphGalleryPickerEl.innerHTML = '<option disabled>完成分析后这里会出现概念图</option>';
    graphGalleryEl.innerHTML = '<p class="empty">还没有已保存的概念图。</p>';
    return;
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

function renderGraphNodesMarkup(graph, compact = false) {
  const depths = graphDepths(graph);
  const relationsByTarget = {};
  graph.edges.forEach((edge) => {
    const relations = relationsByTarget[edge.target] || [];
    relations.push(edge.relation);
    relationsByTarget[edge.target] = relations;
  });
  const nodes = [...graph.nodes].sort(
    (a, b) => (depths[a.id] - depths[b.id]) || a.label.localeCompare(b.label),
  );
  return nodes.map((node) => `
    <div class="graph-node gallery-node node-${escapeHtml(node.node_type)}" style="--depth:${Math.min(depths[node.id], compact ? 3 : 4)}">
      <div class="node-content">
        <div>
          <span class="node-type">${escapeHtml(node.node_type)}</span>
          <h3>${escapeHtml(node.label)}</h3>
          <p>${escapeHtml(node.summary || "暂无说明")}</p>
        </div>
      </div>
      ${relationsByTarget[node.id] ? `<small class="node-relation">${escapeHtml(relationsByTarget[node.id].join(" · "))}</small>` : ""}
    </div>
  `).join("");
}

function renderGraphGallery(graphs, warnings = []) {
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
            </div>
          </div>
          <p class="graph-gallery-description">${escapeHtml(graph.description || "暂无描述")}</p>
          <div class="graph-gallery-tree">${renderGraphNodesMarkup(graph, true)}</div>
        </article>
      `).join("")}
    </div>
  `;
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
    setGraphGalleryMessage("请至少选择一棵概念图。", "error-text");
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
    setGraphGalleryMessage(`已显示 ${graphs.length} 棵概念图。`, "");
  } catch (error) {
    setGraphGalleryMessage(`多图视图加载失败：${error.message}`, "error-text");
  } finally {
    graphGallerySubmit.disabled = false;
  }
});

graphGalleryEl.addEventListener("click", async (event) => {
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

async function applyUserPatch(operations, reason) {
  if (!state.graphId) return;
  const response = await apiFetch(`/api/v1/graphs/${encodeURIComponent(state.graphId)}/patches`, {
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
  const response = await apiFetch(
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
  const response = await apiFetch(`/api/v1/graphs/${encodeURIComponent(state.graphId)}/patches`, {
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
    const response = await apiFetch(`/api/v1/graphs/${encodeURIComponent(state.graphId)}/agent-patch`, {
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
  const response = await apiFetch(`/api/v1/graphs/${encodeURIComponent(state.graphId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name || undefined, root_id: rootId || undefined, base_version: state.graph.version }),
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
      const response = await apiFetch(
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
  const response = await apiFetch(`/api/v1/analyses/${encodeURIComponent(id)}`);
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
  renderEvidenceLedger(result);
  renderInnovations(result);
  renderResearchBrief(result);
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
document.querySelector("#refresh-settings").addEventListener("click", loadApiKeys);
window.addEventListener("hashchange", () => renderRoute());
routeLinks.forEach((link) => {
  link.addEventListener("click", () => {
    window.setTimeout(() => window.scrollTo({ top: 0, behavior: "smooth" }), 0);
  });
});

renderApiBaseConfiguration();
renderRoute();
loadHealth();
loadProjects();
loadApiKeys();
