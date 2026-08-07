# Stage 0 架构说明

## 目标

先验证最小的 Web 控制台和 API 边界，为之后的“文献证据—解释—实验—结论”闭环留出稳定接口。Stage 0 不引入数据库、向量库、论文爬虫或任意代码执行权限。

## 组件

```text
Browser
  │ HTTP
  ▼
FastAPI API (/api/v1)
  ├── ProjectService（当前为内存存储）
  ├── SettingsService（分用途密钥状态，不返回明文）
  ├── EvidenceService（下一阶段）
  ├── ExperimentService（下一阶段）
  └── Runner Adapter（下一阶段，通过 runner 边界接入）
```

前端由 FastAPI 提供静态文件，减少第一阶段的构建工具和部署变量。后续如果 UI 复杂化，可以平滑迁移到 Next.js，而不改变 API 契约。

## 当前 API

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/v1/health` | 服务健康检查 |
| GET | `/api/v1/settings/api-keys` | 获取各用途密钥的配置状态和掩码 |
| GET | `/api/v1/projects` | 获取研究项目 |
| POST | `/api/v1/projects` | 创建草稿项目 |

## 阶段边界

- API 层只负责输入校验、响应格式和鉴权扩展点；
- 论文检索、解释模型、实验执行分别使用独立的 provider 和 API key 配置槽位；
- API 只返回密钥是否配置以及最后几位掩码，绝不返回明文；
- `.env` 是当前版本的密钥入口，`.env` 已被 Git 忽略；
- 领域服务不依赖 FastAPI，后续可被任务队列或 CLI 调用；
- Runner 不与 API 进程共享任意 Shell 权限；
- 论文全文只从用户合法提供的文件或开放来源进入系统；
- 每个后续阶段都必须有可验证的输入、输出和验收指标。

## 后续阶段建议

1. `codex/literature-explanation`：论文导入、元数据去重、证据卡和易懂解释；
2. `codex/evidence-matrix`：主张、条件、冲突和证据图；
3. `codex/experiment-contract`：可证伪假设、实验计划和人工审批；
4. `codex/local-runner`：隔离的计算实验执行和产物清单；
5. `codex/provenance-report`：结论溯源图和可复现报告。
