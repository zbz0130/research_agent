# WishForge / 许愿机：Stage 1 架构说明

## 1. 这一阶段解决的问题

第一版只承诺一条可以现场演示、可以追溯边界的闭环：

```text
用户输入概念
      │
      ▼
异步 AnalysisJob
      │
      ├── 论文检索 Provider（Semantic Scholar / Demo）
      ├── 摘要级 EvidenceCard
      ├── 解释 Provider（OpenAI-compatible / 规则回退）
      ├── ConceptGraph 构建
      ├── research 模式：三路 AgentRun + ResearchBrief + 谨慎候选
      ├── IdeaCheckService：范围化 prior-art 判断
      └── SQLite Storage：任务、项目、图谱、Patch 和查重记录
      │
      ▼
前端展示、用户编辑或批准 Agent GraphPatch
```

这不是“自动证明创新”的系统。系统只会在指定数据源和当前检索范围内给出候选，并明确显示证据等级、来源类型和需要人工核验的地方。

## 2. 组件和职责

```text
Browser（静态 HTML/CSS/JS）
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
  ├── IdeaCheckService     想法查重、相似度分级和替代验证方向
  └── SettingsService      分用途 API Key 状态（不返回明文）
```

### Provider 边界

- `WISHFORGE_PAPER_API_KEY` 只交给论文检索 Provider；
- `WISHFORGE_EXPLANATION_API_KEY` 只交给解释模型 Provider；
- `WISHFORGE_EXPERIMENT_API_KEY` 预留给未来执行器，本阶段不会使用；
- 网页 `PATCH /api/v1/settings/api-keys` 写入的三个槽位只覆盖当前进程内的 `Settings`，重启后回到 `.env`；本地第一版不把明文密钥写进 SQLite；
- 当前没有登录、租户隔离或权限系统，密钥配置接口只适合本机/受保护内网；公网部署前必须加认证、审计和 Secret Manager；
- 外部论文或网页内容是“不可信输入”，不能改变系统提示词、工具权限或 API Key；
- 论文全文只应来自开放来源或用户合法提供的文件。本阶段默认只处理 Semantic Scholar 元数据和摘要。
- IdeaCheck 的 L0–L4 是检索范围内的分诊信号，不是专利或论文法律意义上的新颖性结论。

