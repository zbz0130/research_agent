# WishForge Windows 桌面 App 规划与当前运行方式

> 当前 `codex/research-overview` 分支仍是 Vite + FastAPI 的本地 Web 应用。
> Tauri、Python sidecar、Windows Credential Manager 和安装包属于下一阶段
> `codex/tauri-ios-shell`，本文件用于锁定实现边界，不能当作已经完成的桌面交付。

## 当前怎样运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt

cd frontend
npm install
npm run build
cd ..

$env:PYTHONPATH = "backend"
python -m uvicorn app.main:app --reload
```

打开 <http://127.0.0.1:8000>。前端热更新可另开终端运行：

```powershell
cd frontend
npm run dev
```

然后打开 <http://127.0.0.1:1420>；Vite 会将 `/api` 代理到本地 8000。

## 下一阶段桌面结构

```text
Tauri Windows host
  ├── WebView2 加载 Vite 构建资源
  ├── 启动 PyInstaller FastAPI sidecar（仅监听 127.0.0.1 临时端口）
  ├── 把端口和 appDataDir 安全注入前端/sidecar
  ├── App 退出时终止 sidecar
  └── Windows Credential Manager 保存按用途分离的凭据

FastAPI sidecar
  ├── SQLite 位于 Tauri appDataDir
  ├── 论文、解释、社区、实验四个独立 Key/Base URL/模型槽位
  └── 不在日志、前端资源或 URL 中输出 API Key
```

## Windows 前置条件

- Rust stable（`rustc`、`cargo`）；
- Microsoft C++ Build Tools；
- WebView2 Runtime；
- Node.js/npm；
- Python 3.11/3.12 与 PyInstaller。

本机此前检测不到 `rustc` 和 `cargo`，所以 Phase 4 开始前要先安装 Rust 工具链；这不会阻塞当前 Web 阶段的验收。

## 数据与密钥规则

- 开发浏览器模式仍可使用现有的进程内配置和本地 `.env`；
- 生产 App 中 API Key 必须进入 Windows Credential Manager，不能写进 Vite 构建、SQLite 普通字段或日志；
- Base URL 必须是完整 `http://` 或 `https://` URL，不接受 query/fragment；
- Tauri 关闭时必须回收 sidecar；异常退出后未完成 Overview 标记为 `interrupted`；
- SQLite、日志和临时 PDF 不放在安装目录或仓库目录。

## Phase 4 验收门槛

- `npm run tauri dev` 可启动 App 和 sidecar；
- sidecar 在随机本地端口返回 `/api/v1/health`；
- 安装包重启后分析、图谱和 Overview 可恢复；
- 四种凭据分别配置、测试、脱敏显示，构建资源和普通日志中不存在 Key；
- 浅色为默认，支持暗色、键盘焦点、缩减动画和窄窗口底部导航；
- App 关闭后 sidecar 进程退出。
