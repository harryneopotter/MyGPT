# Model Switcher for llama.cpp Server
# Allows replacing the current model without changing ports

$ErrorActionPreference = "Stop"

# Configuration
$LLAMA_SERVER = if ($env:LLAMA_SERVER -and $env:LLAMA_SERVER.Trim().Length -gt 0) { $env:LLAMA_SERVER } else { "F:\Users\Neo\AppData\Roaming\Jan\data\engines\llama.cpp\win-vulkan-x64\b5857\llama-server.exe" }
$DEFAULT_MODEL = if ($env:LLAMA_DEFAULT_MODEL -and $env:LLAMA_DEFAULT_MODEL.Trim().Length -gt 0) { $env:LLAMA_DEFAULT_MODEL } else { "D:\local\mradermacher\Nemotron-Orchestrator-8B-Claude-4.5-Opus-Distill-i1-GGUF\Nemotron-Orchestrator-8B-Claude-4.5-Opus-Distill.i1-Q4_K_S.gguf" }
$PORT = if ($env:LLAMA_PORT -and $env:LLAMA_PORT.Trim().Length -gt 0) { [int]$env:LLAMA_PORT } else { 8081 }
$CTX_SIZE = if ($env:LLAMA_CTX_SIZE -and $env:LLAMA_CTX_SIZE.Trim().Length -gt 0) { [int]$env:LLAMA_CTX_SIZE } else { 4096 }
$THREADS = if ($env:LLAMA_THREADS -and $env:LLAMA_THREADS.Trim().Length -gt 0) { [int]$env:LLAMA_THREADS } else { 8 }
$PARALLEL = if ($env:LLAMA_PARALLEL -and $env:LLAMA_PARALLEL.Trim().Length -gt 0) { [int]$env:LLAMA_PARALLEL } else { 2 }
$CONT_BATCHING = if ($env:LLAMA_CONT_BATCHING -and $env:LLAMA_CONT_BATCHING.Trim().Length -gt 0) { $env:LLAMA_CONT_BATCHING } else { "1" }
$MAX_WAIT_SECONDS = if ($env:LLAMA_MAX_WAIT_SECONDS -and $env:LLAMA_MAX_WAIT_SECONDS.Trim().Length -gt 0) { [int]$env:LLAMA_MAX_WAIT_SECONDS } else { 120 }

function Stop-LLamaServer {
    Write-Host "Stopping current llama-server..." -ForegroundColor Yellow
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
    Start-Sleep -Seconds 2
}

function Start-LLamaServer {
    param(
        [string]$ModelPath
    )
    
    if (-not (Test-Path $ModelPath)) {
        throw "Model not found: $ModelPath"
    }
    
    Write-Host "Starting llama-server with model: $ModelPath" -ForegroundColor Cyan
    
    $args = @(
        "-m", $ModelPath,
        "--host", "127.0.0.1",
        "--port", "$PORT",
        "--ctx-size", "$CTX_SIZE",
        "--threads", "$THREADS"
    )
    if ($PARALLEL -gt 0) {
        $args += @("--parallel", "$PARALLEL")
    }
    if ($CONT_BATCHING -ne "0") {
        $args += "--cont-batching"
    }
    
    $process = Start-Process -FilePath $LLAMA_SERVER -ArgumentList $args -PassThru -NoNewWindow -RedirectStandardOutput "$env:TEMP\llama_out_$PORT.txt" -RedirectStandardError "$env:TEMP\llama_err_$PORT.txt"
    
    Write-Host "  Started process ID: $($process.Id)" -ForegroundColor Gray
    return $process
}

function Wait-ForServerReady {
    param(
        [int]$Port = 8081,
        [int]$Timeout = $MAX_WAIT_SECONDS
    )
    
    $url = "http://127.0.0.1:$Port/health"
    $waited = 0
    
    Write-Host "Waiting for server to be ready..." -ForegroundColor Gray
    
    while ($waited -lt $Timeout) {
        try {
            $response = Invoke-RestMethod -Uri $url -Method GET -TimeoutSec 2
            if ($response -and $response.status -eq "ok") {
                Write-Host "  Server is ready!" -ForegroundColor Green
                return $true
            }
        } catch [System.Net.WebException] {
            # Expected - server not ready yet
        } catch {
            Write-Host "  Error: $_" -ForegroundColor Red
            return $false
        }
        
        Start-Sleep -Seconds 2
        $waited += 2
        
        if ($waited -ge $Timeout) {
            Write-Host "  Timeout waiting for server!" -ForegroundColor Red
            return $false
        }
        
        Write-Host "    Still waiting... ($waited/$Timeout seconds)" -ForegroundColor Gray
    }
    
    return $false
}

function Switch-LLModel {
    param(
        [string]$ModelPath,
        [int]$Port = 8081,
        [switch]$Force
    )
    
    # Check if model exists
    if (-not (Test-Path $ModelPath)) {
        Write-Host "ERROR: Model not found: $ModelPath" -ForegroundColor Red
        return $false
    }
    
    # Check if server is running
    $serverRunning = $false
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -Method GET -TimeoutSec 2
        $serverRunning = $true
    } catch {
        # Server not running
    }
    
    # If same model is already running, do nothing
    if ($serverRunning) {
        # llama.cpp server does not expose current model path by default, so we always switch.
    }
    
    # Stop current server
    Stop-LLamaServer
    
    # Start new server
    try {
        $process = Start-LLamaServer -ModelPath $ModelPath
        
        # Wait for server to be ready
        if (-not (Wait-ForServerReady -Port $Port)) {
            Write-Host "ERROR: Server failed to start" -ForegroundColor Red
            return $false
        }
        
        Write-Host "Model switched successfully to: $ModelPath" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "ERROR: Failed to start server: $_" -ForegroundColor Red
        return $false
    }
}

# Example usage
if ($MyInvocation.InvocationName -eq '.') {
    # This script is being run directly
    
    Write-Host @"
╔══════════════════════════════════════════════════════════════╗
║           llama.cpp Model Switcher                         ║
║                                                             ║
║  Usage: .\model_switcher.ps1 -Model "path/to/model.gguf"  ║
║                                                             ║
║  Examples:                                                  ║
║    .\model_switcher.ps1 -Model "D:\models\nemotron.gguf" ║
║    .\model_switcher.ps1 -Model "D:\models\phinance.gguf"  ║
╚══════════════════════════════════════════════════════════════╝
"@ -ForegroundColor Cyan
    
    param(
        [Parameter(Mandatory=$true)]
        [string]$Model
    )
    
    Switch-LLModel -ModelPath $Model
}
