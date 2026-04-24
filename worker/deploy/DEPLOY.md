# CorridorKey RunPod Serverless — Deployment Runbook

End-to-end instructions to publish the worker image and spin up a RunPod
Serverless endpoint that accepts the [input schema](../README.md#input-schema)
documented in `worker/README.md`.

> Everything below assumes the repository already exists at
> `github.com/<owner>/corridorkey-runpod-worker` with the contents of
> `worker/` + `CorridorKey_src/`. If you forked/renamed, substitute the
> tag and repo wherever they appear.

---

## 0. One-time: GitHub repo & registry access

1. Push the project to a GitHub repo that you control.
2. Make sure your user / org has **Packages → Container registry** enabled
   (it is on by default for public accounts).
3. The first publish by `GITHUB_TOKEN` creates the package automatically;
   no PAT needed for public images.

The workflow lives at `ci/docker-publish.yml.template` rather than
`.github/workflows/` because our OAuth session did not have the `workflow`
scope. Copy (or move) it into place once:

```bash
git mv ci/docker-publish.yml.template .github/workflows/docker-publish.yml
git commit -m "chore: enable docker-publish workflow"
git push
```

A user with a browser session (which implicitly has `workflow`) can also
just rename the file in the GitHub UI and commit via the web editor.

See [`ci/README.md`](../../ci/README.md) for the full activation walkthrough.

---

## 1. Build & push the image

The workflow is triggered manually — "Actions" tab → **Build & Publish
CorridorKey Worker** → **Run workflow**.

Inputs (safe defaults already set):

| Input | Default | Meaning |
|-------|---------|---------|
| `skip_model_prefetch` | `1` | `1` = weights fetched at runtime (slim image, slow first cold start). `0` = weights baked into the image (~15 GB, fast cold start). |
| `corridorkey_ref` | `main` | Git ref of `nikopueringer/CorridorKey` to clone inside the image. Pin to a commit SHA for reproducibility. |

The GHA runner uses `jlumbroso/free-disk-space@main` to free ~30 GB before
building; with `skip_model_prefetch=0` you need that headroom.

Expected completion: ~12 min (slim) / ~25 min (prefetched weights).

The image lands at `ghcr.io/<owner>/corridorkey-runpod-worker:<tag>` with
three tag forms published:

- `latest` (only for `main`)
- `sha-<short>` (always)
- `<ref>` (branch or tag name)

Verify:

```bash
docker pull ghcr.io/<owner>/corridorkey-runpod-worker:latest
docker inspect ghcr.io/<owner>/corridorkey-runpod-worker:latest | jq '.[0].Size'
```

---

## 2. Create the RunPod template + endpoint

Prereqs:

```powershell
runpodctl -v           # must be v2.x
runpodctl doctor       # confirms API key is stored (or export RUNPOD_API_KEY)
```

Provision in one shot:

```powershell
cd worker\deploy
.\runpodctl_deploy.ps1 `
    -ImageTag ghcr.io/<owner>/corridorkey-runpod-worker:latest `
    -TemplateName corridorkey-worker-v1 `
    -EndpointName corridorkey-endpoint `
    -GpuId "NVIDIA GeForce RTX 4090" `
    -WorkersMin 0 `
    -WorkersMax 1 `
    -ContainerDiskGb 30 `
    -DataCenterIds "EU-RO-1"
```

The script prints `template_id`, `endpoint_id`, and the three REST URLs.
Everything is also saved to `worker/deploy/endpoint.json` for your
records.

Notes on the environment variables injected by the template:

| Variable | Purpose |
|----------|---------|
| `CORRIDORKEY_DEVICE=auto` | Picks CUDA when available, CPU otherwise. |
| `CORRIDORKEY_JOB_ROOT=/tmp/corridorkey_jobs` | Per-job scratch dir; wiped between invocations. |
| `MAX_INLINE_MP4_BYTES=83886080` | 80 MB limit on base64 payloads returned inline — anything bigger must go to S3 (see §4). |
| `OPENCV_IO_ENABLE_OPENEXR=1` | Required for BiRefNet's alpha-hint exports. |
| `HF_HUB_DISABLE_TELEMETRY=1` | Quiet HuggingFace. |
| `HF_HUB_ENABLE_HF_TRANSFER=1` | Uses `hf_transfer` for faster weight downloads. |

If you baked the weights into the image (`skip_model_prefetch=0`), bump
`-ContainerDiskGb` to at least `50` so the worker doesn't OOD on disk.

---

## 3. Smoke test the endpoint

```powershell
cd worker\deploy
.\smoke_test.ps1 -EndpointId <endpoint_id>
```

This reads `worker/test_input.json`, POSTs to `/run`, polls `/status`
until the job reaches a terminal state (up to 15 min by default), then
decodes `comp_mp4_base64` / `comp_preview_png_base64` / the zip blobs
into `worker/deploy/smoke_out/`.

First invocation (cold start) expected timing — `skip_model_prefetch=1`,
RTX 4090, 6 frames @ 512 px:

| Phase | ~Seconds |
|-------|----------|
| Image pull | 60–120 |
| `pipeline.py` + CorridorKey import | 5 |
| Model prefetch (HF → local cache) | 45–60 |
| Inference + Alpha + Stitch | 90–130 |
| **Total first job** | **~3–5 min** |
| **Warm subsequent job** | **~80–100 s** |

If `skip_model_prefetch=0` was used at build time, subtract the
prefetch phase.

---

## 4. (Optional) Large-output offload to S3

By default the worker embeds `comp.mp4`, `Processed.zip`, `Matte.zip`,
`FG.zip` as base64 inside the `/status` response. Anything over
`MAX_INLINE_MP4_BYTES` is dropped with a warning. To get durable URLs
instead, set these on the endpoint (RunPod UI → **Endpoint → Environment**
or `runpodctl serverless update`):

| Variable | Example |
|----------|---------|
| `BUCKET_NAME` | `corridorkey-outputs` |
| `BUCKET_ENDPOINT_URL` | `https://s3api-eu-ro-1.runpod.io` |
| `AWS_ACCESS_KEY_ID` | RunPod S3 key |
| `AWS_SECRET_ACCESS_KEY` | RunPod S3 secret |
| `S3_REGION` | `eu-ro-1` |

See the [runpod-s3-access skill](https://github.com/gercheg/cursor-skills)
for how to obtain credentials. Once configured, outputs are uploaded and
the response contains `comp_mp4_url` / `processed_zip_url` / etc instead
of the base64 fields.

---

## 5. Updating the image

The workflow is re-runnable. To redeploy:

1. Run **Build & Publish CorridorKey Worker** again with the new SHA.
2. Update the template's image tag in RunPod UI (or create a new
   template and point the endpoint at it). `latest` updates don't force
   RunPod to pull — bump the tag or toggle the endpoint.

---

## 6. Troubleshooting cheatsheet

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `workers: throttled` forever | Image tag does not exist or is private | Re-run GHA workflow / make package public |
| `AlphaHint was produced` failures | Old image without the `trust_remote_code=True` patch | Rebuild — `Dockerfile` applies the `sed` patch in the `deps` stage |
| `output_formats` missing | Older `rp_handler.py` contract | Update worker to >= commit `9177bc9` (accepts top-level and nested `output_formats`) |
| First job times out | Cold start longer than client timeout | Use `/run` + `/status` polling, or set `WorkersMin=1` (always-on) |
| `comp.mp4` missing from response | File bigger than `MAX_INLINE_MP4_BYTES` | Configure S3 offload (§4) or reduce `max_frames` / `scene_size_px` |

---

## 7. Current deploy status (this repo)

As of the latest local run (`worker/deploy/endpoint.json`):

- Template `corridorkey-worker-v1` → id `4we83sqxqn`
- Endpoint `corridorkey-endpoint` → id `a72mhm1kdwsvoh`
- Image `ghcr.io/gercheg/corridorkey-runpod-worker:latest` — **not yet
  published**; workflow activation is waiting for a push with `workflow`
  OAuth scope (see `ci/README.md`).
- `/health` confirms the endpoint is reachable:

  ```json
  { "jobs": {"inQueue": 0}, "workers": {"throttled": 1} }
  ```

  The `throttled` worker is RunPod back-pressuring because image pull
  fails. As soon as the image exists it will flip to `ready`.
