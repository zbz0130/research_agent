# 许愿机 / WishForge

面向科研人员的证据驱动研究工作台：把一个模糊想法变成有来源、能理解、可继续研究的知识。

当前仓库处于 **Stage 0：最小架构骨架**。这一阶段验证 Web 控制台、API、分用途密钥配置和后续本地实验执行器之间的边界。

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
├── frontend/                # 许愿机 Web 控制台（当前为零构建依赖原型）
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

## API Key 配置

不同用途的服务使用不同的配置槽位，避免查论文的密钥被实验执行器误用：

```text
WISHFORGE_PAPER_API_KEY          # 论文检索
WISHFORGE_EXPLANATION_API_KEY   # 解释模型
WISHFORGE_EXPERIMENT_API_KEY    # 实验执行
```

复制 [.env.example](<D:/C++/search_agent/.env.example>) 为 `.env` 后填写。网页设置面板只显示“已配置/未配置”和掩码，不会返回明文密钥。

配置状态接口：

```text
GET /api/v1/settings/api-keys
```

## Docker 运行

```powershell
docker compose up --build
```

## 当前阶段验收标准

- `GET /api/v1/health` 返回 `status=ok`，服务名称显示为许愿机；
- Web 首页可以打开并显示 API 状态；
- Web 首页可以看到论文检索、解释模型和实验执行三个独立密钥槽位；
- 可以创建和查看一个研究项目（当前使用内存存储）；
- `python -m pytest` 全部通过；
- README、架构说明和后续执行器边界清晰；
- 不提前引入数据库、向量库或任意代码执行权限。

下一阶段再实现论文导入、证据卡和持久化数据模型。