## 3. API 契约

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/settings/api-keys` | 获取各用途密钥的配置状态和掩码 |
| PATCH | `/api/v1/settings/api-keys` | 在当前进程设置/清除各用途密钥（只返回掩码） |
| GET | `/api/v1/projects` | 获取研究项目 |
| POST | `/api/v1/projects` | 创建草稿项目 |
| POST | `/api/v1/analyses` | 创建异步概念分析任务，返回 `202` 和任务 ID |
| GET | `/api/v1/analyses` | 查看最近分析任务摘要 |
| GET | `/api/v1/analyses/{analysis_id}` | 查看状态、阶段进度和完成结果 |
| GET | `/api/v1/analyses/{analysis_id}/research-brief` | 单独读取 research 模式的三路 Agent Brief |
| POST | `/api/v1/ideas/check` | 对一个研究想法做有界 prior-art 判断并保存结果 |
| GET | `/api/v1/ideas/checks` | 获取已保存的想法查重记录 |
| GET | `/api/v1/ideas/checks/{check_id}` | 获取一条想法查重记录 |
| GET | `/api/v1/graphs` | 获取 SQLite 中的概念图列表，可按 `project_id` 过滤 |
| GET | `/api/v1/graphs/{graph_id}` | 获取当前概念图和版本号 |
| GET | `/api/v1/graphs/{graph_id}/subset?node_ids=a,b` | 获取不修改原图的局部裁剪视图 |
| PATCH | `/api/v1/graphs/{graph_id}` | 修改概念图名称、说明或根节点（带版本检查） |
| POST | `/api/v1/graphs/compare` | 选择多棵图或节点子集，生成未验证的跨图连接候选 |
| POST | `/api/v1/graphs/{graph_id}/patches` | 创建用户修改或 Agent 修改提案 |
| GET | `/api/v1/graphs/{graph_id}/patches` | 获取该图的修改提案历史 |
| POST | `/api/v1/graphs/{graph_id}/nodes/{node_id}/explanation-patch` | 让 Agent 生成节点解释提案（仍需批准） |
| POST | `/api/v1/graphs/{graph_id}/patches/{patch_id}/apply` | 批准 Agent 提案并应用 |
| POST | `/api/v1/graphs/{graph_id}/patches/{patch_id}/reject` | 拒绝 Agent 提案 |

分析结果目前包含：

- `papers`：标题、作者、年份、来源、摘要和链接；
- `search_terms` / `retrieval_scope`：本次实际使用的检索词和证据范围；
- `evidence`：论文 ID、摘要摘录、结构化定位、证据类型、支持关系、置信度和人工核验状态；
- `explanation`：一句话、直觉类比、技术机制、演变、相关概念、限制和关联证据 ID；
- `graph`：节点、边、根节点和版本；
- `innovation_candidates`：研究模式下的候选、最近工作、风险和验证步骤；
- `research_brief`：`AgentRun`、社区信号、模型脑暴、论文摘要级限制线索、综合候选、证据覆盖率和 arXiv 范围状态；
- `IdeaCheckResult`：想法、检索词、匹配论文、L0–L4、置信度、替代方向和验证步骤；
- `warnings` / `novelty_note`：明确说明 Demo、回退和新颖性检索边界。

持久化表为 `projects`、`analysis_jobs`、`concept_graphs`、`graph_patches` 和 `idea_checks`。图谱应用修改使用版本 compare-and-swap，并把图和 Patch 放在同一 SQLite 事务中提交。

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

每次应用都会让 `graph.version` 加一。若提案基于旧版本，服务端返回 `409 Conflict`，前端需要重新获取图后再生成提案。根节点不可删除；边的两个端点必须存在；删除节点会同时删除关联边。

本阶段还是单用户本地 MVP，`actor` 字段用于区分网页用户操作和 Agent 提案；正式部署时必须接入身份认证，并由服务端权限决定 actor，不能信任客户端自行声明。

## 5. 当前明确不做的事情

为保证比赛首版稳定，下列能力先不成为主流程的硬依赖：

- X、知乎、Reddit 的实时爬取（当前仅有明确标记的 demo 社区 Provider 和可替换接口）；
- “确保 arXiv 没有相同论文”或任何绝对新颖性承诺；
- 全量 PDF 图表理解和商业数据库的版权内容；
- 真实仪器控制、耗材管理和任意代码执行；
- 多用户权限、团队协作和跨多个概念树的自动合并（当前只生成跨图候选；网页并排画布和临时局部裁剪不会自动合并或写回）；

社区讨论若在后续接入，应标记为探索性痛点信号；模型脑暴应标记为未验证假设；当前论文分支只有摘要级线索，已明确标为 `abstract_signal`，不能声称读过全文 `Discussion`。接入合法的 PDF / HTML 全文后，再把 `Discussion`、`Conclusion`、`Limitations` 和 `Future Work` 单独保存原文定位，不能与事实证据混成一栏。

## 6. 后续演进路线

1. **持久化层**：SQLite → PostgreSQL，保存 `AnalysisRun`、`Paper`、`Evidence`、`ConceptGraph`、`GraphPatch` 和版本历史。
2. **主张级证据账本**：把解释拆成 Claim/Paragraph，并绑定 `evidence_ids`、原文位置和支持/反驳关系。
3. **多 Agent 研究模式**：当前已实现社区信号、论文摘要限制、模型假设三个子任务并行和 `AgentRun`；下一步增加真实连接器、超时/预算、重试与全文 section 抽取。
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
