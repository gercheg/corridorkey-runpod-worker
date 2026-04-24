# M3 — CorridorKey end-to-end smoke run

Worker: `197fn14tqy0md6` (RTX 4090, EU-RO-1) — NOT deleted.
Date: 2026-04-24
Runner: Ops subagent.

## Phase results

| Phase | Name | Result | Notes |
|-------|------|--------|-------|
| A | Model prefetch | PASS | CorridorKey_v1.0.safetensors downloaded (383 MB); BiRefNet General already cached (429 MB). 109 s total. |
| B | CLI smoke via `process_job()` | PASS (with patch) | First run failed because `BiRefNetModule/wrapper.py` passes `trust_remote_code=False` to `AutoModelForImageSegmentation.from_pretrained` — ZhengPeng7/BiRefNet ships custom code and refuses to load. Patched locally (`sed -i 's/trust_remote_code=False/trust_remote_code=True/'`). After patch, 4-frame run on `sample_extra.mp4` (512 px, General) completed in 328.15 s wall, 270.79 s inference. |
| C | `rp_handler.py --rp_serve_api` + `/runsync` | PASS | Server bound to :8000, processed the same payload in **114.3 s wall / 75.7 s inference** (warm torch.inductor cache, BiRefNet re-init per job). Response size: 7.75 MB. All 5 `output_formats` present. |
| D | Decode & verify every format | PASS | `comp_mp4` decodes as H.264, 640×360, 30 fps, 4 packets, 0.133 s. `comp_preview_png` has valid PNG magic. `processed_zip`, `matte_zip`, `fg_zip` each contain 4 `0000N.exr` entries. |
| E | Perf | PASS | Peak VRAM 2,834 MiB (≈ 2.77 GiB). Full numbers below. |
| F | Summary | PASS | This file. |

`M3_RESULT: PASS`

## Phase B — CLI `process_job()` final metadata (4 frames)

```json
{
  "status": "success",
  "metadata": {
    "clip_name": "sample_extra_cli",
    "frame_count": 4,
    "input_frames": 300,
    "alpha_frames": 300,
    "input_kind": "video",
    "device": "cuda",
    "settings": {
      "input_is_linear": false,
      "despill_strength": 0.5,
      "auto_despeckle": true,
      "despeckle_size": 400,
      "refiner_scale": 1.0,
      "image_size": 512,
      "alpha_source": "auto"
    },
    "inference_seconds": 270.794,
    "fps": 30.0,
    "total_seconds": 328.148
  },
  "comp_preview_png_base64": "<7200 chars>",
  "comp_mp4_base64":         "<2424 chars>",
  "comp_mp4_path":           "/workspace/ck_job_cli/ClipsForInference/sample_extra_cli/Output/sample_extra_cli_comp.mp4",
  "output_dir":              "/workspace/ck_job_cli/ClipsForInference/sample_extra_cli/Output"
}
```

Note: the CLI-level smoke request passed `output_formats` at the top of the
payload (mirroring the M3 task brief), but `pipeline.process_job` only reads
`output_formats` out of the `settings` dict — so the CLI slot defaulted to
`["comp_mp4", "comp_preview"]`. Phase C fixes this by also placing the list
inside `settings`.

## Phase C — first 40 lines of `output.metadata` from `/runsync`

```json
{
  "id": "test-99622986-d529-416d-8e5f-0faf53b9e7fb",
  "status": "COMPLETED",
  "output": {
    "status": "success",
    "metadata": {
      "clip_name": "clip_c1dfc86c",
      "frame_count": 4,
      "input_frames": 300,
      "alpha_frames": 300,
      "input_kind": "video",
      "device": "cuda",
      "settings": {
        "input_is_linear": false,
        "despill_strength": 0.5,
        "auto_despeckle": true,
        "despeckle_size": 400,
        "refiner_scale": 1.0,
        "image_size": 512,
        "alpha_source": "auto"
      },
      "inference_seconds": 75.71,
      "fps": 30.0,
      "total_seconds": 114.344
    },
    "comp_preview_png_base64": "<base64 len=7200>",
    "comp_mp4_base64": "<base64 len=2424>",
    "comp_mp4_path": "/tmp/corridorkey_jobs/job_test-99622986-d529-416d-8e5f-0faf53b9e7fb/ClipsForInference/clip_c1dfc86c/Output/clip_c1dfc86c_comp.mp4",
    "fg_zip_base64": "<base64 len=5952832>",
    "matte_zip_base64": "<base64 len=1618564>",
    "processed_zip_base64": "<base64 len=170332>",
    "output_dir": "/tmp/corridorkey_jobs/job_test-99622986-d529-416d-8e5f-0faf53b9e7fb/ClipsForInference/clip_c1dfc86c/Output"
  }
}
```

## Output sizes — decoded bytes on disk (Phase C response)

| Format | Base64 length | Decoded bytes |
|--------|---------------|---------------|
| `comp_mp4_base64`          |     2 424 |     1 818 |
| `comp_preview_png_base64`  |     7 200 |     5 398 |
| `processed_zip_base64`     |   170 332 |   127 747 |
| `matte_zip_base64`         | 1 618 564 | 1 213 921 |
| `fg_zip_base64`            | 5 952 832 | 4 464 622 |
| **Total payload**          | 7 751 352 | 5 813 506 |

## Zip contents

All three zips hold the same 4 frames at 640×360 (`00000.exr` … `00003.exr`), OpenEXR floating point:

| Zip | Per-frame bytes (avg) |
|-----|-----------------------|
| `processed_zip` | ~34 kB (sRGB + baked matte) |
| `matte_zip`     | ~303 kB (alpha channel) |
| `fg_zip`        | ~1.12 MB (unpremultiplied RGBA) |

## Phase C — `ffprobe serve_comp.mp4`

```
[STREAM]
codec_name=h264
width=640
height=360
r_frame_rate=30/1
duration=0.133333
nb_read_packets=4
[/STREAM]
[FORMAT]
duration=0.133333
bit_rate=109080
```

## Perf table

| Metric | CLI (Phase B, cold) | `/runsync` (Phase C, warm) |
|--------|---------------------|----------------------------|
| Frames processed | 4 | 4 |
| Source fps | 30 | 30 |
| Image size | 512 | 512 |
| BiRefNet usage | General | General |
| `inference_seconds` (pipeline) | 270.79 | 75.71 |
| `total_seconds` (pipeline) | 328.15 | 114.34 |
| Wall-clock (bash) | 436 s (incl. import + compile) | 114 s |
| Wall-clock / frame | ~109 s | ~28.6 s |
| Pipeline s/frame (inference) | 67.70 | 18.93 |
| Peak VRAM (MiB) | n/a (not sampled) | 2 834 |

The huge gap between Phase B and Phase C is the torch.inductor / triton AUTOTUNE compilation step on first run (≈ 180 s) + first-ever BiRefNet weight materialization. Phase C hits the `.venv/lib/python*/site-packages/torch` inductor cache and the warm HF cache, so only BiRefNet eval setup and the 4-frame inference actually cost time.

## Disk footprint (pod)

| Path | Size |
|------|------|
| `/workspace/CorridorKey/CorridorKeyModule/checkpoints` | 383 MB |
| `/workspace/CorridorKey/BiRefNetModule/checkpoints`    | 429 MB |
| `/workspace/CorridorKey/.venv`                         | 11 GB |
| `/workspace/source`                                    | 12 MB |
| `/workspace/ck_outputs`                                | 7.5 MB |
| `/workspace/ck_job_cli`                                | 22 MB |

Network volume `/workspace` is 2.1 PiB total, 1.4 PiB used (67 %) — we have plenty of headroom.

## Billing

- Pod created: 2026-04-24 10:53:46 UTC.
- Now: 2026-04-24 11:47 UTC.
- Billed so far: ≈ 0.89 h × $0.69/hr ≈ **$0.61**.
- Projected at $0.69/hr: $5.52 for 8 h, $16.56 for 24 h.

## Local artifacts

Everything pulled from the pod into `d:\Work\RunpodProjects\KorridorKey\worker\artifacts\`:

```
worker\artifacts\
├── ck_outputs\
│   ├── serve_comp.mp4              (1,818 B — H.264 640x360 30fps 4 frames)
│   ├── serve_comp_preview.png      (5,398 B — valid PNG)
│   ├── serve_processed.zip         (127,747 B — 4× EXR)
│   ├── serve_matte.zip             (1,213,921 B — 4× EXR)
│   └── serve_fg.zip                (4,464,622 B — 4× EXR)
├── cli_smoke.py                    # Python driver used in Phase B
├── inspect.py                      # dumps keys of /runsync response
├── strip.py                        # removes base64 bodies from response
├── verify.py                       # decodes + checks every format
├── test_payload_serve.json         # payload used against /runsync
├── serve_response_slim.json        # /runsync response with base64 redacted
├── download_full.log               # Phase A
├── cli_run.log                     # Phase B
├── rp_serve.log                    # Phase C server log
└── vram_trace.log                  # nvidia-smi sample-every-3s trace
```

## Pod-side patches applied

Only one file was modified on the pod:

```
/workspace/CorridorKey/BiRefNetModule/wrapper.py
- self.birefnet = AutoModelForImageSegmentation.from_pretrained(model_local_dir, trust_remote_code=False)
+ self.birefnet = AutoModelForImageSegmentation.from_pretrained(model_local_dir, trust_remote_code=True)
```

This is upstream CorridorKey code — the patch should be upstreamed or shimmed
in the worker before the Dockerfile build in M4. Without it the pipeline
aborts at alpha-hint generation with `JobError("Alpha generation finished but
no AlphaHint was produced")`.

No files outside `/workspace/` or `/tmp/` were touched on the pod.
No local files outside `d:\Work\RunpodProjects\KorridorKey\worker\` were touched.

## Follow-ups for M4

1. Either patch `BiRefNetModule/wrapper.py` into a vendored subclass, or
   export `HF_HUB_TRUST_REMOTE_CODE=1` / monkey-patch in `download_models.py`
   before the Dockerfile rebuild.
2. Consider warm-starting the pipeline once inside the container image so
   the torch.inductor cache (autotune for BiRefNet) is baked in. That alone
   cuts the first request from 7 min → ~2 min.
3. The `output_formats` contract is only honoured under `input.settings.output_formats`;
   the top-level key in the task brief is silently ignored. Either accept
   both or document loudly.
4. `comp_mp4` on 4 frames at 30 fps is 0.13 s long. For real clips we'll
   hit `MAX_INLINE_MP4_BYTES=80 MB` quickly — M4 should wire
   `BUCKET_ENDPOINT_URL` so big outputs upload to S3 instead of inlining.

---

`M3_RESULT: PASS`