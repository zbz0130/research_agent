# 许愿机 / WishForge

面向科研人员的证据驱动研究工作台：把一个模糊想法变成有来源、能理解、可继续研究的知识。

当前仓库处于 **Stage 1：概念分析与研究线索 MVP**。这一阶段已经打通“概念 → 论文检索 → 证据卡 → 主张—证据账本 → 易懂解释 → 概念图”的首条闭环，并新增“研究想法 → 范围化 prior-art 判断”“三路研究 Agent Brief”“多图 → 跨领域候选”和“创新候选 → 实验方案草案”的可验收入口。真实社交平台实时抓取、全文页码级证据、团队权限和实验执行仍属于后续阶段。

## 当前分支

开发采用阶段分支流程：

```text
main
  └── codex/first-version-evidence-ledger  # 当前阶段：证据账本 + 实验方案草案（待验收）
```

每个阶段完成后先由项目负责人验收，再合并到 `main`。未通过验收的阶段不会直接进入 `main`。

## 当前第一版做什么

在网页中输入“Attention Mechanism”“LoRA”等概念，选择一种模式：

- **快速解释**：不检索论文，立即给出透明的基础解释；
- **文献解释**：通过 Semantic Scholar 检索，或在无网络时使用明确标记的 Demo 资料，生成论文列表、摘要级证据卡、分层解释和概念图；
- **研究线索**：在文献解释的基础上，用“限制 / future work / 方法对比”检索词做一次有预算的 prior-art 扩展，再生成探索性候选，列出最近资料、风险、可行性和最小验证步骤。
- **三路研究 Brief**：研究模式会并行记录社区痛点 Agent、模型/启发式脑暴 Agent 和论文限制/Future Work Agent，再由综合记录汇总候选。社区内容和模型脑暴始终与学术证据分栏显示；当前没有实时 X、知乎、Reddit 连接器，也没有把摘要伪装成全文 Discussion。
- **想法查重**：输入一段研究想法，展示实际检索词、匹配论文、摘要级证据、L0–L4 相似度分级、替代方向和最小验证步骤；结果保存到 SQLite，方便回看。
- **跨图借鉴**：保存多棵概念图后，可选择多图和节点子集，生成带关系类型、证据 ID、风险提示和验证步骤的跨领域候选；候选不会自动写回原图。
- **多图画布**：在网页中选择多棵已保存概念图并排查看，也可以按节点 ID生成临时局部视图；局部视图不改变源图。
- **主张—证据账本**：把解释中的定义、机制、演变和限制拆成可追踪主张，显示证据关联、覆盖率、置信度和下一步人工核验动作；没有人工核验时不会把摘要线索显示成“已证实”。
- **实验方案草案**：从自由文本、创新候选或 prior-art 结果生成假设、基线、变量、控制项、指标、消融、预期结果、失败判据、资源估计和证据来源。草案可以保存并由用户批准/退回/拒绝，但本阶段始终不执行代码或实验。

概念图支持改名、节点手动编辑/新增，以及让 Agent 为节点生成解释。所有 Agent 修改都通过 `GraphPatch`：先进入“待批准”状态，服务端按图谱版本检查冲突后才应用；用户自己的修改则立即应用。

第一版的证据边界需要牢记：

> Demo 资料、规则回退解释和模型生成的研究候选只是为了保证流程可演示。它们不会被伪装成正式论文结论，也不能证明某个想法在全球范围内绝对原创。

L4 只表示：在本次记录的数据库、关键词、论文数量和“标题/摘要/公开元数据”范围内，暂未发现直接等价工作；这不是“arXiv 上绝对没有相同论文”的证明。

## 目录结构

