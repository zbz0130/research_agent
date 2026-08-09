# GitHub Pages 前端部署

GitHub Pages 只能承载静态前端，**不会运行 FastAPI、SQLite、论文检索或模型调用**。因此发布后的许愿机由两部分组成：

```text
GitHub Pages（公开 HTML / CSS / JavaScript）
        │ HTTPS + CORS
        ▼
独立部署的 WishForge FastAPI 服务（密钥、SQLite、Provider 调用）
```

不要把 `WISHFORGE_*_API_KEY`、`.env` 或任何 Provider 密钥放进 GitHub Pages、仓库 Variable、前端 JavaScript 或 GitHub Actions 日志。`WISHFORGE_API_BASE_URL` 只是浏览器可以公开看到的后端地址，不是密钥。

## 一次性配置

1. 将 FastAPI 服务部署在一个公开的 **HTTPS** 地址，例如 `https://wishforge-api.example.com`。它仍应在服务器环境中配置各类 `WISHFORGE_*_API_KEY`。
2. 在该 API 服务设置 CORS，允许 Pages 域名。对于本仓库，设置：

   ```env
   WISHFORGE_CORS_ORIGINS=https://zbz0130.github.io,http://localhost:8000
   ```

   若将来使用自定义 Pages 域名，也将该 HTTPS 域名以逗号分隔加入此变量。
3. 在 GitHub 仓库的 **Settings → Secrets and variables → Actions → Variables** 新建：

   ```text
   WISHFORGE_API_BASE_URL=https://wishforge-api.example.com
   ```

   这必须是不含 `/api/v1` 的 API 根地址。工作流会拒绝非 HTTPS 地址，以免把公开页面误连到不安全端点。
4. 在 GitHub 仓库的 **Settings → Pages** 将 Source 设为 **GitHub Actions**。
5. 将包含 `.github/workflows/deploy-pages.yml` 的变更合并并推送到 `main`。Actions 完成后，打开：

   ```text
   https://zbz0130.github.io/research_agent/
   ```

`Deploy frontend to GitHub Pages` 也可以在 Actions 页手动运行。每次 `main` 上的 `frontend/` 或部署工作流变化都会触发新的发布。

## 本地开发与发布版的区别

- 本地由 FastAPI 同源提供页面，`frontend/runtime-config.js` 保持空字符串即可；浏览器请求会发往当前站点的 `/api/v1/...`。
- GitHub Pages 工作流只会在发布副本中覆写 `runtime-config.js`，将 API 基地址写成仓库 Variable 的公开值。
- 页面上的 API Key 配置表单会把密钥提交给所连接的 FastAPI 服务；第一版该服务将网页输入仅保留在进程内存。没有登录、权限和持久化密钥管理时，不应将这个管理接口暴露给不受信任的公网用户。

## 发布前检查

```text
[ ] 前端能读取 runtime-config.js，并用 apiBaseUrl 构造请求 URL。
[ ] API 的 WISHFORGE_CORS_ORIGINS 包含 https://zbz0130.github.io。
[ ] GitHub Variable WISHFORGE_API_BASE_URL 是 HTTPS 根地址，且不包含密钥。
[ ] GitHub Pages Source 已设为 GitHub Actions。
[ ] 没有将 .env 或 Provider API Key 提交到仓库。
```
