$ErrorActionPreference = "Stop"

Write-Host "Stopping llama-server..." -ForegroundColor Yellow
Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | ForEach-Object {
  try {
    $_.CloseMainWindow()
    if (!$_.HasExited) {
      Stop-Process $_ -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  Stopped process ID: $($_.Id)" -ForegroundColor Gray
  } catch {
    Write-Host "  Warning: Could not stop process $($_.Id)" -ForegroundColor Yellow
  }
}
Start-Sleep -Seconds 1
Write-Host "Stop complete." -ForegroundColor Green
