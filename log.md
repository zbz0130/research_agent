# WishForge 本轮开发日志

> 本文档记录从项目原始版本到当前开发分支的一整轮实现、问题定位、架构调整、测试验证和运行经验。它既是开发日志，也是后续协作时的交接文档与验收依据。

## 0. 版本信息与结论摘要

| 项目 | 内容 |
| --- | --- |
| 项目名称 | WishForge / 许愿机 |
| 仓库 | zbz0130/research_agent |
| 开发日期 | 2026-08-10 至 2026-08-11 |
| 基准分支 | main |
| 当前开发分支 | codex/iterative-retrieval-atomic-claims |
| 写日志前的最新功能提交 | c5ea2f5 feat: improve evidence-backed literature analysis |
| main 是否被直接修改 | 否 |
| 本轮功能提交数量 | 8 个 |
| 相对 main 的功能改动规模 | 21 个文件，新增 4,278 行，删除 265 行 |
| 最终自动化回归 | 96 passed |
| 前端语法检查 | 通过 |
| Git 空白检查 | 通过 |

这一轮已经把原本偏演示性质的“概念分析”，推进成了一个可以实际检索 arXiv、阅读论文摘要、生成分层解释、抽取原子主张、建立主张—证据关系、审计研究限制并接受人工核验的研究工作流。

最重要的变化不是“多展示了几篇论文”，而是系统的数据流已经变成：

1. 先理解用户概念并规划检索词；
2. 使用 arXiv 官方接口检索真实论文；
3. 阅读第一轮论文摘要后再次生成反馈检索词；
4. 从摘要中抽取可追溯的证据句；
5. 将模型调用拆成核心解释、分批论文主张和限制审计；
6. 对模型生成的每条主张进行原子性、数字、强措辞和原文引用校验；
7. 只在相同论文、数字相符和语义可解释的条件下建立证据链接；
8. 将“摘要支持”与“人工核验”明确区分；
9. 将真正的研究限制、研究空白、复现检查和普通背景问题拆开；
10. 在前端显示检索过程、论文卡、解释、演变、证据账本、修复记录和人工核验入口。

本轮仍然没有把系统包装成“已经证明创新性”的工具。当前系统主要读取 arXiv 元数据和摘要，不能把摘要支持等同于全文结论，也不能保证全世界不存在相同创新点。所有这类边界都在数据结构、提示词和界面文案中被显式保留。

---

## 1. 原始目标、协作规则与本轮范围

### 1.1 长期产品目标

项目长期目标是帮助研究者完成两类工作。

第一类是概念分析：

- 从一个研究概念出发进行多层次解释；
- 检索并梳理相关论文；
- 阅读论文摘要并形成概念演变；
- 从论文、社区讨论和模型推理中发现问题；
- 形成可以继续验证的创新候选。

第二类是创新点判断：

- 输入一个想法；
- 检索是否已有相同或相近论文；
- 解释已有工作如何实现；
- 总结已有工作的边界；
- 以当前想法为起点生成其他创新方向；
- 通过后续检索降低重复造轮子的风险。

长期规划还包括概念树、概念图、节点编辑工具、多个概念树组合展示、跨概念迁移、社区检索、多智能体并行分析和创新点查重。

### 1.2 本轮批准的优先范围

本轮首先聚焦两个能力：

1. 直接调用解释模型，对用户输入概念给出容易理解的说明；
2. 检索 arXiv 相关论文，阅读摘要，给出概念解释、相关概念、发展演变和证据化主张。

在初版能够运行后，根据真实测试继续加入：

- 反馈检索；
- 原子主张；
- 研究限制审计；
- 主张—证据账本；
- 人工核验；
- 模型输出容错；
- 分批、并行模型调用；
- 真实阶段耗时与诊断记录；
- Windows 环境变量和服务进程问题修复。

### 1.3 协作约束

本轮始终遵循以下规则：

- 不直接在 main 上开发；
- 所有实现均位于 codex/iterative-retrieval-atomic-claims 分支；
- push 时明确告知协作者；
- 不将 API Key 写入 Git；
- 不把演示数据伪装成真实检索结果；
- 不把规则回退内容伪装成模型生成内容；
- 不把摘要证据伪装成全文或人工核验结论。

---

## 2. 开发前的主要问题

### 2.1 项目启动路径不清晰

最初在 D:\agent 直接安装 backend\requirements.txt 会报文件不存在，因为仓库实际位于 D:\agent\research_agent。虚拟环境虽然已经激活，但依赖并没有成功安装，于是随后出现 No module named uvicorn。

根因是：

- 当前工作目录不在仓库根目录；
- requirements.txt 的相对路径无效；
- 前一步安装失败后仍继续启动；
- 虚拟环境中自然没有 Uvicorn。

### 2.2 环境变量随启动目录变化而失效

原配置使用相对路径读取 .env。从 backend 目录启动时，相对路径指向错误位置，导致：

- 页面提示未配置解释模型 API Key；
- 系统进入规则回退解释；
- arXiv 或模型配置状态与实际 .env 不一致。

### 2.3 初版文献解释过度依赖一个长模型调用

早期流程接近：

1. 模型生成一段长解释；
2. 把长解释中的句子当作主张；
3. 再尝试从摘要中寻找支持这些主张的证据。

这会造成：

- 主张不够原子，一句话同时包含多个机制、条件和结果；
- 模型生成的数字、范围或强措辞未必存在于摘要；
- 证据匹配退化为“主题看起来相似”；
- 任意字段格式错误都可能使整次解释失效；
- “限制”容易变成泛泛背景问题；
- 一次长调用响应很慢，失败后也没有局部恢复能力。

### 2.4 检索只围绕用户原始输入

如果用户输入 KV cache 压缩，只搜索这个词，会遗漏：

- eviction；
- token pruning；
- quantization；
- low-rank / latent；
- reasoning model 场景；
- agentic coding 场景。

论文摘要中的术语往往比用户输入更适合继续检索，因此需要“先检索、再读摘要、再检索”的反馈环。

### 2.5 限制类别混入低质量内容

早期限制类主张出现过：

- 当前只读取摘要，需要人工核验；
- KV cache 会消耗显存；
- 方法存在 tradeoff，但没有负面后果；
- 单纯的方法描述或结果句；
- 系统数据边界被误写成论文研究限制。

这些内容分别属于产品告警、领域背景、无效候选或复现检查，不能放进“当前研究的局限性”。

### 2.6 旧开发服务进程造成“代码改了但页面没变”

