# WishForge / 许愿机：研究图谱阶段架构说明

## 1. 这一阶段解决的问题

第一版只承诺一条可以现场演示、可以追溯边界的闭环：

```text
用户输入概念
      │
      ▼
异步 AnalysisJob
      │
      ├── 论文检索 Provider（arXiv / Semantic Scholar / Demo）
      ├── 摘要级 EvidenceCard
      ├── 解释 Provider（OpenAI-compatible / 规则回退）
      ├── ConceptGraph 构建与 Cytoscape 真实图渲染
      ├── OverviewService：异步摘要/开放章节研究方向图、按需检索展开与保存
      ├── Claim/Evidence Ledger（主张级溯源与覆盖率）
      ├── research 模式：三路 AgentRun + ResearchBrief + 谨慎候选
      ├── IdeaCheckService：范围化 prior-art 判断
      ├── ExperimentService：只生成可审阅实验方案草案
      └── SQLite Storage：任务、项目、图谱、Patch、查重记录、实验方案和 Overview 任务
      │
      ▼
前端展示、用户编辑或批准 Agent GraphPatch
```

这不是“自动证明创新”的系统。系统只会在指定数据源和当前检索范围内给出候选，并明确显示证据等级、来源类型和需要人工核验的地方。

## 2. 组件和职责

```text
Vite Web App（Cytoscape.js；后续嵌入 Tauri）
  │ HTTP + 轮询
  ▼
FastAPI API (/api/v1)
  ├── ProjectService       研究项目（SQLite）
  ├── ResearchService      分析任务编排与进度
  │     ├── SearchProvider
  │     │     ├── SemanticScholarProvider
  │     │     └── DemoSearchProvider
  │     └── ExplanationProvider
  │           ├── OpenAICompatibleExplanationProvider
  │           └── RuleBasedExplanationProvider
  ├── ResearchOrchestrator（research 模式）
  │     ├── Community Agent（X / 知乎 / Reddit Provider 边界，当前 demo）
  │     ├── Model Brainstorm Agent（模型或透明启发式回退）
  │     ├── Paper Future Work Agent（当前摘要级限制线索）
  │     └── Synthesis Agent（来源分层、候选去重和范围化 arXiv 检查）
  ├── GraphService         版本化概念图和 GraphPatch 审批
  ├── OverviewService      持久异步任务、方向分类、论文阅读卡、验证、展开和保存
  ├── GraphAgentPatchService  自然语言请求的有界启发式翻译（只生成提案）
  ├── IdeaCheckService     想法查重、相似度分级和替代验证方向
  ├── ExperimentService    假设、基线、指标、消融和失败判据草案
  └── SettingsService      分用途 API Key 状态（不返回明文）
```

### Provider 边界

- `WISHFORGE_PAPER_API_KEY` 只交给论文检索 Provider；
- `WISHFORGE_COMMUNITY_API_KEY` 只交给社区 Provider（当前研究模式仍使用明确标记的 Demo provider）；
- `WISHFORGE_EXPLANATION_API_KEY` 只交给解释模型 Provider；
- `WISHFORGE_EXPERIMENT_API_KEY` 预留给未来执行器，本阶段不会使用；
- 网页 `PATCH /api/v1/settings/api-keys` 写入的四个槽位只覆盖当前进程内的 `Settings`；桌面 Tauri 先把密钥写入 Windows Credential Manager，再注入 sidecar 环境，永远不进入 SQLite、构建资源或普通日志；
- 非敏感 Provider 路由按四个职责分离，可通过 `PATCH /api/v1/settings/providers/{slot}` 配置 Provider、Base URL、模型和启用状态；`POST /api/v1/settings/providers/{slot}/test` 默认只做格式检查，显式 probe 才做无凭据、限时连通性探测；
- 当前没有登录、租户隔离或权限系统，密钥配置接口只适合本机/受保护内网；公网部署前必须加认证、审计和 Secret Manager；
- 外部论文或网页内容是“不可信输入”，不能改变系统提示词、工具权限或 API Key；
- 论文全文只应来自开放来源或用户合法提供的文件。本阶段默认通过 arXiv 处理元数据和摘要，不声称已阅读 PDF 全文。
- IdeaCheck 的 L0–L4 是检索范围内的分诊信号，不是专利或论文法律意义上的新颖性结论。

