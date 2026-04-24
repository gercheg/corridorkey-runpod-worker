<#
.SYNOPSIS
    Provision a RunPod Serverless endpoint for the CorridorKey worker.

.DESCRIPTION
    Creates a RunPod template pointing at a GHCR image, then creates a
    serverless endpoint on top of it. Idempotent if you re-use the same
    -TemplateName / -EndpointName with different IDs.

    Prereqs:
      * runpodctl v2+ on PATH (`runpodctl -v` reports v2.x)
      * RUNPOD_API_KEY stored via `runpodctl doctor` (or $env:RUNPOD_API_KEY)
      * The image tag exists at ghcr.io (pushed by GHA workflow in ci/)

.PARAMETER ImageTag
    Full GHCR image tag, e.g. `ghcr.io/gercheg/corridorkey-runpod-worker:latest`.

.PARAMETER TemplateName
    Human-readable template name. Default: corridorkey-worker-v1.

.PARAMETER EndpointName
    Serverless endpoint name. Default: corridorkey-endpoint.

.PARAMETER GpuId
    runpodctl GPU id. Default: "NVIDIA GeForce RTX 4090".

.PARAMETER WorkersMin
    Minimum always-on workers. Default: 0 (scale-from-zero).

.PARAMETER WorkersMax
    Scale-out ceiling. Default: 1.

.PARAMETER ContainerDiskGb
    Container disk per worker. Default: 30 (fits CUDA base + .venv + weights).
    Bump to 50 if you baked the full ~15 GB model layer.

.PARAMETER NetworkVolumeId
    Optional RunPod network volume ID for model caching when the image was
    built with SKIP_MODEL_PREFETCH=1.

.PARAMETER DataCenterIds
    Comma-separated RunPod DC IDs. Default: EU-RO-1 (matches M2/M3 pod).

.EXAMPLE
    .\runpodctl_deploy.ps1 -ImageTag ghcr.io/gercheg/corridorkey-runpod-worker:latest

.NOTES
    Because PowerShell eats double quotes when passing native args, the
    --env JSON is built with escaped quotes (\") so runpodctl sees a valid
    JSON object. Do NOT edit the $envJson escape pattern without testing.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string] $ImageTag,
    [string] $TemplateName      = "corridorkey-worker-v1",
    [string] $EndpointName      = "corridorkey-endpoint",
    [string] $GpuId             = "NVIDIA GeForce RTX 4090",
    [int]    $WorkersMin        = 0,
    [int]    $WorkersMax        = 1,
    [int]    $ContainerDiskGb   = 30,
    [string] $NetworkVolumeId   = "",
    [string] $DataCenterIds     = "EU-RO-1"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command runpodctl -ErrorAction SilentlyContinue)) {
    throw "runpodctl not found on PATH. Install it before running this script."
}

Write-Host "==> Creating template '$TemplateName' -> $ImageTag"

# PowerShell mangles JSON in native args; use backslash-escaped quotes so
# runpodctl receives `{"KEY":"VAL",...}` verbatim.
$envJson = '{\"CORRIDORKEY_DEVICE\":\"auto\",\"CORRIDORKEY_JOB_ROOT\":\"/tmp/corridorkey_jobs\",\"LOG_LEVEL\":\"INFO\",\"MAX_INLINE_MP4_BYTES\":\"83886080\",\"OPENCV_IO_ENABLE_OPENEXR\":\"1\",\"HF_HUB_DISABLE_TELEMETRY\":\"1\",\"HF_HUB_ENABLE_HF_TRANSFER\":\"1\"}'

$tplRaw = runpodctl template create `
    --name $TemplateName `
    --image $ImageTag `
    --serverless `
    --container-disk-in-gb $ContainerDiskGb `
    --env "$envJson" `
    2>&1
Write-Host $tplRaw

$tplJson = $tplRaw -join "`n" | ConvertFrom-Json
$templateId = $tplJson.id
if (-not $templateId) { throw "Failed to extract template id from runpodctl output" }
Write-Host "    template_id = $templateId"

Write-Host ""
Write-Host "==> Creating serverless endpoint '$EndpointName' on template $templateId"

$endpointArgs = @(
    "serverless", "create",
    "--name", $EndpointName,
    "--template-id", $templateId,
    "--gpu-id", $GpuId,
    "--gpu-count", "1",
    "--workers-min", "$WorkersMin",
    "--workers-max", "$WorkersMax",
    "--data-center-ids", $DataCenterIds
)
if ($NetworkVolumeId) { $endpointArgs += @("--network-volume-id", $NetworkVolumeId) }

$epRaw = & runpodctl @endpointArgs 2>&1
Write-Host $epRaw

$epJson = $epRaw -join "`n" | ConvertFrom-Json
$endpointId = $epJson.id
if (-not $endpointId) { throw "Failed to extract endpoint id from runpodctl output" }

Write-Host ""
Write-Host "================================================================"
Write-Host "SUCCESS"
Write-Host "    template_id  = $templateId"
Write-Host "    endpoint_id  = $endpointId"
Write-Host "    runsync_url  = https://api.runpod.ai/v2/$endpointId/runsync"
Write-Host "    run_url      = https://api.runpod.ai/v2/$endpointId/run"
Write-Host "    status_url   = https://api.runpod.ai/v2/$endpointId/status/<jobId>"
Write-Host "================================================================"
Write-Host ""
Write-Host "Run a smoke test with .\smoke_test.ps1 -EndpointId $endpointId"
