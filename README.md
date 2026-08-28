# 许愿机 / WishForge

面向科研人员的证据驱动研究工作台：把一个模糊想法变成有来源、能理解、可继续研究的知识。

当前仓库处于 **研究图谱阶段：概念分析、真实关系图与研究方向 Overview**。现已打通“概念 → 多源论文检索 → 证据卡 → 主张—证据账本 → 易懂解释 → 可交互概念图”，并增加按需生成的“主题 → 研究方向 → 细分方向 → 论文叶节点”Overview，以及“研究想法 → 范围化 prior-art 判断”“三路研究 Agent Brief”“多图 → 跨领域候选”和“创新候选 → 实验方案草案”等入口。桌面版已提供首次 API Key 引导、实时 Hacker News 社区线索与新版 Release 检查；非开放论文全文、团队权限和实验执行仍属于后续阶段。

功能的当前可用状态和 API/页面入口见 [已实现功能说明](docs/features.md)；逐次开发过程、失败实验和验收记录见 [开发日志](log.md)。

## 当前分支

开发采用阶段分支流程：

```text
main
  └── codex/*  # 各阶段独立开发分支，验收后合并回 main
```

每个阶段完成后先由项目负责人验收，再合并到 `main`。未通过验收的阶段不会直接进入 `main`。

## 当前第一版做什么

在网页中输入“Attention Mechanism”“LoRA”等概念，选择一种模式：

- **快速解释**：不检索论文，直接调用已配置的 OpenAI-compatible 模型生成易懂说明；未配置模型时明确回退到基础规则解释；
- **文献解释**：默认合并 arXiv、OpenAlex 与 Crossref 的公开元数据检索；单一来源断连时保留其他来源结果。模型阅读可用摘要并生成论文列表、摘要级证据卡、相关概念、演变过程和概念图；只有用户明确启用 Demo 模式时才允许回退到明确标记的演示资料；
- **研究线索**：在文献解释的基础上，用“限制 / future work / 方法对比”检索词做一次有预算的 prior-art 扩展，再生成探索性候选，列出最近资料、风险、可行性和最小验证步骤。
- **三路研究 Brief**：研究模式会并行记录社区痛点 Agent、模型/启发式脑暴 Agent 和论文限制/Future Work Agent，再由综合记录汇总候选。社区内容和模型脑暴始终与学术证据分栏显示；默认读取实时 Hacker News 公开讨论，X 与 Reddit 需由用户配置官方 Bearer Token，知乎不会进行未授权抓取。
- **想法查重**：输入一段研究想法，展示实际检索词、匹配论文、摘要级证据、L0–L4 相似度分级、替代方向和最小验证步骤；结果保存到 SQLite，方便回看。
- 查重结果可以通过人工审阅接口记录 `reviewed / dismissed / needs_review`、审阅人和备注；这只更新审阅元数据，不会把范围化检索升级成原创性结论。
- **跨图借鉴**：保存多棵概念图后，可选择多图和节点子集，生成带关系类型、证据 ID、风险提示和验证步骤的跨领域候选；候选不会自动写回原图。
- **多图画布**：在网页中选择多棵已保存概念图并排查看，也可以按节点 ID生成临时局部视图；局部视图不改变源图。
- **主张—证据账本**：把解释中的定义、机制、演变和限制拆成可追踪主张，显示证据关联、覆盖率、置信度和下一步人工核验动作；没有人工核验时不会把摘要线索显示成“已证实”。
- **实验方案草案**：从自由文本、创新候选或 prior-art 结果生成假设、基线、变量、控制项、指标、消融、预期结果、失败判据、资源估计和证据来源。草案可以保存并由用户批准/退回/拒绝，但本阶段始终不执行代码或实验。

