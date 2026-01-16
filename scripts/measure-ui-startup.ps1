$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$logDir = Join-Path $repoRoot "data\perf"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$logPath = Join-Path $logDir "ui_startup.log"
$start = Get-Date
Add-Content -Path $logPath -Value "$($start.ToString('s'))`tui_startup_invoke"

Write-Output "Starting UI (tauri dev). Close with Ctrl+C when done."
Push-Location (Join-Path $repoRoot "src\ui")
try {
  Start-Process npm -ArgumentList @("run", "tauri", "dev") -WorkingDirectory (Get-Location) | Out-Null
} finally {
  Pop-Location
}

Write-Output "Press Enter when the UI window is interactive."
Read-Host | Out-Null

$ready = Get-Date
$deltaMs = [math]::Round(($ready - $start).TotalMilliseconds, 1)
Add-Content -Path $logPath -Value "$($ready.ToString('s'))`tui_startup_ms=$deltaMs"
Write-Output "ui_startup_ms=$deltaMs"