Windows 下使用 Uvicorn --reload 时，父进程、重载进程和 multiprocessing spawn 子进程可能没有同时退出：

- 端口 8000 继续被旧子进程占用；
- 新进程启动失败或没有接管端口；
- 浏览器看似运行最新版本，实际返回旧数据结构；
- 开发者误以为修复没有生效。

后来通过检查监听端口、父子进程、OpenAPI 字段和实际响应解决。验收阶段改用单进程 Uvicorn，避免热重载残留进程干扰判断。

---

## 3. 最终端到端流程

    用户输入概念
          |
          v
    模式判断：快速解释 / arXiv 文献解释 / 研究模式
          |
          +---------------------- 快速解释 ----------------------+
          |                                                     |
          |                                             单次模型解释
          |                                                     |
          |                                             不生成虚假论文
          |
          +---------------------- 文献解释 ----------------------+
                                |
                                v
                         初始检索词规划
                                |
                                v
                       arXiv 第一轮真实检索
                                |
                                v
                    合并、规范化、去重论文记录
                                |
                                v
                      摘要反馈检索词规划
                        /              \
                   模型成功          规则回退
                        \              /
                                v
                       arXiv 第二轮补充检索
                                |
                                v
                     摘要证据句与多标签抽取
                                |
                 +--------------+--------------+
                 |              |              |
                 v              v              v
             核心解释       分批论文主张       限制候选审计
                 |              |              |
                 +--------------+--------------+
                                |
                                v
                    模型输出修复与安全后处理
                                |
                                v
                   主张—证据匹配与证据账本
                                |
                                v
                 前端展示、人工核验、研究问题保存

最终设计遵循五个原则：

1. 来源优先：论文、证据、链接和检索时间必须可追溯；
2. 证据与结论分离：论文摘要、模型主张、匹配关系和人工核验是四层不同事实；
3. 局部失败隔离：一个论文批次或可选字段失败，不应抹掉整个分析；
4. 明确回退：规则回退必须标记，不能伪装成模型输出；
5. 保守表达：摘要不支持的数字、强措辞、全球性结论和创新性保证不得保留。

---

## 4. Git 提交时间线

本轮相对 main 共有 8 个功能提交。

### 4.1 8fde746 — feat: add arxiv concept analysis

建立第一版真实 arXiv 概念分析：

- 新增 arXiv 检索适配器；
- 增加论文记录结构；
- 增加快速解释和文献解释模式；
- 接入 OpenAI 兼容解释模型；
- 前端显示论文和解释结果；
- 增加基础测试和环境变量示例；
- 更新 README、架构文档和容器配置。

该提交解决“系统是否真正查询论文”的基础问题。

### 4.2 090024a — feat: improve research evidence quality and result UX

- 从摘要中抽取证据句；
- 丰富论文卡元数据；
- 增加检索计划、阶段状态和耗时；
- 改善长页面布局；
- 显示完整摘要、证据类型和来源；
- 区分演示来源和真实学术来源。

该提交让结果从论文列表变成带来源的研究资料。

### 4.3 d5d13c2 — feat: add feedback retrieval and atomic research claims

- 第一轮检索后阅读摘要；
- 根据摘要生成第二轮查询；
- 反馈模型失败时用可追溯规则补充；
- 让模型生成结构化原子主张；
- 对主张进行原子性检查；
- 记录主张对应的论文和证据引用。

该提交改变检索策略，也首次解决“长解释不能直接当主张”的问题。

### 4.4 5068947 — fix: preserve valid model output on schema drift

- 核心解释严格校验；
- 可选数组逐项校验；
- 常见字段别名自动修复；
- 单个无效主张、研究空白或复现检查单独丢弃；
- 其他有效内容继续保留；
- 修复行为写入用户可见告警。

该提交把全有或全无的解析改成保留确定有效的部分。

### 4.5 fe908a7 — feat: make evidence links auditable and reviewable

- 每条主张成为独立 ClaimRecord；
- 主张与 EvidenceCard 通过 ClaimEvidenceLink 关联；
- 记录关系、强度、分数、匹配词、来源和核验状态；
- 增加 evidence ledger 查询接口；
- 增加人工核验接口；
- 前端加入支持、有条件、反驳和仅背景按钮；
- 重新计算覆盖率和人工核验指标。

该提交将自动判断变成可检查、可纠正的数据对象。

### 4.6 68aee02 — fix: load environment from project root

- 使用配置文件位置推导项目根目录；
- 固定从项目根目录 .env 加载；
- 不再依赖当前 PowerShell 目录；
- 保留 WISHFORGE_ 环境变量前缀。

该提交解决“明明写了 Key，服务却提示没配置”。

### 4.7 3d5481c — refactor: split literature explanation model calls

- 核心解释独立调用；
- 论文主张按批独立调用；
- 限制审计独立调用；
- 多个调用并行执行；
- 记录每个子调用的耗时、状态、字段和项目数；
- 单个辅助调用失败时保留其他结果。

拆分首先服务于故障隔离和结构稳定，其次才是延迟优化。

### 4.8 c5ea2f5 — feat: improve evidence-backed literature analysis

- 每批主张必须覆盖指定论文；
- 机制与结果进一步原子化；
- 引用必须原样存在于对应论文摘要；
- 数字不一致时拒绝建立直接证据链接；
- 强措辞缺少原文支持时自动弱化；
- 限制审计覆盖所有候选；
- 研究限制、研究空白、复现检查明确分离；
- 对模型已判定的有效研究空白增加安全恢复；
- 补充高密度测试。

这是本轮证据质量治理的收尾提交。

---

## 5. arXiv 检索适配器

### 5.1 数据源

系统调用 arXiv 官方 Atom API：

    https://export.arxiv.org/api/query

arXiv 适配器不需要单独 API Key。

### 5.2 查询规划

模型优先生成 2 至 3 个有边界的英文短语，而不是把整段中文问题直接交给 arXiv。

每个 SearchQueryPlan 包含：

- query：实际检索词；
- purpose：核心方法、奠基论文、近期方向等目的；
- phase：initial 或 feedback；
- derived_from_paper_ids：反馈查询来自哪些第一轮论文。

### 5.3 论文记录

每篇论文规范化为 PaperRecord，包含：

- provider_id；
- canonical_id；
- arxiv_id；
- arxiv_version；
- title；
- authors；
- year；
- venue / category；
- abstract；
- source_url；
- doi；
- access_type；
- retrieved_at。

### 5.4 去重

