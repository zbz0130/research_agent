$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$frontendDir = Join-Path $repoRoot "frontend"

if (-not (Test-Path $venvPython)) {
  Write-Host "Python virtual environment not found: $venvPython" -ForegroundColor Yellow
  Write-Host "This launcher is for developers. First run: python -m venv .venv" -ForegroundColor Yellow
  Read-Host "Press Enter to exit"
  exit 1
}

# Keep this launcher ASCII-only so that it is parsed correctly by Windows
# PowerShell 5.1 after users download a source archive from GitHub.
$venvScripts = Join-Path $repoRoot ".venv\Scripts"
$env:Path = $venvScripts + ";" + $env:Path
$env:PYTHONPATH = Join-Path $repoRoot "backend"

if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
  Write-Host "First launch: installing frontend dependencies..." -ForegroundColor Cyan
  Push-Location $frontendDir
  try { & npm.cmd install }
  finally { Pop-Location }
  if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
}

Write-Host "Starting WishForge desktop app..." -ForegroundColor Cyan
Push-Location $frontendDir
try { & npm.cmd run tauri:dev }
finally { Pop-Location }
exit $LASTEXITCODE
