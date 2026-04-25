# Dify Plugin Integration: Loremax -> CorridorKey -> RunPod

This document is the implementation guide for a Dify plugin/tool that sends a
video to the CorridorKey RunPod Serverless worker, waits for processing, and
returns usable final artifacts to a Dify workflow.

Recommended production endpoint after GPU price testing:

```text
RUNPOD_ENDPOINT_ID=ca60ckj57xfzzz
GPU=NVIDIA RTX 6000 Ada Generation (48 GB)
Template=4we83sqxqn
```

The previous H100 / RTX PRO 6000 endpoint remains as historical baseline, but
new Dify integrations should default to the RTX 6000 Ada 48GB endpoint because
it was faster on the 300-frame test and about 5-6x cheaper by catalog pricing.

## Important Production Note

Template `4we83sqxqn` now points at the permanent DockerHub image:

```text
gercheg/corridorkey-runpod-worker:transparent-alpha
```

Published tags:

```text
gercheg/corridorkey-runpod-worker:transparent-alpha
gercheg/corridorkey-runpod-worker:20260425-transparent-alpha
gercheg/corridorkey-runpod-worker:latest
```

Digest:

```text
sha256:d3abe4cd1aeb215b1c338a99c7d4bccdc06372779395a82599ed0fbae0f1be05
```

Verified transparent-output smoke job:

```text
job_id=98344961-9483-49c3-a104-becd4089cc1b-e2
status=COMPLETED
delay_ms=9983
execution_ms=67591
```

Published outputs:

- Preview MP4: <https://content.loremax.ai/Demos/CorridorKey/runpod_outputs/98344961-9483-49c3-a104-becd4089cc1b-e2/comp.mp4>
- Transparent ProRes MOV: <https://content.loremax.ai/Demos/CorridorKey/runpod_outputs/98344961-9483-49c3-a104-becd4089cc1b-e2/transparent.mov>
- Transparent VP9 WebM: <https://content.loremax.ai/Demos/CorridorKey/runpod_outputs/98344961-9483-49c3-a104-becd4089cc1b-e2/transparent.webm>
- FG zip: <https://content.loremax.ai/Demos/CorridorKey/runpod_outputs/98344961-9483-49c3-a104-becd4089cc1b-e2/FG.zip>
- Matte zip: <https://content.loremax.ai/Demos/CorridorKey/runpod_outputs/98344961-9483-49c3-a104-becd4089cc1b-e2/Matte.zip>
- Processed zip: <https://content.loremax.ai/Demos/CorridorKey/runpod_outputs/98344961-9483-49c3-a104-becd4089cc1b-e2/Processed.zip>
- Preview PNG: <https://content.loremax.ai/Demos/CorridorKey/runpod_outputs/98344961-9483-49c3-a104-becd4089cc1b-e2/comp_preview.png>

DockerHub-image smoke job:

```text
job_id=29a2a55a-b799-4c74-affe-0e1203e30a02-e2
status=COMPLETED
delay_ms=65917
execution_ms=39143
```

## End-to-End Workflow

The full production workflow has three logical stages:

1. **Generate or receive input video**
   - Dify receives a video URL from Loremax generation, user upload, or any
     public HTTPS URL.
   - The video must be accessible by the RunPod worker.

2. **Call CorridorKey RunPod endpoint**
   - Dify plugin submits `POST /run` with the payload documented below.
   - Plugin polls `GET /status/{jobId}` until `COMPLETED`, `FAILED`, or
     `CANCELLED`.

3. **Normalize final outputs for downstream Dify nodes**
   - For normal preview / review: return `comp_mp4_url` or decode
     `comp_mp4_base64`.
   - For alpha/transparent workflows: request `transparent_mov`,
     `transparent_webm`, `fg_zip`, `matte_zip`, and `processed_zip`.

## What Format Does CorridorKey Return?

The current worker can return both browser preview video and alpha-carrying
video files.

