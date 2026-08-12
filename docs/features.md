# WishForge / 许愿机：已实现功能说明

> 这份文档描述当前产品已经可以使用的功能、入口、数据边界和验收方式。
> 它和 [`log.md`](../log.md) 的职责不同：`log.md` 记录开发过程、失败实验和提交时间线；本文件只维护“现在有什么、怎么用、能相信到什么程度”。
>
> 文档基线：`main` 的既有功能，加上当前 `codex/research-overview` 分支的图生命周期、真实 Cytoscape 图和可审计 Overview 流水线。Tauri 桌面外壳仍属于后续阶段，不能按本文件当作已完成能力。

## 1. 产品定位

WishForge 是一个面向科研人员的研究工作台。当前第一版的主线是：

```text
模糊概念 / 研究想法
        ↓
范围化检索
        ↓
论文元数据与摘要
        ↓
摘要证据卡
        ↓
易懂解释、演变和原子研究主张
        ↓
主张—证据账本与人工核验
        ↓
概念图、研究候选和实验方案草案
```

当前版本是“摘要级研究助手”，不是自动证明论文结论或创新性的系统。页面、API 和数据结构都会保留这个边界。

## 2. 功能总览

| 功能 | 当前状态 | 主要入口 | 说明 |
| --- | --- | --- | --- |
| 快速概念解释 | 已实现 | 工作台 → 快速解释 | 不检索论文，调用解释模型或规则回退 |
| arXiv 文献解释 | 已实现 | 工作台 → 文献解释 | 首轮检索、摘要反馈检索、证据卡和分层解释 |
| 研究模式 | 有限实现 | 工作台 → 研究线索 | 三路研究 Agent + 综合结果；社区当前主要是 demo/占位 Provider |
| 原子研究主张 | 已实现 | 文献解释结果 | 一条主张只表达一个可核验事实，并绑定论文和证据 |
| 主张—证据账本 | 已实现 | 分析结果 / ledger API | 展示支持关系、覆盖率、强度和下一步核验动作 |
| 人工证据核验 | 已实现 | 账本按钮 / review API | 只能修改审阅元数据，不会改写原文摘要 |
| 想法 prior-art 查重 | 已实现 | 创新与查重页 | L0–L4 范围化相似度、相关工作、替代方向和验证步骤 |
| 概念图与概念树 | 已实现（真实图第一版） | 概念图页 | Cytoscape 圆/椭圆节点、真实连线、缩放、平移、拖拽、节点搜索/类型筛选和 Inspector；多图画布也使用真实图，并继续支持保存、编辑、局部查看、多图比较和 Agent 提案 |
| 概念图保存生命周期 | Phase 1 已实现 | 工作台 / 概念图页 | 分析结果先保存为临时快照，用户确认后进入图库；支持稍后保存、幂等保存和整图删除 |
| 研究方向 Overview | 已实现（有界可审计版） | 文献/研究分析结果 → `Overview / 研究方向图`，或顶部“研究方向图”页 | 方向规划、最多 4 个方向工作器共享 Provider 并行检索、显式 split/keep/merge/discard、开放 arXiv PDF 章节抽取和逐篇摘要降级；异步生成“主题 → 方向 → 细分方向 → 论文叶节点” |
| Agent GraphPatch | 已实现（受限版） | 概念图页 / API | 自然语言只转换成有界提案，必须人工批准或拒绝 |
| 实验方案草案 | 已实现（不执行） | 实验页 / API | 生成并审阅方案，但不会运行代码或实验 |
| API Key 分槽位 | 已实现 | 设置页 / `.env` | 论文、社区、解释模型和实验用途分开配置 |
| 运行时模型代理 | `main` 已实现 | 设置页 / `/settings/runtime` | Provider、模型和 Base URL 只覆盖当前 API 进程 |

## 3. 概念分析模式

### 3.1 快速解释

适合第一次接触一个术语时建立直觉。

- 不访问论文数据源；
- 只执行一次解释调用；
- 返回一句话解释、直观类比、技术解释和相关概念；
- 不生成论文、证据 ID 或伪造引用；
- 没有解释模型 Key 时明确显示规则回退；
- 页面会显示“本次没有检索论文”的范围提醒。

快速模式的结果是知识起点，不应直接当作论文结论。

