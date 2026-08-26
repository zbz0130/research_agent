# 发布 Windows 桌面版

本项目使用 Tauri 生成 Windows NSIS 安装程序。发布工作流位于
`.github/workflows/release.yml`，推送形如 `v0.2.2` 的版本标签后会自动运行。

## 首次发布

当前项目版本是 `0.2.2`。提交代码和图标后，在仓库根目录执行：

```powershell
git add .
git commit -m "release: WishForge v0.2.2"
git push origin main
git tag v0.2.2
git push origin v0.2.2
```

然后在 GitHub 的 **Actions** 页面查看 `Release Windows app`。构建成功后，
GitHub 会自动创建 `WishForge v0.2.2` Release，并上传 Windows 安装包。

## 用户下载和运行

用户应下载 Release 的：

```text
WishForge_0.2.2_x64-setup.exe
```

这是安装程序，不是源码压缩包。用户双击安装程序完成安装，再从开始菜单或桌面
快捷方式点击 WishForge 图标即可运行。不要下载 Tag 页面提供的 Source code zip；
它是给开发者使用的源码，不能作为普通用户的安装包。当前构建目标是 Windows x64。

首次安装时，如果系统没有 WebView2，安装程序会联网下载安装 WebView2；这是当前
`tauri.conf.json` 中 `downloadBootstrapper` 的设置。

## 发布新版本

修改版本号时，保持下面三个文件中的版本一致：

- `src-tauri/tauri.conf.json`
- `src-tauri/Cargo.toml`
- `frontend/package.json`

同时更新 `frontend/package-lock.json` 中的根版本，然后提交并推送新的标签，例如：

```powershell
git add .
git commit -m "chore: release v0.3.0"
git push origin main
git tag v0.3.0
git push origin v0.3.0
```

## 图标

`images/eb85be0c-2d4b-4623-ab00-0a8840c9e9e8.png` 已生成到
`src-tauri/icons/`。Windows 安装程序和安装后的快捷方式使用其中的
`src-tauri/icons/icon.ico`。

## 注意事项

- 不要上传 API Key；应用运行时再由用户配置。
- 发布工作流会在配置 `WINDOWS_CERTIFICATE_BASE64` 与 `WINDOWS_CERTIFICATE_PASSWORD`
  两个 GitHub Secrets 后对安装包进行 Authenticode 签名；未配置证书时会明确发布未签名安装包，
  Windows 可能显示 SmartScreen 提示。不要把 PFX、密码或任何 API Key 提交到仓库。
- 桌面应用会检查 GitHub 上是否存在更高版本，并提供官方 Release 下载链接；静默自动安装需要
  额外配置 Tauri 更新签名私钥，当前不会在没有私钥时伪造更新签名。
- 当前 sidecar 和发布工作流只构建 Windows x64，不会生成 macOS/Linux 安装包。
