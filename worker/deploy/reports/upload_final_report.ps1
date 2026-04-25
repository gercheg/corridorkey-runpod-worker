param(
    [string]$ReportPath = (Join-Path $PSScriptRoot "corridorkey_runpod_final_report_20260425.html"),
    [string]$EndpointUrl = "https://8455919443be3d65a8515d77fde32b8f.r2.cloudflarestorage.com",
    [string]$Profile = "r2-loremax",
    [string]$Bucket = "loremax",
    [string]$Key = "Demos/CorridorKey/corridorkey_runpod_final_report_20260425.html"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ReportPath)) {
    throw "Report file not found: $ReportPath"
}

aws s3 cp $ReportPath "s3://$Bucket/$Key" `
    --content-type text/html `
    --endpoint-url $EndpointUrl `
    --profile $Profile

Write-Host "https://content.loremax.ai/$Key"
