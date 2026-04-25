# Output Contracts

## Default production rule

Do not return large binary artifacts inline in the RunPod response.

Return URLs when artifacts can exceed a few MB. Use inline base64 only for
short smoke tests or small preview images.

## Recommended response shape

```json
{
  "status": "success",
  "metadata": {
    "frame_count": 300,
    "fps": 30,
    "device": "cuda",
    "inference_seconds": 442.239,
    "total_seconds": 491.332
  },
  "outputs": {
    "preview_video_url": "https://...",
    "preview_image_url": "https://...",
    "transparent_video_mov_url": "https://...",
    "transparent_video_webm_url": "https://...",
    "foreground_zip_url": "https://...",
    "matte_zip_url": "https://...",
    "processed_zip_url": "https://..."
  }
}
```

## Preview vs alpha deliverables

Use two layers of output:

1. **Preview**
   - H.264 MP4
   - browser-compatible
   - no alpha

2. **Production alpha**
   - ProRes 4444 MOV for editorial/compositing
   - WebM VP9 alpha for browser transparency
   - foreground/matte zip sequences for exact downstream control

## Artifact upload environment

Configure the RunPod template with:

```text
BUCKET_ENDPOINT_URL
BUCKET_NAME
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
S3_REGION
S3_PUBLIC_BASE_URL
S3_PREFIX
```

Never print or commit secrets. Record only the public output URLs and the
environment variable names needed.

## Validation

For videos:

```powershell
ffprobe -v error -show_entries stream=codec_name,pix_fmt,width,height,nb_frames <url>
```

For WebM alpha:

```powershell
ffprobe -v error -show_entries stream_tags=alpha_mode -of json <url>
```

For CDN uploads:

```powershell
curl.exe -L -I --max-time 20 <url>
```

Expect `200 OK` and correct `Content-Type`.