## 3. API 契约

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/settings/api-keys` | 获取各用途密钥的配置状态和掩码 |
| PATCH | `/api/v1/settings/api-keys` | 在当前进程设置/清除各用途密钥（只返回掩码） |
| GET | `/api/v1/settings/runtime` | 获取兼容的解释模型配置及四个 Provider 槽位的非敏感配置 |
| PATCH | `/api/v1/settings/runtime` | 更新兼容的解释模型路由 |
| PATCH | `/api/v1/settings/providers/{slot}` | 更新单个用途的 Provider、Base URL、模型或启用状态 |
| POST | `/api/v1/settings/providers/{slot}/test` | 返回脱敏的配置状态；可选无凭据连通性探测 |
| GET | `/api/v1/projects` | 获取研究项目 |
| POST | `/api/v1/projects` | 创建草稿项目 |
| POST | `/api/v1/analyses` | 创建异步概念分析任务，返回 `202` 和任务 ID |
| GET | `/api/v1/analyses` | 查看最近分析任务摘要 |
| GET | `/api/v1/analyses/{analysis_id}` | 查看状态、阶段进度和完成结果 |
| GET | `/api/v1/analyses/{analysis_id}/graph` | 读取分析结果中的临时或已保存图快照 |
| PATCH | `/api/v1/analyses/{analysis_id}/graph` | 修改分析快照的图名、说明或根节点，不自动进入图库 |
| POST | `/api/v1/analyses/{analysis_id}/graph/save` | 在用户确认后将分析快照幂等提升为已保存图 |
| GET/POST | `/api/v1/analyses/{analysis_id}/graph/patches` | 列出或创建临时图 Patch；用户 Patch 立即应用，Agent Patch 待审核 |
| POST | `/api/v1/analyses/{analysis_id}/graph/agent-patch` | 把临时图自然语言修改翻译成待审核提案 |
| POST | `/api/v1/analyses/{analysis_id}/graph/nodes/{node_id}/explanation-patch` | 为临时图节点生成待审核解释 |
| POST | `/api/v1/analyses/{analysis_id}/overview` | 按需创建或复用异步研究方向图任务；快速模式/无论文返回冲突 |
| GET | `/api/v1/overviews?analysis_id=...` | 列出持久化 Overview 历史，支持应用重启后重新打开终态或中断任务 |
| GET | `/api/v1/overviews/{overview_id}` | 轮询 Overview 的阶段、进度、结果、范围警告和保存状态 |
| POST | `/api/v1/overviews/{overview_id}/expand` | 在深度和论文预算内细分一个方向节点，使用图版本 CAS |
| POST | `/api/v1/overviews/{overview_id}/directions/{direction_key}/retry` | 只重试一个失败方向，保留其他成功结果与结构化审计 |
| GET | `/api/v1/overviews/{overview_id}/nodes/{node_id}` | 返回 Overview 节点、论文、摘要/章节证据、关系和范围提示 |
| POST | `/api/v1/overviews/{overview_id}/save` | 把临时研究方向图幂等保存到统一图库 |
| GET | `/api/v1/graphs/{graph_id}/nodes/{node_id}` | 返回节点、来源论文、证据、相关边与阅读范围警告 |
| PATCH | `/api/v1/graphs/{graph_id}/layout` | 以图版本 CAS 保存节点坐标与布局算法 |
| GET | `/api/v1/analyses/{analysis_id}/research-brief` | 单独读取 research 模式的三路 Agent Brief |
| GET | `/api/v1/analyses/{analysis_id}/evidence-ledger` | 读取主张—证据账本和覆盖率 |
| POST | `/api/v1/ideas/check` | 对一个研究想法做有界 prior-art 判断并保存结果 |
| GET | `/api/v1/ideas/checks` | 获取已保存的想法查重记录 |
| GET | `/api/v1/ideas/checks/{check_id}` | 获取一条想法查重记录 |
| POST | `/api/v1/ideas/checks/{check_id}/review` | 写入人工核验状态、备注和审阅人，不改变原检索范围 |
| GET | `/api/v1/graphs` | 获取 SQLite 中的概念图列表，可按 `project_id` 过滤 |
| POST | `/api/v1/graphs` | 创建或导入一棵独立概念图（重复 ID 返回 `409`） |
| GET | `/api/v1/graphs/{graph_id}` | 获取当前概念图和版本号 |
| DELETE | `/api/v1/graphs/{graph_id}?expected_version=...` | 删除整张已保存图并级联删除 GraphPatch；历史分析快照保留 |
| GET | `/api/v1/graphs/{graph_id}/subset?node_ids=a,b` | 获取不修改原图的局部裁剪视图 |
| PATCH | `/api/v1/graphs/{graph_id}` | 修改概念图名称、说明或根节点（带版本检查） |
| POST | `/api/v1/graphs/compare` | 选择多棵图或节点子集，生成未验证的跨图连接候选 |
| POST | `/api/v1/graphs/{graph_id}/patches` | 创建用户修改或 Agent 修改提案 |
| GET | `/api/v1/graphs/{graph_id}/patches` | 获取该图的修改提案历史 |
| POST | `/api/v1/graphs/{graph_id}/agent-patch` | 将自然语言修改请求翻译成最多 4 个受限 Agent 操作（只生成 `proposed` 提案） |
| POST | `/api/v1/graphs/{graph_id}/nodes/{node_id}/explanation-patch` | 让 Agent 生成节点解释提案（仍需批准） |
| POST | `/api/v1/graphs/{graph_id}/patches/{patch_id}/apply` | 批准 Agent 提案并应用 |
| POST | `/api/v1/graphs/{graph_id}/patches/{patch_id}/reject` | 拒绝 Agent 提案 |
| POST | `/api/v1/experiments/plans` | 生成并保存只读实验方案草案 |
| GET | `/api/v1/experiments/plans` | 列出已保存实验方案，可按项目过滤 |
| GET | `/api/v1/experiments/plans/{plan_id}` | 读取一份实验方案草案 |
| POST | `/api/v1/experiments/plans/{plan_id}/review` | 记录人工审阅状态，不启动执行 |

分析结果目前包含：

- `papers`：标题、作者、年份、来源、摘要和链接；
- `search_terms` / `retrieval_scope`：本次实际使用的检索词和证据范围；
- `evidence`：论文 ID、摘要摘录、结构化定位、证据类型、支持关系、置信度和人工核验状态；
- `explanation`：一句话、直觉类比、技术机制、演变、相关概念、限制和关联证据 ID；
- `graph`：节点、边、根节点和版本；
- `innovation_candidates`：研究模式下的候选、最近工作、风险和验证步骤；
- `research_brief`：`AgentRun`、社区信号、模型脑暴、论文摘要级限制线索、综合候选、证据覆盖率和 arXiv 范围状态；
- `evidence_ledger`：定义、机制、演变、限制和相关概念等主张，以及每条主张关联的证据卡、状态、置信度、证据关联覆盖、已核验覆盖和下一步核验动作；
- `IdeaCheckResult`：想法、检索词、匹配论文、摘要级“别人怎么做”的易懂说明、L0–L4、置信度、替代方向、验证步骤和人工审阅元数据；
- `ExperimentPlan`：假设、基线、变量、控制项、指标、消融、预期结果、失败判据、资源估计、来源和审阅状态；`execution_status` 固定为 `not_started`；
- `warnings` / `novelty_note`：明确说明 Demo、回退和新颖性检索边界。

持久化表为 `projects`、`analysis_jobs`、`concept_graphs`、`graph_patches`、`analysis_graph_patches`、`overview_jobs`、`idea_checks` 和 `experiment_plans`。`overview_jobs` 保存请求边界、阶段、进度、结果图、保存状态和错误；进程重启时只有真正运行中的 `queued/running` 任务会标记为 `interrupted`，已可查看的 `partial` 结果继续保留。`concept_graphs` 只列出 `save_state=saved` 的图库副本；分析生成的 `transient` 图完整保存在 `analysis_jobs.result.graph` 中。图谱应用修改使用版本 compare-and-swap，并把图和 Patch 放在同一 SQLite 事务中提交；完整 Patch 通过结构校验后还要保证所有节点与根节点连通。删除已保存图时，SQLite 同一事务会级联删除 `graph_patches`，并把关联分析或 Overview 快照的保存状态改回 `transient`；不会删除分析、Overview、论文或证据。

### 3.1 Overview 有界编排架构和边界

```text
AnalysisResult.papers + EvidenceCard
              │ POST /analyses/{id}/overview
              ▼
      durable OverviewJob
              │ background worker
              ├── TopicTaxonomyPlannerAgent：可选模型规划 + 可审计规则回退
              ├── DirectionResearchAgent × ≤4（共享 Provider + 限流器）
              ├── split/keep/merge/discard 与论文唯一归属
              ├── 开放 arXiv PDF 章节读取；逐篇摘要降级
              ├── 方向/论文归属与 DAG 校验；局部失败保留 partial
              ├── OverviewSynthesisAgent：可选模型展示文案 + 规则回退
              ├── recency_score / heat_score
              ▼