多轮、多关键词可能重复命中同一论文。系统按以下优先级合并：

1. canonical ID；
2. DOI；
3. provider ID / arXiv ID；
4. 规范化标题。

### 5.5 节流和错误处理

连续 arXiv 请求保留至少约 3 秒间隔，减少公开接口压力。测试使用可注入时钟，不执行真实等待。

系统显式处理：

- 网络异常；
- 非法 Atom XML；
- 空结果；
- 限流；
- 单条元数据不完整；
- 模型生成无效查询。

真实检索失败时显示数据源错误，不自动把演示论文伪装成 arXiv 结果。

---

## 6. 解释模式

### 6.1 快速解释

快速解释用于先建立直觉：

- 不检索论文；
- 只调用一次解释模型；
- 生成一句话、直观和技术解释；
- 可给出相关概念；
- 不生成虚假论文；
- 模型未配置时明确显示规则回退。

### 6.2 arXiv 文献解释

文献解释用于从摘要证据建立初步研究地图：

- 规划查询；
- 查询真实 arXiv；
- 对第一轮摘要进行反馈检索；
- 抽取摘要证据；
- 生成解释、演变、主张、限制和研究空白；
- 建立证据账本；
- 显示范围和核验状态。

### 6.3 研究模式边界

当前研究模式建立在文献解释之上，但真实社区平台检索、全文 Discussion 抽取和创新点全网查重仍属于后续工作。任何界面和服务端文案都不应暗示这些能力已经完成。

---

## 7. 初始检索与反馈检索

### 7.1 初始检索要求

查询需要：

- 简短；
- 适合 arXiv；
- 避免完整自然语言问句；
- 兼顾核心主题、方法家族、奠基或近期工作；
- 避免生成无法从用户概念解释的无关词。

### 7.2 反馈检索

第一轮论文返回后，模型读取标题和摘要，再决定是否补充：

- 方法家族；
- 应用场景；
- 奠基术语；
- 新近术语；
- 第一轮暴露但原始输入没有包含的专业词。

反馈查询记录 derived_from_paper_ids，因此可以回答“这个词为什么被搜索”。

### 7.3 规则回退

如果摘要反馈模型没有返回可用查询，系统从可见标题和摘要中选择可追溯术语：

| 摘要线索 | 规则补充查询 |
| --- | --- |
| eviction | KV cache eviction |
| pruning / critical token | KV cache token pruning |
| quantization | KV cache quantization |
| low-rank / latent | low rank KV cache |
| reasoning | KV cache reasoning models |
| code + agent | KV cache agentic coding |

页面提示“摘要反馈模型未生成可用查询，已使用可追溯关键词规则补充检索词”只表示第二轮查询规划用了规则，不表示：

- 核心解释失败；
- arXiv 检索失败；
- 所有模型调用失败；
- 结果使用演示数据。

---

## 8. 论文证据卡

EvidenceCard 表示“摘要里的哪一句话能够提供什么信息”。

### 8.1 字段

- evidence_id；
- paper_id；
- claim；
- excerpt：摘要原句；
- evidence_type：主要类型；
- evidence_types：全部适用类型；
- locator；
- relation；
- confidence；
- verification_status；
- reviewed_by；
- reviewed_at；
- review_note；
- source_url。

### 8.2 多标签

一条句子可以同时描述机制并报告结果，因此允许：

- definition；
- mechanism；
- result；
- limitation；
- future_work；
- context。

evidence_type 保留主标签以兼容旧结构，evidence_types 保存完整多标签。

### 8.3 位置

当前证据主要来自摘要，locator 通常记录：

- kind = abstract；
- source URL；
- 可选段落或句子位置。

结构已经预留 page、section、figure、table、paragraph，后续接入 PDF 全文时不需要重写上层账本。

### 8.4 “有证据”和“已核验”

有证据表示系统找到了能够与主张建立关系的摘要原句。

已核验表示人类研究者明确审阅过该关系。

所以：

- 摘要原句存在，不等于全文结论已验证；
- 自动匹配，不等于人工确认；
- 没有人工核验时 verified coverage 保持 0；
- low 可能只是尚未核验，不代表论文质量差。

---

## 9. 模型调用拆分

### 9.1 为什么拆

一个长调用同时生成所有字段会导致：

- JSON 太长容易截断；
- 一处格式异常污染全部结果；
- 多篇论文的主张互相串线；
- 无法判断慢在核心解释、论文主张还是限制分析。

### 9.2 当前子调用

1. 核心解释：
   - one_sentence；
   - intuitive；
   - technical；
   - related_concepts；
   - scope_warnings。
2. 论文主张和演变：
   - 每批最多 2 篇论文；
   - 6 篇通常产生 3 个批次；
   - 每篇必须有一个演变项；
   - 每篇产生 1 至 3 条原子主张。
3. 限制审计：
   - 输入全部 limitation / future-work 候选；
   - 每个候选必须得到 limitation、research_gap 或 reject 决策。

子调用并行运行，使用有界线程池限制并发。

### 9.3 故障隔离

- 核心失败：进入安全回退；
- 某个主张批次失败：保留其他批次；
- 限制审计失败：保留核心解释和可验证主张；
- 单个可选对象非法：只丢弃该对象；
- 修复与丢弃写入 warning。

### 9.4 ModelCallTrace

每个子调用记录：

- part；
- status；
- duration_ms；
- returned_fields；
- item_counts；
- message。

追踪不保存 API Key、Authorization 或敏感请求。当前数据保存在 ExplanationResult，可通过接口和持久化结果检查；前端还没有完整专用诊断面板。

### 9.5 真实耗时

最近一次真实成功运行：

| 子调用 | 耗时 |
| --- | ---: |
| core explanation | 5,860 ms |
| limitation audit | 39,328 ms |
| claim batch 1 | 135,707 ms |
| claim batch 2 | 61,754 ms |
| claim batch 3 | 118,189 ms |
| 整体分析 | 205.111 s |

批次并行，因此整体耗时不是简单相加。DeepSeek 响应存在波动，拆分的首要收益是：

- 容易定位慢点；
- 单批失败不拖垮全部；
- 未来可只重试失败批次；
- 未来可按批缓存。

不能承诺拆分后每次绝对更快。真实运行出现过约 174 秒到 205 秒的差异。

---

## 10. 原子主张与安全校验

### 10.1 AtomicClaimDraft

包含：

- claim_type；
- text；
- paper_ids；
- evidence_ids；
- evidence_quotes；
- scope。

### 10.2 原子性

