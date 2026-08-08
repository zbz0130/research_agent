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
      └── research 模式：谨慎的 InnovationCandidate
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
  ├── ProjectService       研究项目（Stage 1 仍为内存）
  ├── ResearchService      分析任务编排与进度
  │     ├── SearchProvider
  │     │     ├── SemanticScholarProvider
  │     │     └── DemoSearchProvider
  │     └── ExplanationProvider
  │           ├── OpenAICompatibleExplanationProvider
  │           └── RuleBasedExplanationProvider
  ├── GraphService         版本化概念图和 GraphPatch 审批
  └── SettingsService      分用途 API Key 状态（不返回明文）
```

### Provider 边界

- `WISHFORGE_PAPER_API_KEY` 只交给论文检索 Provider；
- `WISHFORGE_EXPLANATION_API_KEY` 只交给解释模型 Provider；
- `WISHFORGE_EXPERIMENT_API_KEY` 预留给未来执行器，本阶段不会使用；
- 外部论文或网页内容是“不可信输入”，不能改变系统提示词、工具权限或 API Key；
- 论文全文只应来自开放来源或用户合法提供的文件。本阶段默认只处理 Semantic Scholar 元数据和摘要。

## 3. API 契约

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/settings/api-keys` | 获取各用途密钥的配置状态和掩码 |
| GET | `/api/v1/projects` | 获取研究项目 |
| POST | `/api/v1/projects` | 创建草稿项目 |
| POST | `/api/v1/analyses` | 创建异步概念分析任务，返回 `202` 和任务 ID |
| GET | `/api/v1/analyses` | 查看最近分析任务摘要 |
| GET | `/api/v1/analyses/{analysis_id}` | 查看状态、阶段进度和完成结果 |
| GET | `/api/v1/graphs` | 获取当前进程中的概念图列表，可按 `project_id` 过滤 |
| GET | `/api/v1/graphs/{graph_id}` | 获取当前概念图和版本号 |
| PATCH | `/api/v1/graphs/{graph_id}` | 修改概念图名称、说明或根节点（带版本检查） |
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
- `warnings` / `novelty_note`：明确说明 Demo、回退和新颖性检索边界。

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

- X、知乎、Reddit 的实时爬取；
- “确保 arXiv 没有相同论文”或任何绝对新颖性承诺；
- 全量 PDF 图表理解和商业数据库的版权内容；
- 真实仪器控制、耗材管理和任意代码执行；
- 多用户权限、团队协作和跨多个概念树的自动合并；
- 服务器重启后仍可恢复的持久化数据库。

社区讨论若在后续接入，应标记为探索性痛点信号；模型脑暴应标记为未验证假设；论文 `Discussion`、`Conclusion`、`Limitations` 和 `Future Work` 应单独保存原文定位，不能与事实证据混成一栏。

## 6. 后续演进路线

1. **持久化层**：SQLite → PostgreSQL，保存 `AnalysisRun`、`Paper`、`Evidence`、`ConceptGraph`、`GraphPatch` 和版本历史。
2. **主张级证据账本**：把解释拆成 Claim/Paragraph，并绑定 `evidence_ids`、原文位置和支持/反驳关系。
3. **多 Agent 研究模式**：社区信号、论文 Future Work、模型假设三个子任务并行，增加 `AgentRun`、预算、超时、局部失败和重试。
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
7. 切换“研究线索”，检查候选和新颖性免责声明。
