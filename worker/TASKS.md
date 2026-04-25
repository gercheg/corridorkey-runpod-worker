# CorridorKey RunPod Worker — Task Tracker

Source of truth for milestone/issue status. Linear Project:
<https://linear.app/loremax/project/corridorkey-runpod-worker-56dc121d07d1>

> Linear workspace hit its free issue-creation quota (only Project + 4 milestones were created).
> Detailed issues are tracked here; progress is mirrored into the Linear Project description.

Legend: `[ ]` pending · `[~]` in-progress · `[x]` done · `[!]` blocked.

## M1 — Scaffolding & sanity (parallel)

- [x] **CK-1** Audit `worker/` vs CorridorKey: 11/12 PASS. Fix: removed `.webm` from `VIDEO_EXTS` in `pipeline.py`.
- [x] **CK-2** `worker/README.md` (227 lines, 10 sections)
- [x] **CK-3** `source/` populated with `sample_official.mp4` (Pexels CC0 substitute, 8.4 MB, 1920x1080@25 fps) and `sample_extra.mp4` (Big Buck Bunny CC-BY, 0.95 MB) + `CHECKSUMS.txt` + `MANIFEST.json`. Note: original URLs in plan returned 404/403; substitutes are valid MP4 but not true green-screen — OK for smoke tests, NOT for visual QA.
- [x] **CK-4** `git init` + `.gitignore` + first commit `3d0dc0b`

## M2 — Docker build on RunPod pod (sequential)

- [x] **CK-5**  Pod `197fn14tqy0md6` (RTX 4090, EU-RO-1, Secure Cloud, 2.1 PiB `/workspace`). SSH: `root@213.173.108.96:12208`.
- [x] **CK-6**  Clone+native install (`uv venv` + `uv sync --extra cuda`) used for fast iteration on the pod; Docker build deferred to M4 CI. 11 GB `.venv`, torch 2.8.0+cu128, runpod 1.9.0.
- [x] **CK-7**  Smoke imports OK: `from pipeline import process_job`, `from rp_handler import handler`.
- [x] **CK-8**  No build errors. One upstream defect found during M3 (see M3 below): `BiRefNetModule/wrapper.py` hard-codes `trust_remote_code=False` → fixed in Dockerfile.

## M3 — End-to-end testing on pod (mostly sequential)

- [x] **CK-9**   `process_job()` smoke on `sample_extra.mp4` via `.venv` CLI: 4 frames, 512 px, 328.15 s wall / 270.79 s inference (cold — first-run torch.inductor autotune).
- [x] **CK-10**  `rp_handler.py --rp_serve_api` + `/runsync` curl: 114.3 s wall / 75.7 s inference warm. 7.75 MB response. See `worker/M3_SUMMARY.md`.
- [x] **CK-11**  All 5 formats decoded and verified: `comp_mp4` (H.264 640×360 30 fps 4 pkts), `comp_preview_png`, `processed_zip`/`matte_zip`/`fg_zip` (each 4× `0000N.exr`).
- [x] **CK-12**  Perf: warm ≈ 18.9 s/frame inference, 28.6 s/frame wall. Peak VRAM 2,834 MiB. Disk: models 812 MB, `.venv` 11 GB.

**Fixups applied post-M3 (before M4):**
- Dockerfile: `sed` patch on `BiRefNetModule/wrapper.py` to flip `trust_remote_code=False` → `True`.
- `pipeline.py::process_job`: accept `output_formats` at top level of job_input as a fallback (settings-level key still primary).
- `.gitignore`: exclude `worker/artifacts/` (pod-side run artefacts).

## M4 — Serverless deploy (sequential)

- [~] **CK-13**  GHCR publish via GitHub Actions — workflow staged at `ci/docker-publish.yml.template` with manual inputs (`skip_model_prefetch`, `corridorkey_ref`). Blocked on OAuth `workflow` scope; activate via `ci/README.md`. **Workaround used during M4:** built locally (`docker buildx build --platform linux/amd64 …`) and pushed to anonymous ttl.sh tag `ttl.sh/corridorkey-gercheg-984225:24h` — proves the Dockerfile is correct end-to-end on a real RunPod worker.
- [x] **CK-14**  Template `corridorkey-worker-v1` → id `4we83sqxqn`. All 7 env vars attached (see `worker/deploy/endpoint.json`). Reusable via `worker/deploy/runpodctl_deploy.ps1`.
- [x] **CK-15**  Endpoint `corridorkey-endpoint` → id `a72mhm1kdwsvoh` on RTX 4090 / EU-RO-1, workers min 0 / max 2 (bumped from 1 to clear a hung unhealthy pod after the CRLF bug).
- [x] **CK-16**  `/run` smoke **PASSED** end-to-end with the rebuilt image. Job `ea490cb0-ae8a-45ab-9deb-4fe0e8a47f87-e2`: cold image-pull 103 s, queue→exec 177.3 s, in-handler 29.35 s, output `comp_mp4` (h264 640×360 6 frames, 3369 B) + `comp_preview_png` (5398 B) decoded to `worker/deploy/smoke_out/`. Pure inference 5.485 s on RTX 4090.
- [x] **CK-17**  User-facing runbook: `worker/deploy/DEPLOY.md` + scripted path `runpodctl_deploy.ps1` / `smoke_test.ps1`; main `worker/README.md` now links to both.

**M4 status:** infrastructure complete and end-to-end verified against the live RunPod endpoint. The `ttl.sh` image expires ~2026-04-26 10:14 UTC; for permanent deployment activate the GHA workflow (`ci/README.md`) or push to your own registry per `worker/deploy/DEPLOY.md` and re-run `runpodctl template update 4we83sqxqn --image <tag>`.

### Critical post-M3 bug discovered & fixed during M4

**Symptom:** First two RunPod smoke jobs timed out in `IN_QUEUE`; worker entered `running=1` for ~60 s then flipped to `unhealthy=1` with empty `/stream` and `/status` payload.

**Root cause:** `worker/start.sh` was checked out with Windows CRLF line endings on the developer machine. Inside the Linux container, `/usr/bin/env bash` interpreted the trailing `\r` as part of the executable name and crashed before the handler could even import:

```
/usr/bin/env: 'bash\r': No such file or directory
```

**Fixes (both committed):**
- `worker/Dockerfile`: `RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh` after the `COPY start.sh` line — defends in depth even if the bug recurs.
- `.gitattributes` at repo root: forces `*.sh`, `*.bash`, `Dockerfile`, `*.dockerfile` to LF on every checkout so it cannot recur.

Verified locally with `docker run --rm -e SERVE_API_LOCALLY=true … <image>` (handler boots cleanly, FastAPI listens on :8000), then re-pushed (~10 s — only 2 small layers changed) and re-tested on RunPod (success documented above).
