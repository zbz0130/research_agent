$ErrorActionPreference = "Stop"

# Build the Python API into the filename Tauri expects for the current target.
# API keys are read at runtime by the Tauri host; this executable contains no
# credentials or user data.
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\")).Path
$targetTriple = "x86_64-pc-windows-msvc"
$outputDir = Join-Path $repoRoot "src-tauri\bin"
$name = "wishforge-sidecar-$targetTriple"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$backendPath = Join-Path $repoRoot "backend"
$entryPoint = Join-Path $backendPath "sidecar.py"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
  throw "Project Python was not found at $python. Create .venv and install backend/requirements-dev.txt first."
}

& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller is missing from .venv. Run .venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt pyinstaller."
}

New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

Push-Location $repoRoot
try {
  & $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name $name `
    --paths $backendPath `
    --hidden-import app.main `
    --collect-submodules uvicorn `
    --collect-submodules pydantic `
    --distpath $outputDir `
    --workpath (Join-Path $repoRoot "artifacts\pyinstaller") `
    --specpath (Join-Path $repoRoot "artifacts\pyinstaller") `
    $entryPoint
} finally {
  Pop-Location
}

$executable = Join-Path $outputDir "$name.exe"
$runId = [Guid]::NewGuid().ToString("N")
$smokeDir = Join-Path $repoRoot "artifacts\sidecar-smoke\$runId"
$stdoutLog = Join-Path $smokeDir "stdout.log"
$stderrLog = Join-Path $smokeDir "stderr.log"
New-Item -ItemType Directory -Path $smokeDir -Force | Out-Null
$existingProcessIds = @(
  Get-Process -Name $name -ErrorAction SilentlyContinue |
    ForEach-Object { $_.Id }
)

$listener = [System.Net.Sockets.TcpListener]::new(
  [System.Net.IPAddress]::Loopback,
  0
)
$listener.Start()
$port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
$listener.Stop()

$process = Start-Process `
  -FilePath $executable `
  -ArgumentList @("--port", $port, "--data-dir", $smokeDir) `
  -WindowStyle Hidden `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog `
  -PassThru

try {
  $healthy = $false
  for ($attempt = 0; $attempt -lt 120; $attempt++) {
    if ($process.HasExited) {
      break
    }
    try {
      $response = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$port/api/v1/health" `
        -TimeoutSec 1
      if ($null -ne $response) {
        $healthy = $true
        break
      }
    } catch {
      Start-Sleep -Milliseconds 250
    }
  }
  if (-not $healthy) {
    $details = (Get-Content -LiteralPath $stderrLog -Raw -ErrorAction SilentlyContinue).Trim()
    throw "Built sidecar failed its health check. $details"
  }
} finally {
  $smokeProcesses = @(
    Get-Process -Name $name -ErrorAction SilentlyContinue |
      Where-Object { $_.Id -notin $existingProcessIds }
  )
  foreach ($smokeProcess in $smokeProcesses) {
    Stop-Process -Id $smokeProcess.Id -Force -ErrorAction SilentlyContinue
  }
  foreach ($smokeProcess in $smokeProcesses) {
    $smokeProcess.WaitForExit()
  }
}

$sizeMiB = [math]::Round((Get-Item -LiteralPath $executable).Length / 1MB, 2)
Write-Host "Built and verified $name.exe ($sizeMiB MiB) in $outputDir"