Current available outputs:

| Output | Format | Alpha? | Use |
|---|---|---:|---|
| `comp_mp4_base64` / `comp_mp4_url` | H.264 MP4, `yuv420p` | No | Fast preview / review / playback in browser |
| `transparent_mov_base64` / `transparent_mov_url` | ProRes 4444 MOV, `yuva444p10le` | Yes | Production/editorial transparent video |
| `transparent_webm_base64` / `transparent_webm_url` | VP9 WebM, `alpha_mode=1` | Yes | Browser-friendly transparent video |
| `comp_preview_png_base64` | PNG first frame from `Output/Comp` | Depends on upstream PNG, but treat as preview | UI thumbnail |
| `fg_zip_base64` / `fg_zip_url` | ZIP of foreground image sequence | Usually RGB/RGBA foreground | High-quality downstream compositing |
| `matte_zip_base64` / `matte_zip_url` | ZIP of matte/alpha frames | Yes, matte data | Build transparency / masks |
| `processed_zip_base64` / `processed_zip_url` | ZIP of processed frames | Pipeline intermediate | Debug / advanced compositing |

Why `comp_mp4` has no transparency:

- The worker stitches `Output/Comp/*.png` with ffmpeg:

  ```text
  ffmpeg -framerate <fps> -i %05d.png -c:v libx264 -pix_fmt yuv420p -crf 18 out.mp4
  ```

- H.264 `yuv420p` does not carry alpha.
- This is intentional because it plays everywhere, including Dify UI and
  browsers.

If Dify needs complete deliverables:

1. Request:

   ```json
   "output_formats": [
     "comp_mp4",
     "comp_preview",
     "transparent_mov",
     "transparent_webm",
     "fg_zip",
     "matte_zip",
     "processed_zip"
   ]
   ```

2. Use:
   - `comp_mp4` for preview/review.
   - `transparent_mov` for production compositing.
   - `transparent_webm` for browser preview with alpha.
   - `fg_zip` + `matte_zip` for exact per-frame downstream compositing.

Recommended Dify output contract:

```json
{
  "preview_video_url": "<comp mp4 URL or uploaded decoded MP4>",
  "transparent_video_mov_url": "<ProRes 4444 MOV URL>",
  "transparent_video_webm_url": "<VP9 alpha WebM URL>",
  "preview_image_url": "<preview PNG URL>",
  "alpha_assets": {
    "foreground_zip_url": "<FG.zip URL>",
    "matte_zip_url": "<Matte.zip URL>",
    "processed_zip_url": "<Processed.zip URL>"
  },
  "metadata": {
    "frame_count": 300,
    "fps": 30,
    "execution_ms": 492803
  }
}
```

## RunPod HTTP Contract

Base URL:

```text
https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}
```

Headers:

```http
Authorization: Bearer ${RUNPOD_API_KEY}
Content-Type: application/json
```

Submit:

```http
POST /run
```

Poll:

```http
GET /status/{jobId}
```

Health:

```http
GET /health
```

## Payload Sent to RunPod (Preview MP4 Only)

This is the exact shape currently used for the 300-frame comparison run:

```json
{
  "input": {
    "clip_name": "dify_corridorkey_comp_example",
    "video": {
      "url": "https://content.loremax.ai/data/2026/04/08/iC9PX90tXlsL.mp4",
      "filename": "input.mp4"
    },
    "settings": {
      "alpha_source": "birefnet",
      "birefnet_usage": "General",
      "birefnet_dilate": 0,
      "input_is_linear": false,
      "despill_strength": 0.5,
      "auto_despeckle": true,
      "despeckle_size": 400,
      "refiner_scale": 1.0,
      "image_size": 1024,
      "generate_comp": true,
      "device": "auto",
      "output_formats": ["comp_mp4", "comp_preview"]
    }
  }
}
```

File:

```text
worker/deploy/dify_plugin/payloads/basic_comp_payload.json
```

## Payload Sent to RunPod (Final Deliverables)

Use this when Dify needs the full final package: preview MP4, transparent MOV,
transparent WebM, and all zip sequences.

```json
{
  "input": {
    "clip_name": "dify_corridorkey_alpha_assets_example",
    "video": {
      "url": "https://content.loremax.ai/data/2026/04/25/0DCiSFABlxtB.mp4",
      "filename": "lora_chromakey_gameplay.mp4"
    },
    "settings": {
      "alpha_source": "birefnet",
      "birefnet_usage": "General",
      "birefnet_dilate": 0,
      "input_is_linear": false,
      "despill_strength": 0.55,
      "auto_despeckle": true,
      "despeckle_size": 350,
      "refiner_scale": 1.0,
      "image_size": 1024,
      "generate_comp": true,
      "device": "auto",
      "output_formats": [
        "comp_mp4",
        "comp_preview",
        "transparent_mov",
        "transparent_webm",
        "fg_zip",
        "matte_zip",
        "processed_zip"
      ]
    }
  }
}
```

File:

```text
worker/deploy/dify_plugin/payloads/alpha_assets_payload.json
```

## Dify Plugin Tool Design

Create one plugin action/tool:

```text
tool name: corridorkey_process_video
description: Remove green screen / generate foreground and matte assets with CorridorKey on RunPod.
```

Recommended input schema:

| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `video_url` | string | yes | - | Public HTTPS input video |
| `clip_name` | string | no | `dify_corridorkey_job` | Used in metadata |
| `filename` | string | no | `input.mp4` | Helps extension sniffing |
| `mode` | enum | no | `preview` | `preview` or `alpha_assets` |
| `image_size` | number | no | `1024` | `512`, `1024`, `2048`; 1024 is best cost/speed |
| `despill_strength` | number | no | `0.5` | `0..1` |
| `despeckle_size` | number | no | `400` | Smaller for thin details |
| `max_frames` | number | no | null | Use for smoke tests |

Recommended output schema:

```json
{
  "status": "success",
  "runpod": {
    "endpoint_id": "ca60ckj57xfzzz",
    "job_id": "...",
    "delay_ms": 112687,
    "execution_ms": 492803
  },
  "outputs": {
    "preview_video_base64": "...",
    "preview_video_url": null,
    "preview_image_base64": "...",
    "foreground_zip_base64": null,
    "matte_zip_base64": null,
    "processed_zip_base64": null
  },
  "metadata": {
    "frame_count": 300,
    "fps": 30,
    "device": "cuda",
    "inference_seconds": 442.239,
    "total_seconds": 491.332
  }
}
```

For production, prefer worker-side S3 offload so Dify receives URLs instead of
large base64 payloads. Configure the RunPod template with:

```text
BUCKET_ENDPOINT_URL
BUCKET_NAME
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
S3_REGION
```

Then the worker can replace large inline base64 values with URL fields such as
`comp_mp4_url`, `fg_zip_url`, `matte_zip_url`.

## Python Script Wrapper

Reusable client:

```text
worker/deploy/dify_plugin/runpod_corridorkey_client.py
```

Smoke preview run:

```powershell
$env:RUNPOD_API_KEY = "<runpod-api-key>"
python worker\deploy\dify_plugin\runpod_corridorkey_client.py `
  --endpoint-id ca60ckj57xfzzz `
  --payload worker\deploy\dify_plugin\payloads\basic_comp_payload.json `
  --output-dir worker\deploy\dify_plugin\out_preview
```

Alpha-assets run:

```powershell
$env:RUNPOD_API_KEY = "<runpod-api-key>"
python worker\deploy\dify_plugin\runpod_corridorkey_client.py `
  --endpoint-id ca60ckj57xfzzz `
  --payload worker\deploy\dify_plugin\payloads\alpha_assets_payload.json `
  --output-dir worker\deploy\dify_plugin\out_alpha
```

