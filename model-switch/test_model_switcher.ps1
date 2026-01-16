#!/usr/bin/env powershell
# Test script for model switcher

$ErrorActionPreference = "Stop"

# Import the model switcher module
. .\model_switcher.ps1

Write-Host @"
╔══════════════════════════════════════════════════════════════╗
║          Model Switcher Test Script                         ║
║                                                             ║
║  This script tests the model switching functionality.      ║
║  It will:                                                     ║
║    1. Start with default model (Nemotron)                    ║
║    2. Switch to a different model (if available)             ║
║    3. Switch back to default                                 ║
║                                                             ║
╚══════════════════════════════════════════════════════════════╝
"@ -ForegroundColor Cyan

# Configuration
$DEFAULT_MODEL = "D:\local\mradermacher\Nemotron-Orchestrator-8B-Claude-4.5-Opus-Distill-i1-GGUF\Nemotron-Orchestrator-8B-Claude-4.5-Opus-Distill.i1-Q4_K_S.gguf"
$ALTERNATIVE_MODEL = "D:\Local\blobs\sha256-7a5d10279b3be88cf473878bda54dc4980fc791be59f26bac21572e83c4fa402"

# Check if models exist
if (-not (Test-Path $DEFAULT_MODEL)) {
    Write-Host "ERROR: Default model not found: $DEFAULT_MODEL" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ALTERNATIVE_MODEL)) {
    Write-Host "WARNING: Alternative model not found: $ALTERNATIVE_MODEL" -ForegroundColor Yellow
    Write-Host "  Test will only verify default model startup" -ForegroundColor Yellow
    $test_alternative = $false
} else {
    $test_alternative = $true
}

# Test 1: Start default model
Write-Host "`n[TEST 1] Starting default model..." -ForegroundColor Green
if (Switch-LLModel -ModelPath $DEFAULT_MODEL) {
    Write-Host "✅ Default model started successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to start default model" -ForegroundColor Red
    exit 1
}

# Test 2: Verify server is responding
Write-Host "`n[TEST 2] Verifying server is responding..." -ForegroundColor Green
try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:8081/health" -Method GET -TimeoutSec 5
    if ($response.status -eq "ok") {
        Write-Host "✅ Server is responding correctly" -ForegroundColor Green
    } else {
        Write-Host "❌ Server returned unexpected status: $($response.status)" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ Failed to connect to server: $_" -ForegroundColor Red
    exit 1
}

# Test 3: Switch to alternative model (if available)
if ($test_alternative) {
    Write-Host "`n[TEST 3] Switching to alternative model..." -ForegroundColor Green
    if (Switch-LLModel -ModelPath $ALTERNATIVE_MODEL) {
        Write-Host "✅ Switched to alternative model successfully" -ForegroundColor Green
        
        # Verify the switch
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:8081/health" -Method GET -TimeoutSec 5
            if ($response.status -eq "ok") {
                Write-Host "✅ Alternative model is responding" -ForegroundColor Green
            }
        } catch {
            Write-Host "❌ Alternative model not responding: $_" -ForegroundColor Red
            exit 1
        }
        
        # Test 4: Switch back to default
        Write-Host "`n[TEST 4] Switching back to default model..." -ForegroundColor Green
        if (Switch-LLModel -ModelPath $DEFAULT_MODEL) {
            Write-Host "✅ Switched back to default model successfully" -ForegroundColor Green
        } else {
            Write-Host "❌ Failed to switch back to default model" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "❌ Failed to switch to alternative model" -ForegroundColor Red
        exit 1
    }
}

# Test 5: Verify final state
Write-Host "`n[TEST 5] Verifying final state..." -ForegroundColor Green
try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:8081/health" -Method GET -TimeoutSec 5
    if ($response.status -eq "ok") {
        Write-Host "✅ Server is in good state" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ Server not responding in final state: $_" -ForegroundColor Red
    exit 1
}

# Summary
Write-Host @"
╔══════════════════════════════════════════════════════════════╗
║                    TEST SUMMARY                              ║
╚══════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Cyan

if ($test_alternative) {
    Write-Host "✅ All tests passed (including model switching)" -ForegroundColor Green
} else {
    Write-Host "✅ Basic tests passed (alternative model not available)" -ForegroundColor Green
}

Write-Host "`nThe model switcher is working correctly!" -ForegroundColor Green
