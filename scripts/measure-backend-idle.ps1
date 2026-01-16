$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$logDir = Join-Path $repoRoot "data\perf"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stdoutLog = Join-Path $logDir "backend_idle.stdout.log"
$stderrLog = Join-Path $logDir "backend_idle.stderr.log"
$metricsLog = Join-Path $logDir "backend_idle.log"

function Get-EventCount {
  param([string]$dbPath)
  if (-not (Test-Path $dbPath)) {
    return $null
  }
  $count = python -c "import sqlite3,sys; db=sys.argv[1]; conn=sqlite3.connect(db); cur=conn.execute('select count(*) from events'); print(cur.fetchone()[0]); conn.close()" $dbPath
  return [int]$count
}

$start = Get-Date
Add-Content -Path $metricsLog -Value "$($start.ToString('s'))`tbackend_idle_measure_start"

$env:MYGPT_STARTUP_LOG = Join-Path $logDir "backend_startup.log"

$proc = Start-Process python -ArgumentList @(
  "-m",
  "uvicorn",
  "src.backend.app:app",
  "--host",
  "127.0.0.1",
  "--port",
  "8000"
) -WorkingDirectory $repoRoot -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

$dbPath = Join-Path $repoRoot "data\chat.db"
$eventCountBefore = $null
$eventCountAfter = $null

try {
  for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 200
    try {
      $resp = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health -TimeoutSec 1
      if ($resp.StatusCode -eq 200) { break }
    } catch {}
  }

  $eventCountBefore = Get-EventCount -dbPath $dbPath
  $procInfoBefore = Get-Process -Id $proc.Id
  Start-Sleep -Seconds 60
  $eventCountAfter = Get-EventCount -dbPath $dbPath
  $procInfoAfter = Get-Process -Id $proc.Id
}
finally {
  if ($proc -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
  }
}

$cpuDeltaSec = $null
if ($procInfoBefore -and $procInfoAfter) {
  $cpuDeltaSec = [math]::Round(($procInfoAfter.CPU - $procInfoBefore.CPU), 4)
}

$workingSetMb = $null
$workingSetBytes = $null
if ($procInfoAfter) {
  $workingSetBytes = $procInfoAfter.WorkingSet64
  $workingSetMb = [math]::Round($workingSetBytes / 1MB, 2)
}

$deltaEvents = $null
if ($eventCountBefore -ne $null -and $eventCountAfter -ne $null) {
  $deltaEvents = $eventCountAfter - $eventCountBefore
}

$end = Get-Date
$lines = @(
  "$($end.ToString('s'))`tbackend_idle_cpu_delta_sec=$cpuDeltaSec",
  "$($end.ToString('s'))`tbackend_idle_working_set_mb=$workingSetMb",
  "$($end.ToString('s'))`tbackend_idle_working_set_bytes=$workingSetBytes",
  "$($end.ToString('s'))`tbackend_idle_events_delta=$deltaEvents"
)
$lines | ForEach-Object { Add-Content -Path $metricsLog -Value $_ }

Write-Output ("backend_idle_cpu_delta_sec={0}" -f $cpuDeltaSec)
Write-Output ("backend_idle_working_set_mb={0}" -f $workingSetMb)
Write-Output ("backend_idle_events_delta={0}" -f $deltaEvents)