```text
.
├── backend/                 # FastAPI API 与领域服务
│   └── app/
├── frontend/                # 许愿机 Web 控制台（当前为零构建依赖原型）
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

然后打开 <http://localhost:8000>。API 文档在 <http://localhost:8000/docs>。

如果你在 Git Bash、WSL 或 Linux 中运行，路径分隔符要使用 `/`：

```bash
source .venv/bin/activate
pip install -r backend/requirements.txt
PYTHONPATH=backend python -m uvicorn app.main:app --reload
```

常见错误是把 PowerShell 的反斜杠路径复制到 Bash，导致 `backend\requirements.txt` 被当成 `backendrequirements.txt`；或者直接输入了 `.venvScriptsActivate.ps1`，少了路径分隔符。使用与终端匹配的命令即可。

## API Key 配置

不同用途的服务使用不同的配置槽位，避免查论文的密钥被实验执行器误用：

```text
WISHFORGE_PAPER_API_KEY          # 论文检索
WISHFORGE_EXPLANATION_API_KEY   # 解释模型
WISHFORGE_EXPERIMENT_API_KEY    # 实验执行
WISHFORGE_EXPLANATION_MODEL     # 解释模型名称（默认 gpt-4.1-mini）
WISHFORGE_EXPLANATION_BASE_URL  # OpenAI-compatible 服务地址
```

复制 [.env.example](<D:/C++/search_agent/.env.example>) 为 `.env` 后填写。网页设置面板只显示“已配置/未配置”和掩码，不会返回明文密钥。

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
  "explanation_model": "sk-...",
  "experiment_runner": "sk-..."
}
```

接口只返回掩码和 `configured` 状态，绝不返回明文。第一版把网页输入保存在当前 API 进程的内存中，服务重启后消失；正式部署应改用操作系统密钥环或 Secret Manager。传入空字符串可清除对应槽位。

当前接口没有用户登录和权限系统，网页密钥配置只适合本机或受保护的内网演示；不要把这个版本直接暴露到公网。

也可以不用网页，直接用 API 验收一轮：

```powershell
$job = Invoke-RestMethod -Method Post http://localhost:8000/api/v1/analyses `
  -ContentType "application/json" `
  -Body '{"concept":"Attention Mechanism","level":"research","audience":"beginner","max_papers":6}'

Invoke-RestMethod "http://localhost:8000/api/v1/analyses/$($job.id)"
```

返回的 `result` 中会有 `papers`、`evidence`、`explanation`、`graph` 和 `innovation_candidates`。当 `level=research` 时还会有 `research_brief`，其中按角色保存 `agent_runs`、社区信号、模型候选、论文摘要级限制线索、综合候选、覆盖率和 arXiv 范围状态。`GraphPatch` 的 Agent 提案先调用创建接口，再调用 `apply` 或 `reject`；用户手动修改则带 `actor: "user"` 立即应用。

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

## 当前阶段验收标准

- `GET /api/v1/health` 返回 `status=ok`，服务名称显示为许愿机；
- Web 首页可以打开并显示 API 状态；
- Web 首页可以看到并配置论文检索、解释模型和实验执行三个独立密钥槽位（当前进程内存，不回显明文）；
- 可以创建和查看一个研究项目，并在服务重启后从 SQLite 恢复；
- 可以创建异步概念分析任务并轮询阶段进度；
- 文献模式能返回论文元数据、摘要级证据卡、分层解释和概念图；
- 研究模式能返回谨慎的创新候选和新颖性范围说明；
- 研究模式能返回社区 / 模型脑暴 / 论文限制三路 AgentRun，以及综合候选和来源标签；
- 可以通过 `POST /api/v1/ideas/check` 对一个研究想法做范围化 prior-art 判断，并通过 `GET /api/v1/ideas/checks` 回看记录；
- 可以通过 `POST /api/v1/graphs/compare` 选择多棵概念图或节点子集，生成未验证的跨图候选；
- Web 页面可以把多棵概念图并排显示，并按节点 ID生成不落库的局部画布；
- 可以获取概念图、手动新增/编辑节点，并提交 Agent GraphPatch 后批准或拒绝；
- 分析任务、概念图、Patch、项目和想法查重结果写入 SQLite，重启后可恢复；
- 图谱版本冲突会返回 `409 Conflict`，防止旧提案覆盖新修改；
- `python -m pytest` 全部通过；
- README、架构说明和后续执行器边界清晰；
- 不在本阶段引入任意代码执行权限。
- 实验方案可以保存、重启后恢复并记录人工审阅状态；批准不会启动执行器；
- 分析结果可以通过 `GET /api/v1/analyses/{analysis_id}/evidence-ledger` 查看主张—证据账本。

下一阶段优先实现全文/用户文献库、arXiv/OpenAlex/Crossref 多源检索、真实社区连接器、Discussion/Future Work 结构化阅读、证据冲突和覆盖度驱动的自适应检索，以及更严格的 Agent 预算/重试；之后再接入经过人工批准、默认只读的隔离计算实验执行器。
