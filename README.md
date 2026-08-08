# 许愿机 / WishForge

面向科研人员的证据驱动研究工作台：把一个模糊想法变成有来源、能理解、可继续研究的知识。

当前仓库处于 **Stage 1：概念分析 MVP**。这一阶段已经打通“概念 → 论文检索 → 证据卡 → 易懂解释 → 概念图”的首条闭环；研究模式还会生成带有相似工作提示和验证步骤的探索性候选。真实实验执行、社交平台抓取和数据库持久化仍属于后续阶段。

## 当前分支

开发采用阶段分支流程：

```text
main
  └── codex/literature-explanation  # 当前阶段：概念分析 MVP（待验收）
```

每个阶段完成后先由项目负责人验收，再合并到 `main`。未通过验收的阶段不会直接进入 `main`。

## 当前第一版做什么

在网页中输入“Attention Mechanism”“LoRA”等概念，选择一种模式：

- **快速解释**：不检索论文，立即给出透明的基础解释；
- **文献解释**：通过 Semantic Scholar 检索，或在无网络时使用明确标记的 Demo 资料，生成论文列表、摘要级证据卡、分层解释和概念图；
- **研究线索**：在文献解释的基础上，用“限制 / future work / 方法对比”检索词做一次有预算的 prior-art 扩展，再生成探索性候选，列出最近资料、风险、可行性和最小验证步骤。

概念图支持改名、节点手动编辑/新增，以及让 Agent 为节点生成解释。所有 Agent 修改都通过 `GraphPatch`：先进入“待批准”状态，服务端按图谱版本检查冲突后才应用；用户自己的修改则立即应用。

第一版的证据边界需要牢记：

> Demo 资料、规则回退解释和模型生成的研究候选只是为了保证流程可演示。它们不会被伪装成正式论文结论，也不能证明某个想法在全球范围内绝对原创。

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

也可以不用网页，直接用 API 验收一轮：

```powershell
$job = Invoke-RestMethod -Method Post http://localhost:8000/api/v1/analyses `
  -ContentType "application/json" `
  -Body '{"concept":"Attention Mechanism","level":"research","audience":"beginner","max_papers":6}'

Invoke-RestMethod "http://localhost:8000/api/v1/analyses/$($job.id)"
```

返回的 `result` 中会有 `papers`、`evidence`、`explanation`、`graph` 和 `innovation_candidates`。`GraphPatch` 的 Agent 提案先调用创建接口，再调用 `apply` 或 `reject`；用户手动修改则带 `actor: "user"` 立即应用。

## Docker 运行

```powershell
docker compose up --build
```

## 当前阶段验收标准

- `GET /api/v1/health` 返回 `status=ok`，服务名称显示为许愿机；
- Web 首页可以打开并显示 API 状态；
- Web 首页可以看到论文检索、解释模型和实验执行三个独立密钥槽位；
- 可以创建和查看一个研究项目（当前使用内存存储）；
- 可以创建异步概念分析任务并轮询阶段进度；
- 文献模式能返回论文元数据、摘要级证据卡、分层解释和概念图；
- 研究模式能返回谨慎的创新候选和新颖性范围说明；
- 可以获取概念图、手动新增/编辑节点，并提交 Agent GraphPatch 后批准或拒绝；
- 图谱版本冲突会返回 `409 Conflict`，防止旧提案覆盖新修改；
- `python -m pytest` 全部通过；
- README、架构说明和后续执行器边界清晰；
- 不在本阶段引入任意代码执行权限。

下一阶段优先实现 SQLite/PostgreSQL 持久化、全文/用户文献库、主张级证据绑定和 Agent 子任务状态；之后再接入隔离的计算实验执行器。
