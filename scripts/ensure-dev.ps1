$ErrorActionPreference = "Stop"

param(
  [string]$ModelKey = "",
  [string]$BackendHost = "127.0.0.1",
  [int]$BackendPort = 8000,
  [int]$UiPort = 1420,
  [switch]$SkipLlama,
  [switch]$SkipBackend,
  [switch]$SkipUi,
  [switch]$DryRun
)

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$modelConfig = Join-Path $repoRoot "model-switch\\models.json"
$modelSwitchScript = Join-Path $repoRoot "model-switch\\model_switcher.ps1"

function Test-Port {
  param([int]$Port)
  try {
    $null = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
    return $true
  } catch {
    return $false
  }
}

function Get-ModelConfig {
  if (-not (Test-Path $modelConfig)) {
    throw "Missing model config: $modelConfig"
  }
  return (Get-Content $modelConfig -Raw | ConvertFrom-Json)
}

$config = Get-ModelConfig
$defaultKey = $config.default_model_key
$selectedKey = if ($ModelKey) { $ModelKey } else { $defaultKey }
$modelEntry = $config.models | Where-Object { $_.key -eq $selectedKey } | Select-Object -First 1
if (-not $modelEntry) {
  throw "Unknown model key: $selectedKey"
}

$modelUrl = $config.model_url
$uri = [Uri]$modelUrl
$llamaPort = $uri.Port

if (-not $SkipLlama) {
  if (Test-Port -Port $llamaPort) {
    Write-Host "llama.cpp already running on port $llamaPort"
  } else {
    Write-Host "Starting llama.cpp with model '$selectedKey' on port $llamaPort..."
    if ($DryRun) {
      Write-Host "pwsh -File `"$modelSwitchScript`" -Model `"$($modelEntry.gguf_path)`""
    } else {
      & pwsh -File $modelSwitchScript -Model $modelEntry.gguf_path
    }
  }
}

if (-not $SkipBackend) {
  if (Test-Port -Port $BackendPort) {
    Write-Host "Backend already running on port $BackendPort"
  } else {
    Write-Host "Starting backend on port $BackendPort..."
    if ($DryRun) {
      Write-Host "MYGPT_MODEL_URL=$modelUrl python -m uvicorn src.backend.app:app --host $BackendHost --port $BackendPort"
    } else {
      $pythonPath = (Get-Command python -ErrorAction Stop).Source
      $backendCommand = @"
`$env:MYGPT_MODEL_URL = '$modelUrl'
& '$pythonPath' -m uvicorn src.backend.app:app --reload --host $BackendHost --port $BackendPort
"@
      Start-Process -FilePath "pwsh" -WorkingDirectory $repoRoot -ArgumentList @(
        "-NoProfile",
        "-NoExit",
        "-Command",
        $backendCommand
      ) | Out-Null
    }
  }
}

if (-not $SkipUi) {
  if (Test-Port -Port $UiPort) {
    Write-Host "UI already running on port $UiPort"
  } else {
    Write-Host "Starting UI (Tauri + Vite) on port $UiPort..."
    if ($DryRun) {
      Write-Host "npm run tauri dev (in $repoRoot\\src\\ui)"
    } else {
      $npmPath = (Get-Command npm -ErrorAction Stop).Source
      $uiCommand = @"
Set-Location '$repoRoot\\src\\ui'
`$env:VITE_BACKEND_URL = 'http://$BackendHost`:$BackendPort'
& '$npmPath' run tauri dev
"@
      Start-Process -FilePath "pwsh" -WorkingDirectory "$repoRoot\\src\\ui" -ArgumentList @(
        "-NoProfile",
        "-NoExit",
        "-Command",
        $uiCommand
      ) | Out-Null
    }
  }
}

Write-Host "Ensure-dev complete."