概念图支持改名、节点手动编辑/新增，以及让 Agent 为节点生成解释。用户也可以通过 `POST /api/v1/graphs` 独立创建或导入一棵概念树。所有 Agent 修改都通过 `GraphPatch`：先进入“待批准”状态，服务端按图谱版本检查冲突后才应用；用户自己的修改则立即应用。网页或其他 Agent 也可以调用自然语言工具，把“在 Attention 下增加 FlashAttention 节点”翻译成最多 4 个受限操作；第一版使用透明启发式翻译，并把原始请求、翻译模式和警告保存在提案中。

第一版的证据边界需要牢记：

> Demo 资料、规则回退解释和模型生成的研究候选只是为了保证流程可演示。它们不会被伪装成正式论文结论，也不能证明某个想法在全球范围内绝对原创。

L4 只表示：在本次记录的数据库、关键词、论文数量和“标题/摘要/公开元数据”范围内，暂未发现直接等价工作；这不是“arXiv 上绝对没有相同论文”的证明。

## 目录结构

```text
.
├── backend/                 # FastAPI API 与领域服务
│   └── app/
├── frontend/                # Vite + Cytoscape.js 本地 Web 控制台
├── runner/                  # 后续本地 Docker/GPU 实验执行器的边界说明
├── docs/                    # 架构和阶段验收说明
├── docker-compose.yml
└── .env.example
```

## 本地运行

在仓库根目录执行（PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
$env:PYTHONPATH = "backend"
python -m uvicorn app.main:app --reload
```

首次运行还需要构建前端：

```powershell
cd frontend
npm install
npm run build
cd ..
```

然后打开 <http://localhost:8000>。FastAPI 会优先托管 `frontend/dist`；API 文档在 <http://localhost:8000/docs>。

需要前端热更新时，在另一个 PowerShell 窗口运行 `cd frontend; npm run dev`，然后打开 <http://127.0.0.1:1420>。Vite 会把 `/api` 代理到本地 8000 端口。

阶段验收可以在已有本地服务上运行真实 Chrome smoke test：先用临时目录中的 `WISHFORGE_STORAGE_PATH` 启动专用 FastAPI 服务，再设置 `WISHFORGE_SMOKE_URL`、已有的 `WISHFORGE_OVERVIEW_ID` 和可选的 `WISHFORGE_CHROME_PATH`，最后在 `frontend` 目录执行 `npm run smoke:browser`。它会验证 Overview 历史恢复、非空 Cytoscape 画布、节点 Inspector、边筛选，以及连续分析后的默认保存弹窗。不要把 smoke test 指向日常使用的 SQLite 数据库。

如果你在 Git Bash、WSL 或 Linux 中运行，路径分隔符要使用 `/`：

```bash
source .venv/bin/activate
pip install -r backend/requirements.txt
PYTHONPATH=backend python -m uvicorn app.main:app --reload
```

常见错误是把 PowerShell 的反斜杠路径复制到 Bash，导致 `backend\requirements.txt` 被当成 `backendrequirements.txt`；或者直接输入了 `.venvScriptsActivate.ps1`，少了路径分隔符。使用与终端匹配的命令即可。

## API Key 配置

不同用途的服务使用不同的配置槽位，避免一种用途的密钥被另一种用途误用：

```text
WISHFORGE_PAPER_API_KEY          # 论文检索
WISHFORGE_COMMUNITY_API_KEY      # X / Reddit 社区 Provider 的 Bearer Token
WISHFORGE_EXPLANATION_API_KEY   # 解释模型
WISHFORGE_EXPERIMENT_API_KEY    # 实验执行
WISHFORGE_EXPLANATION_MODEL     # 解释模型名称（默认 gpt-4.1-mini）
WISHFORGE_EXPLANATION_BASE_URL  # OpenAI-compatible 服务地址
```

复制 [.env.example](<D:/C++/search_agent/.env.example>) 为 `.env` 后填写。网页设置面板只显示“已配置/未配置”和掩码，不会返回明文密钥。

如果使用 OpenAI 兼容代理，代理地址不是填在 API Key 输入框，而是在设置页的“解释模型代理”卡片中填写；对应环境变量是 `WISHFORGE_EXPLANATION_BASE_URL`。地址填写到 `/v1` 这一层，例如 `https://proxy.example.com/v1`，后端会自动请求 `/chat/completions`。浏览器开发模式的网页输入只覆盖当前 API 进程；Windows 桌面版会持久化非敏感路由设置，服务器部署则应写入后端 `.env`。