一条机制主张主要描述一个操作。

合格：

- 该方法根据注意力模式预测需要保留的 KV token。
- 该方法将低重要度 KV token 量化到更低位宽。

不合格：

- 该方法预测 token、执行聚类、量化 KV，并在多个基准上提升准确率。

数值结果应拆成独立 result 主张。

### 10.3 操作家族检查

后处理识别一句话是否混入多个主要操作：

- quantize；
- compress；
- evict；
- prune；
- retain；
- select；
- predict；
- cluster；
- merge；
- project；
- discard；
- reduce；
- share；
- reorder；
- calibrate；
- factor / SVD；
- threshold；
- protect。

混入多个独立操作时，系统拒绝或要求更原子的输出。

### 10.4 论文边界

论文特定机制和结果原则上只绑定一篇论文，避免把 A 论文的方法、B 论文的数字和 C 论文的限制拼成一条不存在的结论。

### 10.5 原文引用

模型必须提供完整摘要句作为 evidence_quotes。系统确认：

- 引用是否原样存在于对应摘要；
- 是否来自声明论文；
- 是否为完整可定位文本；
- 是否包含主张关键数字；
- 是否真正解释主张，而非仅共享主题词。

模型写出的 evidence_id 只是提示，不能绕过校验。

### 10.6 数字保护

主张包含 2%、1.5 倍、32K、8-bit 等数字时，证据句必须包含对应数字。系统禁止：

- 把 2% loss 转写成 98% accuracy；
- 自行计算倒数、提升比例或差值；
- 将一个数据集结果推广到全部场景；
- 用另一论文的相似数字替代。

### 10.7 强措辞弱化

以下措辞只有摘要原句直接支持时才能保留：

- first；
- best；
- optimal；
- lossless；
- guarantee；
- state of the art；
- 完全解决；
- 全面优于；
- 首次证明。

缺少支持时自动改成更保守表达。

---

## 11. 演变时间线

演变不再只是按年份排列论文标题，而是 EvolutionItem：

- year；
- paper_id；
- title；
- contribution；
- evidence_ids / evidence_quotes；
- relationship to concept。

主张批次要求每篇输入论文生成一个演变项，时间线不会完全依赖模型自由挑选论文。

时间线用于回答：

- 论文引入了什么方法；
- 它针对哪类问题；
- 与前后方法家族有什么关系；
- 描述能回到哪篇论文和哪句摘要。

它仍不是严格引用图，也不是 Connected Papers 的图嵌入相似网络。

---

## 12. 主张—证据账本

### 12.1 用途

论文卡告诉研究者“文献里有什么”，主张卡告诉研究者“系统总结了什么”。账本连接两者，回答：

- 主张由哪篇论文支持；
- 支持它的是哪句摘要；
- 是直接支持、有条件支持、反驳还是仅背景；
- 匹配有多强；
- 来自自动匹配、模型引用还是人工确认；
- 是否存在未链接主张。

### 12.2 对象

ClaimRecord：

- claim_id；
- claim_type；
- text；
- paper_ids；
- scope；
- confidence；
- evidence_links。

ClaimEvidenceLink：

- evidence_id；
- relation；
- strength；
- origin；
- match_score；
- matched_terms；
- status；
- reviewed_by；
- reviewed_at；
- review_note。

EvidenceLedger：

- claims；
- coverage 指标；
- direct / qualified / background / contradicted / unlinked 统计；
- verified coverage。

### 12.3 自动匹配约束

如果主张指定 paper_ids，证据只允许来自相同论文。匹配综合考虑：

- 类型是否相容；
- quote 是否精确命中；
- 数字集合是否一致；
- 中英文关键词重叠；
- 模型提示的证据 ID 是否有效；
- 来源范围；
- 引用是否能解释主张。

每条主张最多保留 3 条最相关证据，避免用大量弱相关句制造“证据很多”的错觉。

### 12.4 关系

| relation | 含义 |
| --- | --- |
| supports | 摘要直接支持 |
| qualifies | 支持但有条件、范围或限定 |
| contradicts | 摘要与主张冲突 |
| background | 仅提供主题背景 |

### 12.5 强度

| strength | 含义 |
| --- | --- |
| strong | 精确引用、同论文、类型和数字高度一致 |
| moderate | 语义支持明显但有表述或范围差异 |
| weak | 仅部分相关，应谨慎使用 |

自动 strong 仍可能是 unverified。

### 12.6 指标

- evidence_count；
- linked_claim_count；
- link_coverage；
- verified_coverage；
- direct_support_count；
- direct_support_coverage；
- qualified_count；
- background_count；
- contradicted_count；
- unlinked_count。

这些指标帮助研究者识别：

- 是否有大量无来源主张；
- 哪些只是背景相关；
- 哪些需要人工检查；
- 哪些值得回原论文阅读全文。

---

## 13. 人工核验

新增接口：

    GET /api/v1/analyses/{analysis_id}/evidence-ledger

    PATCH /api/v1/analyses/{analysis_id}/claims/{claim_id}/evidence/{evidence_id}/review

人工核验可以提交：

- relation；
- review_note；
- reviewed_by。

review_note 至少 2 个字符，避免空核验。

研究者可在前端标记：

- 支持；
- 有条件；
- 反驳；
- 仅背景。

核验只更新关系元数据，不修改论文摘要原文，保证来源内容不可被人工审阅操作改写。

---

## 14. 研究限制、研究空白与复现检查

### 14.1 三者分离

研究限制：

- 已有方法在某条件下失败、退化、增加代价或不适用；
- 必须说明对象、条件和后果；
- 必须回到同论文限制证据。

研究空白：

- 摘要明确指出未研究、缺少系统指导或仍未解决；
- 只能限定为“在本次检索到的摘要范围内”；
- 不能声称全世界无人研究。

复现检查：

- 代码、数据、环境、许可证、基准是否可获得；
- 属于工程复现风险，不是方法本身局限。

### 14.2 ResearchLimitation

- text；
- kind；
- target；
- condition；
- consequence；
- paper_ids；
- evidence_ids；
- explicitness。

kind：

- method_limitation；
- failure_mode；
- tradeoff；
- applicability_boundary；
- evaluation_limitation；
- theoretical_limit。

### 14.3 候选生成

只有摘要规则标记为 limitation 或 future_work 的证据句进入限制审计。候选跨论文轮转，避免一篇长摘要占满名额，上限约 30 条。

### 14.4 LimitationDecision

模型必须对每个候选返回：