### 3.2 文献解释

适合建立一个概念的初步研究地图。流程如下：

1. 根据概念生成 2～3 个有边界的检索词；
2. 调用 arXiv 官方 Atom API；
3. 规范化论文 ID、版本、作者、年份、摘要和来源 URL；
4. 从首轮摘要识别方法族、同义词、应用场景和近期术语；
5. 执行第二轮反馈检索；
6. 从摘要句子生成多标签证据卡；
7. 并行生成核心解释、论文批次主张和限制审计；
8. 做引用、数字、论文边界和措辞安全校验；
9. 保存分析快照和证据账本；概念图先以 `transient` 快照嵌入分析，用户确认后才进入已保存图库。

查询计划会保存 `query`、`purpose`、`phase` 和 `derived_from_paper_ids`，因此用户可以看到检索范围是怎样形成的。

### 3.3 研究模式

研究模式在文献解释基础上增加一个有预算的研究线索流程：

- 社区 Agent：整理工程痛点和开放问题；
- 模型脑暴 Agent：生成明确标记为“未验证”的候选；
- 论文 Agent：从摘要中的 limitation / Future Work 线索提取后续方向；
- 综合 Agent：合并候选、来源、风险、可行性和最小验证步骤。

每个 Agent 的运行状态、来源和警告会写入 `ResearchBrief`。社区信号、模型假设和学术证据在页面上分栏展示，不能混成一种证据。

当前研究模式的边界：X、知乎和 Reddit 的实时适配器还没有完成；论文主要来自摘要；“当前范围未发现”不能解释成“全世界没有相同工作”。

## 4. 检索和论文数据

### 4.1 arXiv Provider

默认论文源是 arXiv 官方 Atom API：

```text
https://export.arxiv.org/api/query
```

arXiv 检索不需要 API Key。Provider 会：

- 清理查询文本；
- 限制每次返回数量；
- 对连续请求做约 3 秒节流；
- 解析 Atom XML；
- 忽略 arXiv 错误条目和缺少必要字段的记录；
- 统一 `canonical_id`、版本号和 HTTPS URL；
- 处理网络异常、限流、空结果和 XML 错误；
- 在 Demo 模式下才允许明确标记的演示资料作为回退。

代码中还保留了 Semantic Scholar Provider 作为可选数据源；切换到它时需要相应的论文检索 Key，并需要处理公开接口的限流（例如 HTTP 429）。当前默认配置仍然是 arXiv，因此本轮主流程不依赖 Semantic Scholar。

### 4.2 论文记录

每篇论文保存为 `PaperRecord`，主要字段包括：

- `canonical_id`、`provider_id`、`arxiv_id`、版本号；
- 标题、作者、年份、venue/category；
- 摘要、DOI、来源 URL；
- `source_kind` 和 `access_type`；
- `retrieved_at`。

数据结构允许未来接入 OpenAlex、Crossref、Semantic Scholar 或期刊版本，而不需要重写上层分析结果。

## 5. 证据和主张治理

### 5.1 证据卡

`EvidenceCard` 表示“某篇论文摘要中的哪一句话，可以说明什么”。它保存：

- 论文 ID；
- 摘要原句 `excerpt`；
- 证据主标签和多标签；
- 关系、置信度和来源 URL；
- 摘要定位信息；
- 人工核验状态、审阅人和备注。

目前定位主要是 `abstract`。`page`、`section`、`figure`、`table` 等字段已经为 PDF 全文阶段预留。

### 5.2 原子主张

`AtomicClaimDraft` 把长段落拆成独立事实。每条主张包含：

- `claim_type`：定义、机制或结果；
- 主张文本；
- 论文 ID；
- 证据 ID；
- 一至数条摘要原文引用；
- 适用范围。

系统会拒绝或要求拆分混合多个主要操作的句子，例如同时“预测、聚类、量化和提升准确率”的复合句。数值结果也必须单独作为 result 主张，不能藏在机制描述里。

### 5.3 安全校验

论文特定主张的证据必须满足：

- 只能来自声明的同一篇论文；
- `evidence_quotes` 必须原样命中对应摘要；
- 主张中的数字必须出现在证据句中；
- 不允许跨论文拼接方法、数字和限制；
- 不允许自行换算百分比、倍数、差值或单位含义；
- 摘要没有直接支持时，`first`、`best`、`lossless`、`guarantee` 等强措辞会被弱化；
- 无法建立安全关系时保留为无链接主张，而不是伪造支持。

