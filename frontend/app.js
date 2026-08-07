const healthEl = document.querySelector("#health");
const projectsEl = document.querySelector("#projects");
const form = document.querySelector("#project-form");
const messageEl = document.querySelector("#form-message");
const apiKeysEl = document.querySelector("#api-keys");

function setHealth(text, ok) {
  healthEl.textContent = text;
  healthEl.className = `status-pill ${ok ? "status-ok" : "status-error"}`;
}

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);
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

function renderProjects(projects) {
  if (projects.length === 0) {
    projectsEl.innerHTML = '<p class="empty">还没有项目。先创建一个研究问题吧。</p>';
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

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  messageEl.textContent = "正在创建…";

  const payload = {
    name: document.querySelector("#project-name").value,
    research_question: document.querySelector("#research-question").value,
  };

  try {
    const response = await fetch("/api/v1/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("create project failed");
    form.reset();
    messageEl.textContent = "项目已创建。下一阶段将接入文献证据。";
    await loadProjects();
  } catch (error) {
    messageEl.textContent = "创建失败，请检查 API 日志。";
  }
});

document.querySelector("#refresh").addEventListener("click", loadProjects);
document.querySelector("#refresh-settings").addEventListener("click", loadApiKeys);

loadHealth();
loadProjects();
loadApiKeys();
