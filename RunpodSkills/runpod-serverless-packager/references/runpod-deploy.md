# RunPod Deployment and GPU Price Testing

## Preflight

Check:

```powershell
runpodctl gpu list
runpodctl template get <template-id>
runpodctl serverless get <endpoint-id>
```

For price fields not shown by `runpodctl gpu list`, query RunPod GraphQL:

```graphql
{
  gpuTypes {
    id
    displayName
    memoryInGb
    securePrice
    communityPrice
    secureCloud
    communityCloud
  }
}
```

## Template

Create or update a serverless template:

```powershell
runpodctl template create `
  --name "<worker-name>" `
  --image "<registry/image:tag>" `
  --serverless `
  --container-disk-in-gb 30 `
  --env "<json>"
```

PowerShell often mangles JSON for `--env`. If needed, escape quotes:

```powershell
$envJson = '{"KEY":"VALUE"}'
$escaped = '"' + $envJson.Replace('"','\"') + '"'
runpodctl template update <template-id> --env $escaped
```

## Endpoint

Create:

```powershell
runpodctl serverless create `
  --name "<endpoint-name>" `
  --template-id "<template-id>" `
  --gpu-id "NVIDIA RTX 6000 Ada Generation" `
  --workers-min 0 `
  --workers-max 1
```

Use `workersMin=0` for cost control. Increase only for latency-sensitive services.

## Invoke

Submit:

```powershell
$headers = @{
  Authorization = "Bearer $env:RUNPOD_API_KEY"
  "Content-Type" = "application/json"
}
Invoke-RestMethod `
  -Method POST `
  -Uri "https://api.runpod.ai/v2/<endpoint-id>/run" `
  -Headers $headers `
  -Body $payloadJson
```

Poll:

```powershell
Invoke-RestMethod `
  -Method GET `
  -Uri "https://api.runpod.ai/v2/<endpoint-id>/status/<job-id>" `
  -Headers @{ Authorization = "Bearer $env:RUNPOD_API_KEY" }
```

Health:

```powershell
Invoke-RestMethod `
  -Method GET `
  -Uri "https://api.runpod.ai/v2/<endpoint-id>/health" `
  -Headers @{ Authorization = "Bearer $env:RUNPOD_API_KEY" }
```

## GPU comparison method

Use the same:

- image tag
- input URL
- settings
- output formats
- workers max
- RunPod region if possible

Record:

```text
gpu_id
endpoint_id
job_id
delay_ms
execution_ms
worker health
frame_count
inference_seconds
output URLs
estimated cost
```

Estimate cost:

```text
execution_seconds * hourly_price / 3600
```

If RunPod billing lags, keep the estimate and mark it as catalog-based.

## Cleanup

Delete comparison endpoints once a winner is chosen:

```powershell
runpodctl serverless delete <endpoint-id>
```

Keep one active production endpoint and document it in `deploy/endpoint.json`.