transient research_direction ConceptGraph
              │ 用户确认保存
              ▼
       saved concept_graphs row
```

配置了解释模型 Key 时，方向规划和最终展示综合是两个独立的结构化模型调用；模型输出必须经过方向、论文/证据 ID、数量和 DAG 校验。未配置 Key、调用失败或结果不合格时，任务警告会标记 `deterministic_rule_fallback`。arXiv/Demo 可以安全重建时，方向工作器执行专属外部检索；按需展开也会再次运行所选方向的专属查询，而不是只重排旧论文。需要论文专用 Key 的 Provider 无法安全重建时会退回原分析论文并告警，不借用其他用途密钥。每次方向运行保存结构化审计（Provider、查询、返回/接纳/拒绝/截断数、决策和错误），失败方向可单独重试。PDF 阅读只允许规范 arXiv HTTPS 地址，30 秒、20 MB、无 OCR；运行依赖包含 `pypdf`，不可用时才尝试本机 `pdftotext`，任何失败都保持 `abstract_only`。成功抽取的章节保存短摘录、章节名和规范 PDF URL，不伪造页码；证据仍标为未人工核验。论文节点必须是叶节点并带 `paper_id`；方向最大深度、一级方向数、每方向论文数、总论文数和并发均受限。

`OverviewResult.agent_runs` 是结构化执行账本，覆盖方向规划、方向协调与每个方向工作器、论文读取、图验证、最终综合，以及后续 expand/retry。记录只包含角色、执行模式、Provider、真实模型名（仅真实模型调用）、状态、时间、耗时、计数、安全摘要和错误类别；规则执行不能填写模型名，模型失败与规则回退分别落一条记录。密钥、请求头、代理 URL、Prompt、原始响应和 Provider 原始异常文本不进入 SQLite。

Overview 创建接口会把当前请求解析出的运行时 Settings 对象传入后台线程，只在内存中供这次任务构造 Provider；API Key 不写入 `overview_jobs`。因此设置页刚更新的解释模型 Key、模型名和代理 Base URL 会作用于随后创建的 Overview，而不会因为跨线程重新读取环境配置而退回旧设置。

前端由 Vite 打包 Cytoscape.js，本地开发端口是 1420，`/api` 代理到 FastAPI 8000。普通概念图使用 `cose`，研究方向图使用有向 `breadthfirst` 分层布局；两个页面共享 renderer、视觉分数和 Inspector 模块。FastAPI 在存在 `frontend/dist/index.html` 时优先托管构建产物，未构建时保留源码壳用于本地诊断。

### 3.2 图生命周期

```text
AnalysisJob.result.graph
       │  save_state=transient
       │  用户确认 POST /analyses/{id}/graph/save
       ▼