Dynamic payload:

```powershell
python worker\deploy\dify_plugin\runpod_corridorkey_client.py `
  --endpoint-id ca60ckj57xfzzz `
  --video-url "https://content.loremax.ai/path/to/video.mp4" `
  --alpha-assets `
  --output-dir worker\deploy\dify_plugin\out_dynamic
```

## Dify Workflow Node Sequence

Recommended Dify workflow:

1. **Input node**
   - Receives `video_url`.

2. **Code/tool node: build payload**
   - Builds JSON from `video_url`, `mode`, and quality parameters.

3. **HTTP/tool node: submit RunPod**
   - `POST https://api.runpod.ai/v2/ca60ckj57xfzzz/run`
   - Body: payload above.
   - Save `job_id = response.id`.

4. **Loop / code node: poll RunPod**
   - Every `15-30s`, call:

     ```text
     GET https://api.runpod.ai/v2/ca60ckj57xfzzz/status/{job_id}
     ```

   - Stop when status is `COMPLETED`, `FAILED`, or `CANCELLED`.

5. **Output-normalization node**
   - If response contains URL fields, pass URLs downstream.
   - If response contains base64 fields, either:
     - pass base64 directly for small clips, or
     - upload decoded artifacts to Loremax CDN / R2 and pass URLs.

6. **Final Dify response**
   - Return preview video URL/base64, optional alpha assets, metadata, and timing.

## Error Handling

Handle these cases explicitly:

| Case | Meaning | Action |
|---|---|---|
| `/run` has no `id` | Invalid RunPod response | Fail node with raw response |
| `status=FAILED` | Worker raised error | Surface `output.error` / `traceback` if present |
| `status=CANCELLED` | Job cancelled or endpoint capacity issue | Retry on same endpoint once, then fail |
| `workers.throttled=1` | No capacity for selected GPU | Retry later; old expensive fallback endpoint has been deleted |
| `comp_mp4_base64` missing | Output too large and S3 offload not configured | Request alpha assets or configure S3 offload |

## Endpoint Choice

48GB comparison summary on the same 300-frame job:

| GPU | Endpoint | Execution | Cost estimate |
|---|---|---:|---:|
| RTX 6000 Ada 48GB | `ca60ckj57xfzzz` | `492.803s` | `$0.1013-$0.1054` |
| L40S 48GB | deleted | `535.696s` | `$0.1176-$0.1280` |
| RTX A6000 48GB | deleted | `615.544s` | `$0.0564-$0.0838` |
| A40 48GB | deleted | throttled | n/a |
| H100 / RTX PRO pool (deleted) | `a72mhm1kdwsvoh` | `508.810s` | `$0.5648-$0.5902` |

Keep `ca60ckj57xfzzz` as default. The old H100/RTX PRO endpoint has been deleted; this is now the only active CorridorKey endpoint.

## CI/CD Handoff

The Dify plugin should not depend on `ttl.sh`. CI/CD must publish a permanent
Docker image and update template `4we83sqxqn`.

Current repo state:

- GitHub workflow template: `ci/docker-publish.yml.template`
- Activation guide: `ci/README.md`
- Deployment runbook: `worker/deploy/DEPLOY.md`

Production release sequence:

1. Move `ci/docker-publish.yml.template` to `.github/workflows/docker-publish.yml`
   using a GitHub token with `workflow` scope.
2. Run the workflow and publish a permanent image tag.
3. Update the RunPod template:

   ```powershell
   runpodctl template update 4we83sqxqn --image <permanent-image-tag>
   ```

4. Smoke-test:

   ```powershell
   worker\deploy\smoke_test.ps1 -EndpointId ca60ckj57xfzzz
   ```

5. Point Dify plugin env `RUNPOD_ENDPOINT_ID` to `ca60ckj57xfzzz`.