### 5.4 主张—证据账本

账本由 `ClaimRecord`、`ClaimEvidenceLink` 和 `EvidenceLedger` 组成。它记录：

- 主张文本、类型、范围和状态；
- 证据关系：`supports`、`qualifies`、`contradicts`、`background`；
- 匹配强度、匹配分数和匹配词；
- 自动匹配或模型引用的来源；
- 人工核验状态；
- linked、unlinked、direct support 和 verified coverage 等指标。

“有摘要证据”与“已人工核验”是两件事。自动 `strong` 只表示匹配条件较好，不表示论文质量高，也不表示全文已经确认。

## 6. 研究限制、研究空白和复现检查

系统将三类结果分开保存：

### 研究限制

必须说明目标对象、条件和具体后果，例如方法在某个上下文或评估条件下失败、退化、增加代价或不适用。

### 研究空白

只能写成当前检索范围内的候选，例如“本次检索到的摘要没有看到系统性研究，仍需扩大范围验证”。不能据此声称全球没有相关工作。

### 复现检查

保存代码、数据、环境、许可证和基准是否可获得等工程核验任务。它不是论文方法局限。

限制候选会经过 `limitation`、`research_gap` 或 `reject` 审计。格式错误的可选字段不会抹掉已经得到的安全裁决，系统会保留修复记录和范围警告。

## 7. 想法查重和创新候选

### 7.1 Prior-art 查重

在“创新与查重”页面输入一个研究想法后，系统会返回：

- 实际搜索范围和搜索词；
- 最相关论文；
- 摘要级易懂说明；
- L0～L4 相似度分级；
- 当前相似理由；
- 可能差异；
- 替代想法；
- 最小验证步骤；
- 人工核验状态。

分级含义：

| 等级 | 含义 |
| --- | --- |
| L0 | 直接已有工作 |
| L1 | 核心方法高度相似 |
| L2 | 组件或组合相似 |
| L3 | 问题相近但机制不同 |
| L4 | 当前检索范围未发现直接等价工作 |

L4 只是一个范围化检索结论，不是原创性保证。查重结果可以写入人工审阅状态和备注。

### 7.2 创新候选

研究 Agent 或跨图比较会生成 `InnovationCandidate`。候选包含：

- 问题和机制；
- 最近工作；
- 新颖性等级和置信度；
- 可行性；
- 产生理由；
- 验证步骤；
- 风险警告；
- arXiv 范围状态。

候选默认是未验证假设，页面会要求先查相关论文、读全文和做最小实验。

## 8. 概念图和 GraphPatch

概念图由节点和边组成，节点可以关联摘要证据。当前支持：

- 分析完成后生成概念图快照；默认状态是 `transient`，不会自动出现在已保存图库；
- 分析完成后前端显示保存 Action Sheet，默认推荐“保存概念图”；选择“暂不保存”不会删除历史分析中的快照；
- 从历史分析结果再次点击“保存为概念图”可以稍后保存；同一分析图使用稳定 ID，重复保存不会生成重复记录；
- 手工创建或导入概念图；
- 已保存图和分析历史中的临时图都可以修改图名、描述、根节点、节点和边；临时图使用独立的 `analysis_graph_patches` 审计记录，用户修改立即按版本应用，Agent 修改与节点解释仍需批准；
- 选择多棵图并排查看；
- 按节点 ID 生成不落库的局部视图；
- 比较多棵图并生成跨领域候选；
- 请求 Agent 为节点生成解释。

所有 Agent 修改都通过 `GraphPatch`：

1. 接收自然语言修改需求；
2. 转换为最多 4 个受限操作；
3. 保存为 `actor=agent`、`status=proposed` 的提案；
4. 用户查看操作和警告；
5. 用户调用 apply 或 reject；
6. 服务端检查图谱版本，避免旧提案覆盖新内容。

### 8.1 临时图与已保存图的生命周期

分析结果中的图与图库中的图是两个有意区分的状态：

```text
分析完成
   │
   ▼
transient 图快照（保留在 analysis_jobs.result.graph）
   │  用户选择保存
   ▼
saved 图（写入 concept_graphs，可编辑、可列出、可删除）
```

