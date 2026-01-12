param(
  [string]$ModelUrl = $(if ($env:MYGPT_MODEL_URL) { $env:MYGPT_MODEL_URL } else { "http://127.0.0.1:8080" }),
  [string]$BackendHost = "127.0.0.1",
  [int]$BackendPort = 8000,
  [int]$ModelMaxTokens = $(if ($env:MYGPT_N_PREDICT) { [int]$env:MYGPT_N_PREDICT } else { 256 }),
  [switch]$DisableLlmLogging,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
$backendUrl = "http://$BackendHost`:$BackendPort"

$pythonPath = (Get-Command python -ErrorAction Stop).Source
$npmPath = (Get-Command npm -ErrorAction Stop).Source

$backendCommand = @"
`$env:MYGPT_MODEL_URL = '$ModelUrl'
`$env:MYGPT_N_PREDICT = '$ModelMaxTokens'
`$env:MYGPT_LOG_LLM = '$(if ($DisableLlmLogging) { '0' } else { '1' })'
`$env:MYGPT_REASONING_FORMAT = '$(if ($env:MYGPT_REASONING_FORMAT) { $env:MYGPT_REASONING_FORMAT } else { 'none' })'
& '$pythonPath' -m uvicorn src.backend.app:app --reload --host $BackendHost --port $BackendPort
"@

$uiCommand = @"
Set-Location '$repoRoot\src\ui'
`$env:VITE_BACKEND_URL = '$backendUrl'
& '$npmPath' run tauri dev
"@

if ($DryRun) {
  Write-Host "Repo root: $repoRoot"
  Write-Host ""
  Write-Host "[Backend]"
  Write-Host $backendCommand
  Write-Host ""
  Write-Host "[UI]"
  Write-Host $uiCommand
  exit 0
}

Set-Location $repoRoot

Write-Host "Starting backend ($backendUrl) with model at $ModelUrl ..."
$backendProcess = Start-Process -FilePath "pwsh" -WorkingDirectory $repoRoot -PassThru -ArgumentList @(
  "-NoProfile",
  "-NoExit",
  "-Command",
  $backendCommand
)

Write-Host "Starting UI (Tauri + Vite) ..."
$uiProcess = Start-Process -FilePath "pwsh" -WorkingDirectory "$repoRoot\src\ui" -PassThru -ArgumentList @(
  "-NoProfile",
  "-NoExit",
  "-Command",
  $uiCommand
)

Write-Host ""
Write-Host "Started:"
Write-Host "- Backend PID: $($backendProcess.Id)"
Write-Host "- UI PID: $($uiProcess.Id)"
Write-Host ""
Write-Host "Close the two spawned terminal windows to stop dev mode."
