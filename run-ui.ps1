# Starts the backend and Expo UI app for local development on Windows.
# Usage: .\run-ui.ps1
$ErrorActionPreference = "Stop"
$RootDir = $PSScriptRoot

if (-not (Test-Path "$RootDir\.env")) {
    Write-Host "No .env found -- copying .env.example -> .env (DEMO_MODE=true)"
    Copy-Item "$RootDir\backend\.env.example" "$RootDir\.env"
}

# Load .env into process environment
Get-Content "$RootDir\.env" | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $name, $value = $_ -split '=', 2
    [System.Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim())
}
if (-not $env:DATA_DIR) { $env:DATA_DIR = "$RootDir\data" }

Write-Host "== Backend: checking conda env 'media-forensics' ==" -ForegroundColor Cyan
Set-Location "$RootDir\backend"
$envExists = conda env list | Select-String "^\s*media-forensics\s"
if (-not $envExists) {
    conda env create -f environment.yml
}

Write-Host "== Backend: starting FastAPI on :8000 (new window) ==" -ForegroundColor Cyan
$envSetLines = (Get-Content "$RootDir\.env" | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $name, $value = $_ -split '=', 2
    $name = $name.Trim(); $value = $value.Trim()
    "`$env:$name = " + "'" + ($value -replace "'", "''") + "'"
}) -join '; '
$envSetLines += "; `$env:DATA_DIR = '$($env:DATA_DIR)'"

Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$RootDir\backend'; conda activate media-forensics; $envSetLines; uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

Write-Host "== UI: checking npm dependencies ==" -ForegroundColor Cyan
Set-Location "$RootDir\UI"
if (-not (Test-Path "node_modules")) {
    npm install
}

Write-Host "== UI: starting Expo dev server ==" -ForegroundColor Cyan
npx expo start
