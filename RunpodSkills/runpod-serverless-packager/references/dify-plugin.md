# Dify Plugin Pattern

## Tool responsibility

A Dify plugin should hide RunPod mechanics from the workflow:

```text
Dify input video URL
-> plugin builds RunPod payload
-> plugin submits /run
-> plugin polls /status
-> plugin returns normalized URLs and metadata
```

## Tool inputs

Recommended schema:

| Field | Type | Required | Default |
|---|---|---:|---|
| `video_url` | string | yes | - |
| `clip_name` | string | no | `dify_job` |
| `mode` | enum | no | `final` |
| `image_size` | number | no | `1024` |
| `max_frames` | number | no | null |
| `despill_strength` | number | no | `0.5` |
| `despeckle_size` | number | no | `400` |

## RunPod payload

For full final deliverables:

```json
{
  "input": {
    "clip_name": "dify_job",
    "video": {
      "url": "https://content.example/input.mp4",
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

## Polling

Use async `/run`, not `/runsync`, for real videos:

```text
POST /run -> id
GET /status/{id} every 15-30s
```

Stop on:

```text
COMPLETED
FAILED
CANCELLED
```

## Normalized output for Dify

Return:

```json
{
  "preview_video_url": ".../comp.mp4",
  "transparent_mov_url": ".../transparent.mov",
  "transparent_webm_url": ".../transparent.webm",
  "fg_zip_url": ".../FG.zip",
  "matte_zip_url": ".../Matte.zip",
  "processed_zip_url": ".../Processed.zip",
  "preview_png_url": ".../comp_preview.png",
  "metadata": {
    "frame_count": 145,
    "fps": 24,
    "execution_ms": 67591
  }
}
```

## Error handling

| Case | Action |
|---|---|
| `/run` has no `id` | fail with raw response |
| `FAILED` | surface worker error and traceback |
| `CANCELLED` | retry once, then fail |
| `workers.throttled=1` | retry later or use fallback endpoint |
| output URLs missing | fail; do not silently accept base64 truncation |

## Documentation handoff

Commit:

- plugin README
- exact payload examples
- sample client script
- endpoint/image record
- output URL manifest from a real smoke job