桌面版“配置引导”也提供一键填入。手动填写时可参考：

| 服务 | Provider | 模型名称 | Base URL |
| --- | --- | --- | --- |
| DeepSeek V4 Flash | `openai_compatible` | `deepseek-v4-flash` | `https://api.deepseek.com/v1` |
| DeepSeek V4 Pro | `openai_compatible` | `deepseek-v4-pro` | `https://api.deepseek.com/v1` |
| OpenAI GPT-5.6 Sol | `openai` | `gpt-5.6-sol` | `https://api.openai.com/v1` |

在“解释模型”卡片粘贴该服务自己的 API Key 后，先点击“保存模型路由”，再点击“保存 API Key”。论文检索默认使用无需 Key 的 arXiv、OpenAlex、Crossref 多源合并。

配置状态接口：

```text
GET /api/v1/settings/api-keys
```

网页也可以通过下面的接口配置或清除当前进程的密钥：

```text
PATCH /api/v1/settings/api-keys
Content-Type: application/json

{
  "paper_search": "sk-...",
  "community_search": "sk-...",
  "explanation_model": "sk-...",
  "experiment_runner": "sk-..."
}
```

接口只返回掩码和 `configured` 状态，绝不返回明文。浏览器开发模式下，网页输入只保存在当前 API 进程内存；Windows 桌面版会将 API Key 存入 Windows 凭据管理器，重启后仍可用。传入空字符串可清除对应槽位。

当前接口没有用户登录和权限系统，网页密钥配置只适合本机或受保护的内网演示；不要把这个版本直接暴露到公网。

模型代理的非敏感运行时设置接口：

```text
GET /api/v1/settings/runtime
PATCH /api/v1/settings/runtime
Content-Type: application/json

{
  "explanation_provider": "openai_compatible",
  "explanation_model": "qwen-plus",
  "explanation_base_url": "https://proxy.example.com/v1"
}
```

这个接口不会接收或返回 API Key；Key 仍通过 `/settings/api-keys` 单独配置。桌面版会把这些非敏感设置保存在应用数据目录，供下次启动时恢复。

也可以不用网页，直接用 API 验收一轮：

```powershell
$job = Invoke-RestMethod -Method Post http://localhost:8000/api/v1/analyses `
  -ContentType "application/json" `
  -Body '{"concept":"Attention Mechanism","level":"research","audience":"beginner","max_papers":6}'

Invoke-RestMethod "http://localhost:8000/api/v1/analyses/$($job.id)"
```

返回的 `result` 中会有 `papers`、`evidence`、`explanation`、`graph` 和 `innovation_candidates`。当 `level=research` 时还会有 `research_brief`，其中按角色保存 `agent_runs`、社区信号、模型候选、论文摘要级限制线索、综合候选、覆盖率和 arXiv 范围状态。`GraphPatch` 的 Agent 提案先调用创建接口，再调用 `apply` 或 `reject`；用户手动修改则带 `actor: "user"` 立即应用。

自然语言概念图修改示例（只生成提案，不会直接改图）：

```powershell
$patch = Invoke-RestMethod -Method Post `
  "http://localhost:8000/api/v1/graphs/$graphId/agent-patch" `
  -ContentType "application/json" `
  -Body '{"request":"在根节点下增加一个 FlashAttention 节点，并说明它要解决什么问题","target_node_id":"root","base_version":1}'

# 预览 $patch.operations 和 $patch.warnings 后，再由用户决定：
Invoke-RestMethod -Method Post `
  "http://localhost:8000/api/v1/graphs/$graphId/patches/$($patch.id)/apply"
```