- evidence_id；
- decision：limitation / research_gap / reject；
- reason；
- kind。

接受为 limitation：

- 明确失败；
- 明确性能退化；
- 明确额外成本；
- 明确适用边界；
- 明确理论不可能；
- 明确评估覆盖不足。

接受为 research_gap：

- not investigated；
- little systematic guidance；
- remains open；
- future work should explore；
- 明确尚未覆盖的问题。

拒绝：

- KV cache 普遍消耗显存；
- 只有方法描述，没有负面结果；
- 只出现 tradeoff，没有说明代价；
- 单纯结果句；
- 系统自身只读摘要的告警；
- 需要人工核验；
- 与论文研究对象无关的泛泛建议。

### 14.5 安全恢复

模型可能已经对候选给出有效 research_gap 决策，但附带 gap 对象格式错误。满足以下条件时，系统恢复一个保守研究空白：

- 候选证据有效；
- 决策为 research_gap；
- evidence_id 可定位；
- 原文来自对应摘要；
- 输出限定于本次检索摘要范围。

这样不会因一个附属 JSON 字段错误丢掉已被完整验证的审计决定。

---

## 15. 模型输出解析与修复

### 15.1 核心字段

one_sentence、intuitive、technical 等核心解释严格校验，因为它们决定页面主体是否成立。

### 15.2 可选数组逐项校验

- atomic_claims；
- evolution；
- related_concepts；
- limitations；
- research_gaps；
- reproducibility_checks；
- limitation_decisions。

一个坏对象不会清空同数组其他对象，也不会清空核心解释。

### 15.3 安全别名修复

含义唯一时修复：

- claim / content / statement 映射为 text；
- type 映射为 claim_type；
- paper_id 映射为 paper_ids；
- evidence_quote 映射为 evidence_quotes。

无法确定含义时丢弃该项并告警。

### 15.4 用户可见修复记录

前端“模型输出修复记录”显示：

- 哪个可选项被忽略；
- 为什么无法安全校验；
- 其他内容是否保留。

“研究空白候选中有 1 条无法安全校验，已忽略；其他解释和主张仍然保留”只表示一个结构对象失败，不等于整次结果失败。

---

## 16. 前端更新

本轮前端增加或完善：

- 概念输入；
- 分析模式；
- 面向读者；
- 最大论文数；
- 阶段进度；
- 总耗时和阶段耗时；
- 实际搜索词；
- 查询目的；
- 初始 / 反馈阶段；
- 论文元数据；
- 开放全文链接；
- 摘要预览和展开；
- 多标签证据卡；
- 一句话、直观和技术解释；
- 演变时间线；
- 相关概念；
- 研究限制和研究空白；
- 主张—证据账本；
- 支持强度与关系；
- 人工核验控件；
- 模型修复告警；
- 研究问题保存区域。

设计目标是让研究者从概念解释逐步下钻到论文、摘要原句和主张关系，而不是只看到一篇不可审计的长答案。

---

## 17. 配置、环境和密钥安全

### 17.1 根目录 .env

配置固定从仓库根目录读取：

    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    env_file = PROJECT_ROOT / ".env"

无论从仓库根目录还是 backend 启动，都读取同一份 .env。

### 17.2 配置槽位

- paper provider；
- community provider；
- explanation provider；
- experiment provider。

paper provider 使用 arXiv 时不需要 Key。解释模型使用 OpenAI 兼容接口，可配置 DeepSeek。

### 17.3 安全要求

- .env 不提交；
- .env.example 只放占位符；
- API 状态只返回遮罩信息；
- 本日志不记录真实 Key；
- ModelCallTrace 不记录 Authorization；
- 测试不包含真实密钥。

聊天中出现过的临时 Key 应在试用后由持有人撤销。即使 Key 是临时的，也不应进入 Git 历史。

---

## 18. 数据结构变化

### 18.1 研究数据

| 数据结构 | 用途 |
| --- | --- |
| PaperRecord | 规范化论文元数据 |
| SearchQueryPlan | 记录查询、目的、阶段和来源论文 |
| EvidenceLocator | 标记证据位置 |
| EvidenceCard | 保存摘要原句、多标签和核验信息 |
| EvolutionItem | 带论文与证据来源的演变节点 |
| AtomicClaimDraft | 待校验原子主张 |
| ResearchLimitation | 结构化方法限制 |
| ResearchGapCandidate | 有范围约束的研究空白 |
| ReproducibilityCheck | 工程复现检查 |
| LimitationDecision | 对每个限制候选的审计决定 |
| ModelCallTrace | 子模型调用诊断 |
| ExplanationResult | 汇总解释、主张、演变、限制、告警和追踪 |

### 18.2 证据账本

| 数据结构 | 用途 |
| --- | --- |
| ClaimRecord | 最终展示和核验的主张 |
| ClaimEvidenceLink | 主张与证据关系 |
| EvidenceLedger | 全部主张、链接和覆盖率 |

### 18.3 分析任务

| 数据结构 | 用途 |
| --- | --- |
| AnalysisStageTiming | 阶段开始、结束和耗时 |
| AnalysisResult | 论文、解释、证据、账本和阶段状态 |

这些结构持久化在现有 SQLite 分析记录中，刷新后仍可读取分析结果和账本。

---

## 19. 文件级改动

相对 main 共修改 21 个文件。

### 配置和文档

#### .env.example

- 增加论文、社区、解释和实验提供方示例；
- 提供 OpenAI 兼容 base URL、模型名和 Key 占位符；
- 不包含真实密钥。

#### README.md

- 增加启动和概念分析说明；
- 增加环境变量与开发说明；
- 补充 arXiv 和解释模型配置。

#### docker-compose.yml

- 对齐新环境变量和服务启动配置。

#### docs/architecture.md

- 记录概念分析、论文检索、证据和前后端结构。

### 后端入口与配置

#### backend/app/config.py

- 新增研究提供方配置；
- 将 .env 固定到项目根目录；
- 增加解释模型与数据源参数。

#### backend/app/api/routes.py

- 扩展概念分析任务；
- 增加 evidence ledger 查询；
- 增加人工核验 PATCH；
- 增加请求校验与错误响应。

### 后端数据结构

#### backend/app/schemas.py

- 扩展 API 请求和结果；
- 增加阶段耗时。

#### backend/app/research_schemas.py

- 增加论文、查询计划、演变、原子主张、限制、空白、复现检查和调用追踪。

#### backend/app/evidence_schemas.py

- 增加多标签证据、locator、ClaimRecord、ClaimEvidenceLink 和 EvidenceLedger。

