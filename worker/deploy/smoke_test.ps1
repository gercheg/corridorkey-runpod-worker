<#
.SYNOPSIS
    End-to-end smoke test for a CorridorKey RunPod Serverless endpoint.

.DESCRIPTION
    POSTs worker/test_input.json to /run on the given endpoint, polls
    /status until completion, prints the envelope (without the big base64
    bodies), and optionally decodes comp_mp4 and comp_preview to disk.

.PARAMETER EndpointId
    Serverless endpoint id (from runpodctl_deploy.ps1 output, e.g. a72mhm1kdwsvoh).

.PARAMETER RunpodApiKey
    Bearer token. Falls back to $env:RUNPOD_API_KEY, then to
    $env:USERPROFILE\.runpod\config.toml.

.PARAMETER PayloadPath
    Path to the JSON payload. Default: ./test_input.json in the repo.

.PARAMETER PollTimeoutSec
    Max seconds to poll /status before giving up. Default: 900 (15 min) —
    enough for cold-start + compile + inference on 6 frames.

.PARAMETER OutDir
    Where to write decoded comp_mp4 / comp_preview artefacts. Default:
    ./smoke_out.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string] $EndpointId,
    [string] $RunpodApiKey     = "",
    [string] $PayloadPath      = (Join-Path $PSScriptRoot "..\test_input.json"),
    [int]    $PollTimeoutSec   = 900,
    [string] $OutDir           = (Join-Path $PSScriptRoot "smoke_out")
)

$ErrorActionPreference = "Stop"

if (-not $RunpodApiKey -and $env:RUNPOD_API_KEY) { $RunpodApiKey = $env:RUNPOD_API_KEY }
if (-not $RunpodApiKey) {
    $cfg = Join-Path $env:USERPROFILE ".runpod\config.toml"
    if (Test-Path $cfg) {
        $line = Get-Content $cfg | Select-String "^\s*apikey"
        if ($line) { $RunpodApiKey = ($line -replace ".*'([^']+)'.*", '$1').Trim() }
    }
}
if (-not $RunpodApiKey) { throw "No RunPod API key. Pass -RunpodApiKey, set RUNPOD_API_KEY, or run 'runpodctl doctor'." }
if (-not (Test-Path $PayloadPath)) { throw "Payload not found: $PayloadPath" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$payload = Get-Content $PayloadPath -Raw
$headers = @{Authorization = "Bearer $RunpodApiKey"; "Content-Type" = "application/json"}
$base = "https://api.runpod.ai/v2/$EndpointId"

Write-Host "==> POST $base/run ($(($payload | Measure-Object -Character).Characters) chars)"
$job = Invoke-RestMethod -Method POST -Uri "$base/run" -Headers $headers -Body $payload -TimeoutSec 60
$jobId = $job.id
if (-not $jobId) { throw "No job id in response: $($job | ConvertTo-Json -Compress)" }
Write-Host "    job_id = $jobId, initial status = $($job.status)"

$started = Get-Date
while ((Get-Date) - $started -lt [TimeSpan]::FromSeconds($PollTimeoutSec)) {
    Start-Sleep -Seconds 5
    $st = Invoke-RestMethod -Method GET -Uri "$base/status/$jobId" -Headers $headers
    Write-Host ("[{0,5:0}s] status={1} delay={2} exec={3} worker={4}" -f ((Get-Date) - $started).TotalSeconds, $st.status, $st.delayTime, $st.executionTime, $st.workerId)
    if ($st.status -in 'COMPLETED','FAILED','CANCELLED') { break }
}

if (-not $st -or $st.status -notin 'COMPLETED','FAILED','CANCELLED') {
    throw "Job $jobId did not finish in $PollTimeoutSec s"
}

Write-Host ""
Write-Host "==> Final status: $($st.status)"
Write-Host "    delayTime  (ms): $($st.delayTime)"
Write-Host "    executionTime (ms): $($st.executionTime)"

if ($st.status -ne 'COMPLETED') {
    $st | ConvertTo-Json -Depth 8 | Write-Host
    exit 1
}

# Strip base64 blobs before printing
$body = $st.output
$slim = @{}
foreach ($k in $body.PSObject.Properties.Name) {
    $v = $body.$k
    if ($v -is [string] -and $v.Length -gt 1000) {
        $slim[$k] = "<base64 len=$($v.Length)>"
    } else {
        $slim[$k] = $v
    }
}
Write-Host ""
Write-Host "==> Response envelope (large fields redacted):"
$slim | ConvertTo-Json -Depth 6

# Decode MP4 + PNG if present
foreach ($pair in @(
    @{Key='comp_mp4_base64';       Out=(Join-Path $OutDir 'comp.mp4')},
    @{Key='comp_preview_png_base64';Out=(Join-Path $OutDir 'comp_preview.png')},
    @{Key='processed_zip_base64';  Out=(Join-Path $OutDir 'Processed.zip')},
    @{Key='matte_zip_base64';      Out=(Join-Path $OutDir 'Matte.zip')},
    @{Key='fg_zip_base64';         Out=(Join-Path $OutDir 'FG.zip')}
)) {
    $v = $body.($pair.Key)
    if ($v) {
        [IO.File]::WriteAllBytes($pair.Out, [Convert]::FromBase64String($v))
        $size = (Get-Item $pair.Out).Length
        Write-Host "    wrote $($pair.Out) ($size B)"
    }
}

Write-Host ""
Write-Host "SMOKE TEST OK: $OutDir"