Phase 1 的接口如下：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/v1/analyses/{analysis_id}/graph` | 读取分析中的临时或已保存快照 |
| PATCH | `/api/v1/analyses/{analysis_id}/graph` | 在分析历史中修改图名、说明或根节点；不会自动保存到图库 |
| POST | `/api/v1/analyses/{analysis_id}/graph/save` | 使用版本 CAS 将快照提升为已保存图；重复调用幂等 |
| DELETE | `/api/v1/graphs/{graph_id}?expected_version=...` | 删除整张已保存图和级联 GraphPatch；历史分析快照保留并回到 `transient` |

`GET /api/v1/graphs` 只列出 `saved` 图。删除图不会删除 `analysis_jobs`、`overview_jobs`、论文、证据账本或历史结果；关联的分析或 Overview 快照会回到 `transient`，用户以后仍可重新保存。临时图已经支持用户修改以及 Agent `proposed → apply/reject` 的完整 GraphPatch 审批。图修改在完整 Patch 应用后检查所有节点是否仍与根节点连通；新增节点必须在同一 Patch 中同时建立关系边，删除唯一连接边会被拒绝，避免编辑后出现没有上下文的孤立圆点。

### 8.2 当前边界

当前概念图已经使用本地 npm 依赖中的 Cytoscape.js 渲染：节点是圆形/椭圆形，边是真实连线，并支持缩放、平移、拖拽、fit、低置信边开关和节点详情 Inspector。老图仍使用兼容字段读取，不会因为缺少新视觉字段而失效。

没有保存坐标的新图使用实际布局算法；`x/y=null` 不会再被误当作 `(0,0)` 的 preset 坐标，因此初次打开时节点不会叠成一个圆。图画布可获得键盘焦点，方向键循环选择可见节点，Enter/空格打开 Inspector；同时保留鼠标、触控板缩放、平移和拖拽。

研究方向 Overview 已经可用：完成文献解释或研究线索分析后，点击 `Overview / 研究方向图` 启动异步任务；结果按“主题 → 一级方向 → 细分方向 → 论文叶节点”组织。方向规划器给出定义、边界与专属检索词，方向工作器共享同一个论文 Provider 和限流器并最多并发 4 个，细分审查会记录 `split / keep / merge / discard`。每个方向还会保存结构化审计（查询范围、返回/接纳/拒绝/截断数、决策和错误）；单方向失败不会抹掉其他结果，任务会标为 `partial`，前端允许只重试失败方向。点击方向继续展开时会在可安全重建 Provider 的前提下再次执行方向专属检索。论文节点包含问题、方法、怎么做、年份、来源和真实阅读范围；开放 arXiv PDF 可抽取 Introduction、Method、Experiment、Discussion、Conclusion，章节短摘录以未核验 EvidenceCard 保存，失败或无全文时逐篇回退 `abstract_only`。Overview 任务持久化在 SQLite 中，`GET /api/v1/overviews` 支持应用重启后恢复历史任务；保存到统一图库后，节点 Inspector 仍可通过 `generation_id` 恢复 Overview 独有的 PDF 章节证据。

Overview 使用混合 Agent 编排：配置了解释模型 Key 时，`TopicTaxonomyPlannerAgent` 和 `OverviewSynthesisAgent` 会进行独立的结构化模型调用；每个方向的检索工作器并行运行，共享论文 Provider 与限流器。模型输出仍需经过 ID、边界、数量和图结构校验。没有解释模型 Key、模型调用失败或输出不合格时，会明确记录 `deterministic_rule_fallback` 并使用可审计规则，不能伪装成模型调用。分类、章节边界和摘录仍需研究者核验。arXiv 与 Demo Provider 可以在后台安全重建并执行方向级检索；需要论文专用 Key 的 Provider 当前会诚实退回原分析论文，而不会借用解释或实验 Key。PDF 文本层由 `pypdf` 处理（失败时可尝试本机 `pdftotext`），不做 OCR，也不虚构页码。当前仍不提供完整引用/共引网络，Tauri 桌面壳属于后续阶段。

每次 Overview 还会在 `result.agent_runs` 中保存结构化、无密钥的运行审计：角色、执行模式、Provider、真实模型名（仅模型调用）、状态、起止时间、耗时、输入/输出计数、方向和错误类型。规划、方向协调与每个方向工作器、论文读取、验证、综合，以及按需展开/局部重试都有记录；模型失败和规则回退是两条不同记录。审计不会保存 API Key、Authorization、Base URL、Prompt、原始模型响应或上游错误正文。

设置页中的解释模型 Key、模型名和代理 URL 是当前进程内配置；创建 Overview 时会把这份实时配置安全传给后台任务，但不会把 Key 序列化到 SQLite、结果 JSON 或日志。也就是说，配置后新建的研究方向图会使用该解释模型槽位；论文检索、社区和实验槽位不会被借用。

临时概念图也可直接编辑：用户手动节点修改会立即以版本化 Patch 应用，Agent 自然语言修改与节点解释仍先进入待审核列表。保存前这些 Patch 写入 `analysis_graph_patches`，不会让临时图偷偷进入图库。已保存图支持节点详情接口和手动布局持久化。

用户自己的手动修改可以立即应用。自然语言翻译在当前版本使用透明的有界启发式规则，不允许直接提交任意字段、删除根节点或绕过版本检查。

## 9. 实验方案草案

实验页可以从自由文本、创新候选或 prior-art 结果生成结构化草案，包括：

- 假设；
- 基线；
- 自变量和控制变量；
- 评价指标；
- 消融实验；
- 预期结果；
- 失败判据；
- 资源估计；
- 证据来源。

草案可以保存、读取和人工批准/退回/拒绝。当前接口只管理研究计划，不执行代码、模型训练或实验任务；`execution_status` 会保持 `not_started`。

## 10. 配置、密钥和代理

### 10.1 独立密钥槽位

系统将不同用途分开：

- `WISHFORGE_PAPER_API_KEY`：论文检索；
- `WISHFORGE_COMMUNITY_API_KEY`：社区检索；
- `WISHFORGE_EXPLANATION_API_KEY`：解释模型；
- `WISHFORGE_EXPERIMENT_API_KEY`：实验执行。

arXiv Provider 默认不需要论文 Key。解释模型使用 OpenAI-compatible 接口。

常用的非密钥配置包括：

- `WISHFORGE_PAPER_PROVIDER`：默认 `arxiv`，也可选择已实现的其他 Provider；
- `WISHFORGE_COMMUNITY_PROVIDER`：当前默认 `demo`；
- `WISHFORGE_EXPLANATION_PROVIDER`、`WISHFORGE_EXPLANATION_MODEL`；
- `WISHFORGE_EXPLANATION_BASE_URL`、`WISHFORGE_EXPLANATION_TIMEOUT_SECONDS`；
- `WISHFORGE_EXPERIMENT_PROVIDER`、`WISHFORGE_DEMO_MODE`；
- `WISHFORGE_STORAGE_PATH`、`WISHFORGE_CORS_ORIGINS`。

`.env` 固定从仓库根目录加载，不依赖启动时的当前目录。

网页上的 Key：

- 只返回已配置状态和掩码；
- 当前版本只保存在 API 进程内存；
- 重启后清除；
- 不写入 SQLite、日志或响应正文；
- 当前没有登录和权限系统，只适合本机或受保护内网。

### 10.2 运行时解释模型代理

`main` 的 `df9411c` 增加了非敏感运行时设置：

```text
GET   /api/v1/settings/runtime
PATCH /api/v1/settings/runtime
```

可以配置：

- explanation provider；
- 模型名称；
- OpenAI-compatible Base URL；
- Demo 状态。

代理地址填写到 `/v1` 这一层，例如：

```text
https://proxy.example.com/v1
```

后端会请求 `/chat/completions`。该接口不接收 API Key；Key 仍然通过独立的 `/settings/api-keys` 配置。网页修改只覆盖当前进程，长期部署请写入后端 `.env` 或 Secret Manager。

这两个 runtime endpoint 已随 `df9411c` 合入 `main`。开发分支在合并前曾不包含它们，因此如果单独检出旧的功能分支提交，需要以 `main` 的合并结果为准。

## 11. 前端、后端和持久化

### 前端页面

当前 Web 控制台分为：

- 工作台：概念分析和结果；
- 概念图：真实关系图、节点 Inspector、Patch 审核和多图视图；
- 研究方向图：异步 Overview 状态、方向/论文图、按需展开与保存；
- 创新与查重：prior-art 和研究候选；
- 实验：实验方案草案和人工审阅；
- 设置：后端连接、Provider 状态和密钥槽位。

前端已经切换到 Vite 构建。`npm run dev` 在 1420 端口运行并代理本地 FastAPI，`npm run build` 生成 `frontend/dist`；FastAPI 检测到构建产物后会优先托管它。本分支仍是浏览器/本地 Web 壳，Windows Tauri sidecar 尚未完成。

仓库提供 `frontend/smoke-browser.mjs` 和 `npm run smoke:browser` 进行 Chrome 级交互验收，覆盖 Overview 历史恢复、Cytoscape 节点点击、Inspector、边开关、连续发起分析、保存弹窗默认焦点和暂不保存语义。运行时必须让专用 FastAPI 服务使用临时 `WISHFORGE_STORAGE_PATH`，并显式传入 `WISHFORGE_OVERVIEW_ID`；不要连接日常使用的 SQLite 数据库。

### 后端

FastAPI API 统一挂载在 `/api/v1`。主要资源包括：

| 资源 | 主要接口 |
| --- | --- |
| 分析 | `POST/GET /analyses`、`GET /analyses/{id}` |
| Research Brief | `GET /analyses/{id}/research-brief` |
| 证据账本 | `GET /analyses/{id}/evidence-ledger`、账本 review PATCH |
| 想法查重 | `POST /ideas/check`、`GET /ideas/checks`、review |
| 实验草案 | `POST/GET /experiments/plans`、review |
| 概念图 | `POST/GET/PATCH /graphs`、compare、subset |
| GraphPatch | 创建、Agent 提议、列表、apply、reject |
| 设置 | `GET/PATCH /settings/api-keys`；`main` 已提供 runtime 设置 |

常见响应边界：创建分析通常返回 `202 Accepted`，创建项目、图谱或实验草案返回 `201 Created`；不存在的资源返回 `404`，图谱版本冲突返回 `409`，请求字段不合法返回 `422`，Provider 不可用时返回 `503`。具体响应以 `/docs` 中的 OpenAPI 为准。

### 存储

分析、项目、概念图、GraphPatch、想法查重和实验方案保存到 SQLite。服务重启后可以读取已保存结果。模型调用追踪不保存 Authorization 或 API Key。

## 12. 运行和验收

在仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
$env:PYTHONPATH = "backend"
python -m uvicorn app.main:app --reload
```