### 后端服务

#### backend/app/services/research_providers.py

- 实现 arXiv Atom API；
- 解析 XML 和元数据；
- 处理节流、错误、URL 和去重标识；
- 保留 provider 扩展点。

#### backend/app/services/research_orchestration.py

- 编排阶段；
- 记录进度和耗时；
- 执行初始与反馈检索；
- 合并论文；
- 调用证据、解释和概念关系流程；
- 持久化最终对象。

#### backend/app/services/research_service.py

本轮核心改动最多的文件之一：

- 生成初始和反馈查询；
- 规则回退查询；
- 摘要证据抽取；
- 多标签分类；
- 拆分并行模型调用；
- 分批论文主张；
- 结构解析和局部修复；
- 原子性与数字校验；
- exact quote 回查；
- 限制审计；
- 研究空白安全恢复；
- 生成告警与调用追踪。

#### backend/app/services/settings_service.py

- 返回 provider 的安全配置状态；
- 避免泄露完整密钥。

#### backend/app/services/idea_service.py

- 对齐新增分析结构和后续创新工作区入口。

### 前端

#### frontend/index.html

- 扩展分析表单和结果区；
- 增加论文、证据、账本、限制和核验容器。

#### frontend/app.js

- 发起和轮询任务；
- 展示阶段和耗时；
- 渲染查询、论文、证据、解释、演变和账本；
- 处理展开折叠；
- 发送人工核验；
- 展示修复记录与范围告警。

#### frontend/styles.css

- 重构长页面布局；
- 增加论文卡、证据块、标签、账本、告警、按钮和响应式样式。

### 测试

#### backend/tests/test_research_providers.py

- arXiv XML 正常与异常解析；
- 元数据缺失；
- URL 和 ID 规范化；
- 节流；
- provider 错误。

#### backend/tests/test_evidence_ledger.py

- 同论文约束；
- exact quote；
- 数字不一致；
- 关系和强度；
- 覆盖率；
- 人工核验。

#### backend/tests/test_api.py

- 任务创建、进度和结果；
- 新数据结构；
- evidence ledger；
- review 接口；
- 失败和边界响应。

#### backend/tests/test_api_keys.py

- 配置状态和 Key 遮罩；
- 不泄露真实 Key。

---

## 20. 关键失败实验与经验

### 20.1 过小 max_tokens

目的：控制输出长度、费用和等待。

结果：结构化 JSON 被截断，core 可能成功，但 claim batches 和 limitation audit 解析失败，最终只剩核心解释。

结论：对严格 JSON 输出，硬截断比自然完成更危险，最终撤销 token cap。

后续应改为：

- 缩小批次；
- 只重试失败批次；
- 缓存成功批次；
- 使用结构化输出约束；
- 按字段拆分而非截断尾部。

### 20.2 单次长解释

问题：

- 慢点不可见；
- schema drift 影响全部；
- 论文串线；
- 限制质量不稳定。

修复：拆成 core、claim batches、limitation audit，并行并记录 trace。

结论：拆分提升可靠性和可诊断性，不保证绝对更快。

### 20.3 把格式错误等同于没有研究空白

模型可能已给 evidence_id 做出 research_gap 决策，但 gap 对象缺字段。旧逻辑会全部丢掉。

修复：候选、原文和决策都可验证时，安全恢复受范围限制的 gap。

### 20.4 旧 Uvicorn reload 子进程

表现：

- 代码已更新；
- 测试通过；
- 页面缺少新字段；
- 新日志正常但端口仍由旧进程占用。

定位：

- 查 8000 监听 PID；
- 查父子进程；
- 检查 OpenAPI 是否包含 model_call_traces 和 limitation_decisions；
- 对照真实响应；
- 终止完整旧进程树并重启。

结论：Windows 验收优先单进程。使用 --reload 时必须确保 parent、reloader、spawn 全部退出。

### 20.5 PowerShell 中文编码

一次命令行测试中中文概念经管道变成问号，导致查询异常。浏览器 UTF-8 请求不受影响。

命令行回归应显式使用 UTF-8，或使用英文概念做烟雾测试。

### 20.6 gh 登录网络问题

写本日志时发现 gh 设备登录直连 github.com:443 超时，但仓库 Git 远端通道仍可读取。

根因是当前环境存在本地代理配置，而单独打开的 PowerShell 没有把 HTTP_PROXY / HTTPS_PROXY 传给 gh。该问题影响 gh 设备登录，不等同于仓库损坏、分支错误或 Git 凭据一定失效。

---

## 21. 测试与验收

### 21.1 自动化测试

最终完整后端测试：

    96 passed

只有现有 Starlette 弃用提示，没有失败。

覆盖重点：

- arXiv Atom 解析和 malformed XML；
- 查询规划；
- 反馈查询；
- 节流；
- 快速 / 文献模式；
- provider 回退；
- schema alias 修复；
- 可选数组逐项丢弃；
- 核心与辅助失败隔离；
- 多标签证据；
- 每批论文覆盖；
- exact quote 对应论文；
- 错误 evidence ID 不越权；
- 数字不一致拒绝；
- 强措辞弱化；
- 主张原子性；
- 限制候选覆盖；
- limitation decision；
- research gap 安全恢复；
- evidence ledger；
- 人工核验；
- API 进度；
- Key 遮罩。

### 21.2 前端

    node --check frontend/app.js

通过，无 JavaScript 语法错误。

### 21.3 Git 检查

    git diff --check

通过。仅可能出现 Windows 行尾转换提示，无冲突标记和尾随空白错误。

### 21.4 真实 API 运行

最近一次成功运行：

| 项目 | 结果 |
| --- | --- |
| analysis ID | e57c246c-c4ed-428c-8cb6-2b79cfe58889 |
| 概念 | KV cache compression |
| 论文 | 6 篇 |
| 摘要证据卡 | 23 条 |
| 原子论文主张 | 15 条 |
| 结构化限制 | 3 条 |
| 最终账本主张 | 18 条 |
| 直接支持 | 18 条 |
| direct support coverage | 1.0 |
| 未链接 | 0 条 |
| 限制候选决策 | 7 条 |
| limitation | 3 条 |
| research_gap 决策 | 1 条 |
| reject | 3 条 |
| 总耗时 | 205.111 s |
| 模型子调用 | 5 个全部成功 |

说明：research gap 从有效决策安全恢复结构对象，是该次真实调用后补充的，并由针对性离线测试覆盖。本文不会把离线修复误写成该次真实运行已经展示的结果。

