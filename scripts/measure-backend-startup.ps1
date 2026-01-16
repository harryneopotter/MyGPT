$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$logPath = $env:MYGPT_STARTUP_LOG
if (-not $logPath -or $logPath.Trim().Length -eq 0) {
  $logPath = Join-Path $repoRoot "data\perf\backend_startup.log"
}

$logDir = Split-Path -Parent $logPath
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stdoutLog = Join-Path $logDir "backend_startup.stdout.log"
$stderrLog = Join-Path $logDir "backend_startup.stderr.log"

$start = Get-Date
$startStamp = $start.ToString("s")
Add-Content -Path $logPath -Value "$startStamp`tstartup_script_invoke"

$beforeCount = 0
if (Test-Path $logPath) {
  $beforeCount = (Get-Content -Path $logPath).Count
}

$env:MYGPT_STARTUP_LOG = $logPath

$proc = Start-Process python -ArgumentList @(
  "-m",
  "uvicorn",
  "src.backend.app:app",
  "--host",
  "127.0.0.1",
  "--port",
  "8000"
) -WorkingDirectory $repoRoot -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

$readyStamp = $null
try {
  for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Milliseconds 250
    if (Test-Path $logPath) {
      $lines = Get-Content -Path $logPath
      if ($lines.Count -gt $beforeCount) {
        $latest = $lines[-1]
        $parts = $latest -split "`t"
        if ($parts.Count -ge 2 -and $parts[1] -eq "backend_startup") {
          $readyStamp = [datetime]::Parse($parts[0])
          break
        }
      }
    }
  }
}
finally {
  if ($proc -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
  }
}

if ($readyStamp) {
  $deltaMs = [math]::Round(($readyStamp - $start).TotalMilliseconds, 1)
  Write-Output "backend_startup_ms=$deltaMs"
  Add-Content -Path $logPath -Value "$($readyStamp.ToString('s'))`tbackend_startup_ms=$deltaMs"
} else {
  Write-Output "backend_startup_ms=timeout"
}