请求模型只接受 `request`、可选 `target_node_id`、`base_version`、`language` 和 `max_operations(1-4)`。不能从自然语言接口直接提交任意字段、解锁节点或删除根节点；这些边界仍由 GraphService 在提案阶段校验，旧版本会返回 `409 Conflict`。

独立创建一棵手工概念图：

```powershell
$graph = Invoke-RestMethod -Method Post http://localhost:8000/api/v1/graphs `
  -ContentType "application/json" `
  -Body '{"name":"我的概念树","root_id":"root","nodes":[{"id":"root","label":"研究主题","node_type":"concept"}]}'
```

创建接口会校验根节点、节点 ID 和边端点；非法图谱返回 `422`，重复的显式图 ID 返回 `409`，不会覆盖已有图。

研究 Brief 也可以单独读取：

```text
GET /api/v1/analyses/{analysis_id}/research-brief
```

想法查重示例：

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/ideas/check `
  -ContentType "application/json" `
  -Body '{"idea":"用分页机制管理长上下文 LLM 的 KV cache","max_papers":8}'
```

返回的 `similarity_level` 使用以下含义：`L0` 直接已有工作、`L1` 核心方法高度相似、`L2` 组件或组合相似、`L3` 问题相近但机制不同、`L4` 当前检索范围未发现直接等价。所有级别都需要人工复核。

实验方案草案示例：

```powershell
$plan = Invoke-RestMethod -Method Post http://localhost:8000/api/v1/experiments/plans `
  -ContentType "application/json" `
  -Body '{"idea":"降低长上下文 LLM 推理的 KV Cache 显存占用","baseline":"标准 KV Cache 管理"}'

Invoke-RestMethod "http://localhost:8000/api/v1/experiments/plans/$($plan.id)"

Invoke-RestMethod -Method Post `
  "http://localhost:8000/api/v1/experiments/plans/$($plan.id)/review" `
  -ContentType "application/json" `
  -Body '{"status":"approved","note":"先做小规模预实验","reviewer":"researcher"}'
