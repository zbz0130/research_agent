# TraceLab / 证研

面向科研人员的证据驱动研究工作台：把论文证据、研究假设、可复现实验和结论放进同一条可追溯链路。

当前仓库处于 **Stage 0：最小架构骨架**。这一阶段只验证 Web 控制台、API 和后续本地实验执行器之间的边界，不实现文献检索或实验执行业务。

## 当前分支

开发采用阶段分支流程：

```text
main
  └── codex/scaffold-architecture  # 当前阶段：最小架构骨架
```

每个阶段完成后先由项目负责人验收，再合并到 `main`。未通过验收的阶段不会直接进入 `main`。

## 目录结构

```text
.
├── backend/                 # FastAPI API 与领域服务
│   └── app/
├── frontend/                # 桌面优先的 Web 控制台（当前为零构建依赖原型）
├── runner/                  # 后续本地 Docker/GPU 实验执行器的边界说明
├── docs/                    # 架构和阶段验收说明
├── docker-compose.yml
└── .env.example
```

## 本地运行

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
$env:PYTHONPATH = "backend"
uvicorn app.main:app --reload
```

然后打开 <http://localhost:8000>。API 文档在 <http://localhost:8000/docs>。

## Docker 运行

```powershell
docker compose up --build
```

## 当前阶段验收标准

- `GET /api/v1/health` 返回 `status=ok`；
- Web 首页可以打开并显示 API 状态；
- 可以创建和查看一个研究项目（当前使用内存存储）；
- `python -m pytest` 全部通过；
- README、架构说明和后续执行器边界清晰；
- 不提前引入数据库、向量库或任意代码执行权限。

下一阶段再实现论文导入、证据卡和持久化数据模型。
