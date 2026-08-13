$ErrorActionPreference = "Stop"

# Build the Python API into the filename Tauri expects for the current target.
# API keys are read at runtime by the Tauri host; this executable contains no
# credentials or user data.
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\")).Path
$targetTriple = "x86_64-pc-windows-msvc"
$outputDir = Join-Path $repoRoot "src-tauri\bin"
$name = "wishforge-sidecar-$targetTriple"
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

Push-Location $repoRoot
try {
  python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name $name `
    --paths backend `
    --collect-submodules app `
    --collect-submodules uvicorn `
    --collect-submodules pydantic `
    --distpath $outputDir `
    --workpath (Join-Path $repoRoot "artifacts\pyinstaller") `
    --specpath (Join-Path $repoRoot "artifacts\pyinstaller") `
    backend\sidecar.py
} finally {
  Pop-Location
}

Write-Host "Built $name.exe in $outputDir"