concept_graphs
       │  save_state=saved，可通过 GraphPatch 编辑
       │  DELETE /graphs/{id}
       ▼
AnalysisJob.result.graph（仍保留，回到 transient）
```

服务进程还维护 ResearchService 的分析缓存，因此删除接口成功后会同步刷新热缓存，避免同一进程内下一次读取仍显示已删除的 `saved` 状态。临时图已经接入独立的 `analysis_graph_patches` 与统一的纯 Patch 引擎：手动修改立即按版本应用，Agent 修改和节点解释仍先提案、再由用户批准或拒绝，不会因为编辑而偷偷进入已保存图库。

## 4. GraphPatch 为什么是必要的

Agent 不直接修改图对象，而是生成结构化操作：

```text
Agent 生成 GraphPatch
       │
       ▼
服务端校验节点、边和 base_version
       │
       ├── actor=user  → 立即应用
       └── actor=agent → proposed
                              │
                              ▼
                      用户预览后 Apply / Reject
```

自然语言工具使用同一条安全边界：

```text
自然语言 request（最多 2000 字）
        ↓
有界规则翻译（最多 4 个 add/update/remove 操作）
        ↓
记录 translation_mode=heuristic、原始请求和 warnings
        ↓
GraphService 校验 root / locked node / edge / base_version
        ↓
