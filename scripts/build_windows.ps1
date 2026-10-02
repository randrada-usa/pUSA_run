$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv. Run scripts\setup_windows.ps1 first."
}

$arguments = @(
    "--noconfirm"
    "--clean"
    "--windowed"
    "--name"
    "pUSA Run"
    "--add-data"
    "models;models"
    "--collect-all"
    "mediapipe"
    "run_game.py"
)

Push-Location $projectRoot
try {
    & $python -m pip install -r requirements-build.txt
    & $python -m PyInstaller @arguments
} finally {
    Pop-Location
}

Write-Host "Build complete: dist\pUSA Run\pUSA Run.exe"