另一轮稳定结果：

| 项目 | 结果 |
| --- | --- |
| analysis ID | 3075dee7… |
| 论文 | 6 篇 |
| 原子主张 | 15 条 |
| 限制 | 3 条 |
| 账本主张 | 18 条 |
| 直接支持 | 16 条 |
| 未链接 | 2 条 |
| 总耗时 | 174.861 s |

不同运行的差异来自论文集合、模型排队、输出选择和网络时延。

### 21.5 不消耗 Key 的回归

绝大多数测试使用：

- 固定响应；
- mock provider；
- 本地 XML；
- 可注入时钟；
- 规则后处理；
- API 测试客户端。

日常回归不需要真实模型额度。真实 API 只用于获批的集成验证。

---

## 22. 当前使用方式

### 22.1 目录

推荐在：

    D:\agent\research_agent

不要在 D:\agent 误用仓库内相对路径。

### 22.2 .env 示例

    WISHFORGE_PAPER_PROVIDER=arxiv
    WISHFORGE_EXPLANATION_PROVIDER=openai-compatible
    WISHFORGE_EXPLANATION_BASE_URL=https://api.deepseek.com
    WISHFORGE_EXPLANATION_MODEL=<your-model-name>
    WISHFORGE_EXPLANATION_API_KEY=<your-temporary-key>

不要把真实 Key 复制到日志、README、测试、截图说明或提交记录。

### 22.3 启动检查

- 使用正确虚拟环境；
- Python 能导入 backend/app；
- 端口 8000 没有旧进程；
- 根目录 .env 存在；
- provider 状态显示解释模型已配置。

验收时建议不带 --reload 的单进程 Uvicorn。

### 22.4 页面流程

1. 输入概念；
2. 选择快速或 arXiv 文献解释；
3. 选择读者层级；
4. 设置论文数；
5. 开始分析；
6. 观察阶段进度；
7. 查看查询及反馈来源；
8. 阅读论文摘要与证据卡；
9. 检查解释；
10. 查看演变；
11. 展开账本；
12. 人工核验重要关系；
13. 将真正的问题保存到 Research Board。

---

## 23. 页面标签和告警

### 有证据 / 无证据

- 有证据：找到符合约束的摘要句；
- 无证据：没有安全建立可审计链接。

### low / medium / strong

它是自动证据关系强度，不是论文质量评分。

low 常见原因：

- 只有关键词重叠；
- 没有 exact quote；
- 只能提供背景；
- 主张范围更宽；
- 尚未人工核验；
- 类型不完全匹配。

### 未人工核验

表示研究者尚未审阅。即使 supports 且 strong，也可能仍是 unverified。

### 摘要反馈模型未生成可用查询

只表示反馈检索使用规则回退，不影响已成功的核心解释和第一轮检索。

### 模型输出修复记录

表示模型 JSON 局部偏差，系统保留安全字段并丢弃不确定对象。

### 演示资料

演示资料是无网络或无 Key 时的固定开发数据。正常 arXiv 模式不会自动拿演示资料冒充真实检索；显式 demo 必须显示来源标签。

---

## 24. 研究者如何利用结果

### 第一步：建立术语地图

先看一句话和直观解释，确认系统理解与研究问题一致。技术解释帮助识别方法对象、关键过程和评价维度。

### 第二步：审查检索范围

检查初始和反馈查询，判断是否遗漏同义词、方法家族、任务或场景。查询计划本身就是研究范围定义。

### 第三步：阅读演变

发现：

- 哪些论文提出新机制；
- 哪些论文处理新场景；
- 哪些指出前类方法限制；
- 哪些方向近期活跃。

### 第四步：用账本筛选全文

优先检查：

- 含数字的结果；
- 理论边界；
- 限制；
- 研究空白；
- qualified 或 weak；
- 关键但未人工核验的主张。

### 第五步：回原论文

点击来源阅读全文。摘要卡用于筛选和定位，不替代全文。

### 第六步：形成研究问题

组合：

- 一个方法叶子节点；
- 一条有证据的限制或边界；
- 一个可测量目标或场景。

例：

    方法家族：KV cache token eviction
    限制：特定长上下文或推理场景的重要 token 识别不稳定
    研究问题：能否使用任务条件化价值估计，在相同缓存预算下降低关键 token 误删？

这仍是候选，之后必须进行全文检索、引用追踪和创新性查重。

---

## 25. 当前边界

### 25.1 主要读取摘要

没有系统读取 PDF 全文、Method、Experiment、Limitations 和 Discussion，因此：

- 摘要未写出的限制无法发现；
- 结果条件可能不完整；
- 指标细节可能缺失；
- future work 召回有限；
- 不能进行真正全文定位。

### 25.2 不是 Connected Papers

当前是关键词和反馈关键词检索，不包含：

- 引用图；
- 共引关系；
- bibliographic coupling；
- 论文嵌入相似图；
- seed paper 周边网络。

### 25.3 不能证明创新性

arXiv 没搜到不代表无人做过，还可能存在：

- 期刊；
- 会议正式版；
- 专利；
- 非英文论文；
- 未上 arXiv 的论文；
- 工业报告；
- 使用不同术语的同类方法。

### 25.4 反馈查询偶尔回退

模型可能返回空数组、过长查询或自然语言句。规则回退保证流程继续，但覆盖有限。

### 25.5 模型延迟波动

DeepSeek 成本较低，适合开发反复测试，但延迟受排队和输出长度影响，6 篇论文完整分析可能数分钟。

### 25.6 诊断尚未完整前端化

ModelCallTrace 和 LimitationDecision 已存储，但缺少完整前端诊断专页。

### 25.7 社区检索尚未真实实现

X、知乎、Reddit 适配器仍属后续。现有 community provider / demo 不能描述为真实社区检索完成。

### 25.8 人工核验不可省略

自动账本不能替代：

- 阅读全文；
- 检查实验设置；
- 复核数学推导；
- 评估数据偏差；
- 判断是否被后续工作推翻；
- 判断创新点是否真正新颖。

---

## 26. 后续建议

### P0：下一阶段

1. PDF 全文获取和解析：
   - Method；
   - Experiment；
   - Limitations；
   - Discussion；
   - 页码和章节 locator。
2. 只重试失败模型批次；
3. 子调用缓存：
   - 摘要集合 hash；
   - prompt 版本；
   - 模型名；
   - 模式；
   - 读者层级。