返回 actor=agent、status=proposed 的 GraphPatch
```

第一版没有为这条路径伪造模型理解：无法确定结构性意图时，会把请求作为目标节点的“待核验备注”提案，并在 `warnings` 中说明原因。提案仍需人工预览后调用 `apply` 或 `reject`；自然语言接口本身绝不写入概念图。

每次应用都会让 `graph.version` 加一。若提案基于旧版本，服务端返回 `409 Conflict`，前端需要重新获取图后再生成提案。根节点不可删除；边的两个端点必须存在；删除节点会同时删除关联边。

本阶段还是单用户本地 MVP，`actor` 字段用于区分网页用户操作和 Agent 提案；正式部署时必须接入身份认证，并由服务端权限决定 actor，不能信任客户端自行声明。

## 5. 当前明确不做的事情

为保证比赛首版稳定，下列能力先不成为主流程的硬依赖：

- X、知乎、Reddit 的实时爬取（当前仅有明确标记的 demo 社区 Provider 和可替换接口）；
- “确保 arXiv 没有相同论文”或任何绝对新颖性承诺；
- 全量 PDF 图表理解和商业数据库的版权内容；
- 真实仪器控制、耗材管理和任意代码执行；
- 实验方案批准后的自动执行（本阶段只记录审阅状态，绝不启动命令或网络任务）；
- 多用户权限、团队协作和跨多个概念树的自动合并（当前只生成跨图候选；网页并排画布和临时局部裁剪不会自动合并或写回）；

社区讨论若在后续接入，应标记为探索性痛点信号；模型脑暴应标记为未验证假设；当前论文分支只有摘要级线索，已明确标为 `abstract_signal`，不能声称读过全文 `Discussion`。接入合法的 PDF / HTML 全文后，再把 `Discussion`、`Conclusion`、`Limitations` 和 `Future Work` 单独保存原文定位，不能与事实证据混成一栏。

## 6. 后续演进路线

1. **持久化层**：SQLite → PostgreSQL，保存 `AnalysisRun`、`Paper`、`Evidence`、`ConceptGraph`、`GraphPatch` 和版本历史。
2. **主张级证据账本**：把解释拆成 Claim/Paragraph，并绑定 `evidence_ids`、原文位置和支持/反驳关系。
3. **多 Agent 研究模式**：当前已实现模型可选的方向规划/最终综合、可审计规则回退、方向并行检索、单方向重试，以及开放 arXiv PDF 的有界章节文本抽取；下一步接入真实社区连接器、统一模型预算与更可靠的 PDF 版面定位。
4. **创新核验**：接入 arXiv、OpenAlex、Crossref 等数据源，保存查询词、时间、筛选条件和相似论文；输出“当前检索范围内未发现直接等价工作”。
5. **实验契约**：生成结构化 `ProtocolSpec`，经过安全检查和人工批准后，先在仿真环境运行。
6. **隔离执行器**：参考 Curie/EOS/PyLabRobot 的沙箱、协议校验、设备抽象和产物血缘，禁止 Agent 直接获得主机 Shell 权限。

## 7. 验收建议

用固定示例“注意力机制”验收：

1. 选择“文献解释 / 初学者”；
2. 看到论文、来源类型、摘要和证据卡；
3. 看到分层解释和概念图；
4. 手动编辑一个节点；
5. 提交一个 Agent GraphPatch，预览后批准；
6. 观察版本从 `v1` 变为 `v2`；
7. 切换“研究线索”，检查候选和新颖性免责声明；
8. 在“想法查重”中输入 `PagedAttention 管理 KV cache`，确认会显示 L0–L4、匹配论文和人工核验步骤；
9. 创建第二棵概念图，在“跨图借鉴”中选择两棵图，确认结果带有低置信度和验证步骤，且原图版本不变。
10. 在“同时查看多棵概念树”中选择多棵图，分别验收整图并排展示和按节点 ID 的临时裁剪。