```

无论审阅状态是什么，返回中的 `execution_status` 都保持 `not_started`。它是“可审阅协议”，不是实验观测结果。

## Docker 运行

```powershell
docker compose up --build
```

## 产品运行方式

GitHub Pages 不再作为产品部署目标。当前产品同时支持浏览器开发模式和 Tauri Windows 桌面 App。桌面 App 启动时会自动拉起本地 Python sidecar，不需要单独启动 FastAPI。

Windows Release 的构建和下载说明见 [发布 Windows 桌面版](docs/releasing.md)。

### Windows 桌面 App

普通使用直接运行安装包 `src-tauri\target\release\bundle\nsis\WishForge_0.2.3_x64-setup.exe`，安装后从开始菜单打开 WishForge；不需要手动启动 Python、Vite 或 sidecar。首次启动会自动打开设置并展示不含密钥的模型配置引导。GitHub Tag 页面下载的 Source code zip 仅供开发者使用，普通用户应下载 Release Assets 中的 `*-setup.exe`。

### Windows 桌面开发模式

最简单的方式是双击仓库根目录中的 `启动 WishForge.bat`。这是开发者启动方式，要求本机已安装 Python、Node.js、Rust 和项目依赖；普通用户应使用 Release 安装包。

也可以在 PowerShell 中执行：

```powershell
cd D:\C++\search_agent
.\start-wishforge.ps1
```

请在 Windows PowerShell（不是 WSL）中执行：

```powershell
cd D:\C++\search_agent
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
pip install pyinstaller
cd frontend
npm install
npm.cmd run tauri:dev
```

如果 PowerShell 禁止执行 `npm.ps1`，使用上面的 `npm.cmd` 即可。首次启动会打开 WishForge 桌面窗口；关闭窗口会同时停止本地 sidecar。

生成可安装版本：

```powershell
cd D:\C++\search_agent\frontend
npm.cmd run tauri:build
```

默认生成面向普通 Windows 用户的 NSIS 一键安装程序：`src-tauri\target\release\bundle\nsis\WishForge_0.2.3_x64-setup.exe`。构建前会自动生成 sidecar，并真实调用健康接口；无法启动的 sidecar 不会进入安装包。

## 当前阶段验收标准

- `GET /api/v1/health` 返回 `status=ok`，服务名称显示为许愿机；
- Web 首页可以打开并显示 API 状态；
- Web 首页可以看到并配置论文检索、社区探索、解释模型和实验执行四个独立密钥槽位（当前进程内存，不回显明文）；
- 可以创建和查看一个研究项目，并在服务重启后从 SQLite 恢复；
- 可以创建异步概念分析任务并轮询阶段进度；
- 文献模式能返回论文元数据、摘要级证据卡、分层解释和概念图；
- 文献/研究模式结果可以按需生成异步研究方向 Overview，结构固定为“主题 → 核心问题 → 方法路线 → 论文证据”；
- 概念图和研究方向图以真实节点与连线呈现，支持缩放、平移、拖拽、搜索/筛选和节点详情；
- 临时概念图可编辑且 Agent 修改必须先审核；已保存图可保存手动布局；
- Overview 使用有界方向级并行检索；配置解释模型后，每个问题分支会由独立审查 Agent 判断 split/keep 和方法归组，服务端拒绝越界论文 ID并保留回退审计；
- 开放 arXiv PDF 通过 `pypdf` 读取 Introduction、Method、Experiment、Discussion、Conclusion 等可用章节并生成未核验证据卡，失败逐篇退回摘要；论文阅读 Agent 只能基于这些证据与摘要生成“问题/方法/怎么做”，不能改变来源范围；
- 研究模式能返回谨慎的创新候选和新颖性范围说明；
- 研究模式能返回社区 / 模型脑暴 / 论文限制三路 AgentRun，以及综合候选和来源标签；
- 可以通过 `POST /api/v1/ideas/check` 对一个研究想法做范围化 prior-art 判断，并通过 `GET /api/v1/ideas/checks` 回看记录；
- 可以通过 `POST /api/v1/ideas/checks/{check_id}/review` 写入人工核验状态和备注；
- 可以通过 `POST /api/v1/graphs` 独立创建或导入一棵概念图，并通过 `GET /api/v1/graphs` 回看；
- 可以通过 `POST /api/v1/graphs/compare` 选择多棵概念图或节点子集，生成未验证的跨图候选；
- Web 页面可以把多棵概念图并排显示，并按节点 ID生成不落库的局部画布；
- 可以获取概念图、手动新增/编辑节点，并提交 Agent GraphPatch 后批准或拒绝；
- 可以通过 `POST /api/v1/graphs/{graph_id}/agent-patch` 把自然语言修改需求转换为有界、可审阅的 Agent GraphPatch；提案不会直接改图，并记录启发式翻译警告；
- 分析任务、概念图、Patch、项目和想法查重结果写入 SQLite，重启后可恢复；
- 图谱版本冲突会返回 `409 Conflict`，防止旧提案覆盖新修改；
- `python -m pytest` 全部通过；
- README、架构说明和后续执行器边界清晰；
- 不在本阶段引入任意代码执行权限。
- 实验方案可以保存、重启后恢复并记录人工审阅状态；批准不会启动执行器；
- 分析结果可以通过 `GET /api/v1/analyses/{analysis_id}/evidence-ledger` 查看主张—证据账本。

下一阶段优先实现全文/用户文献库、arXiv/OpenAlex/Crossref 多源检索、知乎等经授权的社区连接器、Discussion/Future Work 结构化阅读、证据冲突和覆盖度驱动的自适应检索，以及更严格的 Agent 预算/重试；之后再接入经过人工批准、默认只读的隔离计算实验执行器。
