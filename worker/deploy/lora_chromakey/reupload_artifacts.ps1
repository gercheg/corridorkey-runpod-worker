param(
    [string]$EndpointUrl = "https://8455919443be3d65a8515d77fde32b8f.r2.cloudflarestorage.com",
    [string]$Profile = "r2-loremax",
    [string]$Bucket = "loremax",
    [string]$Prefix = "Demos/CorridorKey/lora_chromakey"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

$files = @(
    @{
        Local = Join-Path $root "lora_start_frame_pure_green_flood.png"
        Key = "$Prefix/lora_start_frame_pure_green.png"
        ContentType = "image/png"
    },
    @{
        Local = Join-Path $root "lora_corridorkey_comp.mp4"
        Key = "$Prefix/lora_corridorkey_comp.mp4"
        ContentType = "video/mp4"
    },
    @{
        Local = Join-Path $root "lora_corridorkey_preview.png"
        Key = "$Prefix/lora_corridorkey_preview.png"
        ContentType = "image/png"
    }
)

foreach ($item in $files) {
    if (-not (Test-Path $item.Local)) {
        Write-Warning "Skipping missing local file: $($item.Local)"
        continue
    }

    aws s3 cp $item.Local "s3://$Bucket/$($item.Key)" `
        --content-type $item.ContentType `
        --endpoint-url $EndpointUrl `
        --profile $Profile

    Write-Host "https://content.loremax.ai/$($item.Key)"
}
