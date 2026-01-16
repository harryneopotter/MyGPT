param(
  [string]$Prompt = "Hello",
  [string]$BackendUrl = "http://127.0.0.1:8000",
  [string]$ExpectedModelUrl = "http://127.0.0.1:8081",
  [int]$ConversationId = 0
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$logDir = Join-Path $repoRoot "data\perf"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir "ttft.log"

$payload = @{
  content = $Prompt
}
if ($ConversationId -gt 0) {
  $payload.conversation_id = $ConversationId
}

$json = $payload | ConvertTo-Json -Depth 4

$client = [System.Net.Http.HttpClient]::new()
$client.Timeout = [TimeSpan]::FromSeconds(120)
$request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, "$BackendUrl/chat")
$request.Content = [System.Net.Http.StringContent]::new($json, [System.Text.Encoding]::UTF8, "application/json")

$start = Get-Date
Add-Content -Path $logPath -Value "$($start.ToString('s'))`tttft_start"
Add-Content -Path $logPath -Value "$($start.ToString('s'))`texpected_model_url=$ExpectedModelUrl"
Write-Output "Ensure backend is running with MYGPT_MODEL_URL=$ExpectedModelUrl"

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$response = $client.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).Result
$response.EnsureSuccessStatusCode() | Out-Null

$stream = $response.Content.ReadAsStreamAsync().Result
$reader = New-Object System.IO.StreamReader($stream)

$firstTokenMs = $null
try {
  while (-not $reader.EndOfStream) {
    $line = $reader.ReadLine()
    if (-not $line) { continue }
    if ($line.StartsWith("data:")) {
      $payloadLine = $line.Substring(5).Trim()
      if ($payloadLine.Length -gt 0) {
        $firstTokenMs = [math]::Round($stopwatch.Elapsed.TotalMilliseconds, 1)
        break
      }
    }
  }
} finally {
  $reader.Close()
  $response.Dispose()
  $client.Dispose()
}

if ($firstTokenMs -ne $null) {
  $now = Get-Date
  Add-Content -Path $logPath -Value "$($now.ToString('s'))`tttft_ms=$firstTokenMs"
  Write-Output "ttft_ms=$firstTokenMs"
} else {
  Write-Output "ttft_ms=timeout"
}