4. 前端展示 ModelCallTrace 和 LimitationDecision；
5. 支持用户补充、删除检索词；
6. 将研究限制转成可编辑研究问题。

### P1：论文网络

1. 接入 OpenAlex、Crossref 或 Semantic Scholar 引用元数据；
2. 构建 cited-by / references 图；
3. 增加共引和 bibliographic coupling；
4. 使用摘要向量补充相似论文；
5. 区分概念、引用、方法继承、证据支持、限制与解决关系。

### P1：证据质量

1. 为不同主张类型设计独立匹配器；
2. 增加单位归一化但禁止改变指标含义；
3. 增加实验条件结构；
4. 为 contradicts 做专门检索；
5. 将人工核验用于评估，不直接用于无审计自动学习。

### P1：社区检索

1. 分别实现 Reddit、知乎、X 适配器；
2. 保存平台、作者、时间、URL、互动量和原文；
3. 区分事实、体验、工程痛点和观点；
4. 不把社区热度等同学术证据；
5. 单独处理条款、限速和隐私。

### P2：概念树与图

1. 建立 Node / Edge / Tree / Graph；
2. agent 通过受约束工具新增、编辑、移动和删除节点；
3. 所有变更可撤销；
4. 节点关联解释、论文、主张、限制、注释和创新候选；
5. 支持多个树局部选取和跨树连边；
6. 对跨领域连接解释可迁移原因与验证条件。

### P2：工程化

1. 增加任务队列和持久化 worker；
2. 支持取消分析；
3. 支持失败阶段继续；
4. provider 超时、退避与熔断；
5. token / 成本统计；
6. 用户认证与密钥安全存储；
7. 数据库迁移；
8. 版本化 prompt 和离线质量评测。

---

## 27. 验收清单

- [x] 未直接修改 main
- [x] 使用独立开发分支
- [x] arXiv 真实适配器
- [x] 快速解释
- [x] 文献解释
- [x] 初始查询规划
- [x] 摘要反馈检索
- [x] 可追溯规则回退
- [x] 论文规范化与去重
- [x] 摘要证据卡
- [x] 证据多标签
- [x] 原子主张
- [x] 同论文 quote 校验
- [x] 数字保护
- [x] 强措辞弱化
- [x] 演变时间线
- [x] 主张—证据账本
- [x] 自动覆盖率指标
- [x] 人工核验接口
- [x] 前端人工核验
- [x] 研究限制审计
- [x] 研究空白分离
- [x] 复现检查分离
- [x] 模型调用拆分
- [x] 子调用追踪
- [x] 局部 schema drift 容错
- [x] 根目录 .env 加载修复
- [x] Windows 旧进程问题定位
- [x] 96 项自动化测试通过
- [x] 前端 JavaScript 语法检查
- [x] 未提交真实 API Key
- [ ] PDF 全文与 Discussion
- [ ] 引用图 / Connected Papers 式网络
- [ ] 真实社区适配器
- [ ] 概念树编辑工具
- [ ] 多概念树图页面
- [ ] 全面创新性查重

---

## 28. 给下一位开发者的交接

1. 开始前确认当前分支，不在 main 直接改；
2. 先运行完整测试，再判断页面问题是否来自代码；
3. 页面与代码结构不一致时，先查端口和旧 Uvicorn 子进程；
4. 不要把解释、主张和限制重新合成一个巨型调用；
5. 不要设置会截断 JSON 的硬 token 上限；
6. 新字段保持核心严格、可选列表逐项容错；
7. 论文特定主张保持论文边界；
8. 数字必须回查原文；
9. evidence_id 只是提示，不是授权；
10. 自动 supports 不等于人工 verified；
11. 只读摘要属于 scope warning，不是研究限制；
12. 研究空白必须限定检索范围；
13. 新数据源保存 provider、URL、检索时间和原始定位；
14. 真实 API 测试需明确同意，普通回归继续 mock；
15. push 前说明分支和提交，不擅自合并 main。

---

## 29. 最终结论

本轮完成了从“能调用模型、能列出论文”到“能够进行初步证据化文献分析”的关键跃迁。

当前版本最有价值的能力：

- 检索过程可解释；
- 论文来源可追溯；
- 摘要证据可定位；
- 主张拆成更小单位；
- 数字和原文引用会校验；
- 限制和研究空白经过专门审计；
- 模型格式错误不会轻易抹掉全部结果；
- 自动判断允许人工纠正；
- 每一步边界被明确表达。

当前最需要警惕：

- 摘要不是全文；
- 自动支持不是人工核验；
- 关键词检索不是完整论文网络；
- 没搜到不是没人做过；
- 低成本模型适合大量测试，但延迟和结构稳定性仍需治理；
- 真正创新点判断必须扩展全文、引用图、社区和跨来源检索。

因此，这一版本可以作为概念分析和论文初筛的可靠第一版，也为后续概念树、概念图、社区检索、多智能体创新分析和创新性查重提供了较稳固的数据基础。

---

## 30. Phase 1：概念图生命周期（`codex/graph-lifecycle`）

本阶段从 `main` 新建分支开发，目标限定为图快照生命周期，不提前实现 Cytoscape、Overview 多 Agent 或 Tauri 壳。

- 分析完成后的概念图嵌入 `AnalysisResult`，默认 `save_state=transient`；不会自动写入已保存图库。
- 新增分析图读取、元数据 PATCH、显式保存接口；保存使用版本号 CAS，重复保存复用同一图 ID。
- 前端新增保存 Action Sheet，默认聚焦“保存概念图”；关闭或“暂不保存”只保留历史快照。
- 新增整图删除接口；删除会级联 GraphPatch，并把关联历史快照回退为 `transient`，不删除分析、论文和证据。
- SQLite `user_version` 迁移到 2，补充概念图生命周期字段、`overview_jobs` 预留表和临时图 Patch 预留表；旧图默认按已保存图兼容读取。
- 临时图在本阶段只允许改名称/根节点；节点结构和 Agent Patch 控件会提示先保存，避免请求不存在的已保存图端点。
- 新增 `PaperReadingSummary`、节点角色兼容推导和图视觉字段，为后续真实研究图预留数据契约。
- 验证：`python -m pytest backend/tests -q`、`node --check frontend/app.js`、Python 编译检查和 `git diff --check` 通过；另有隔离 SQLite 生命周期端到端测试通过。

本阶段仍明确未完成：真实圆形节点和连线、Cytoscape.js、研究方向 Overview、arXiv PDF 章节阅读、Tauri sidecar 和 iOS 风格桌面壳。
