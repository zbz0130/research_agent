$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$frontendDir = Join-Path $repoRoot "frontend"

if (-not (Test-Path $venvPython)) {
  Write-Host "未找到 Python 虚拟环境：$venvPython" -ForegroundColor Yellow
  Write-Host "请先运行：python -m venv .venv" -ForegroundColor Yellow
  Read-Host "按 Enter 退出"
  exit 1
}

# Make the desktop sidecar use the repository virtual environment without
# requiring the user to activate it manually in the current shell.
$env:Path = "$(Join-Path $repoRoot '.venv\Scripts');$env:Path"
$env:PYTHONPATH = Join-Path $repoRoot "backend"

if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
  Write-Host "首次启动：正在安装前端依赖…" -ForegroundColor Cyan
  Push-Location $frontendDir
  try { & npm.cmd install }
  finally { Pop-Location }
  if ($LASTEXITCODE -ne 0) { throw "前端依赖安装失败。" }
}

Write-Host "正在启动 WishForge 桌面 App…" -ForegroundColor Cyan
Push-Location $frontendDir
try { & npm.cmd run tauri:dev }
finally { Pop-Location }
exit $LASTEXITCODE