日常回归可以使用 mock provider、固定响应和本地 XML，不消耗真实 Key：

```powershell
python -m pytest backend/tests -q
node --check frontend/app.js
git diff --check
```

当前这条开发分支的最后一次完整后端回归为 96 项通过，前端 JavaScript 语法检查和 Git 空白检查也通过。

Windows 验收时建议先确认 8000 端口没有旧的 Uvicorn parent/reloader/spawn 进程，并优先使用单进程启动，避免页面仍返回旧服务的数据结构。

## 13. 明确尚未实现或不能保证的能力

以下内容不能从当前版本的结果中推断出来：

- PDF 全文 Method、Experiment、Discussion 和页码级证据；
- Connected Papers 式引用、共引、bibliographic coupling 或嵌入网络；
- X、知乎、Reddit 的真实实时适配器；
- 对全球论文、期刊、专利、非英文论文和工业报告的完整查重；
- “arXiv 没搜到”到“世界上没有相同工作”的推理；
- 自动判断创新性并替代研究者；
- 自动执行代码、训练模型或提交实验；
- 面向公网的账号、权限和生产级密钥托管。

## 14. 与开发日志的维护规则

以后每次新增功能时：

1. 在本文件对应功能表和章节中更新“已实现功能”；
2. 写清楚页面入口、API 入口、数据是否持久化和证据边界；
3. 如果能力只有 demo、规则回退或摘要级支持，必须标注“有限实现”；
4. 在 `log.md` 记录实现过程、失败实验、提交和测试细节；
5. 功能文档只描述合入后的可用状态，不把候选方案写成已实现能力；
6. 合并前重新运行后端测试、前端语法检查和 `git diff --check`。
