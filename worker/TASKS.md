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

- [ ] **CK-5**  Spin up RTX 4090 pod + 100 GB network volume (EU-RO-1)
- [ ] **CK-6**  Sync `worker/` to pod, `docker build` the multi-stage image
- [ ] **CK-7**  Smoke-test image: `python -c "from pipeline import process_job"`
- [ ] **CK-8**  Fix any build errors (CUDA / torch / uv.lock mismatch)

## M3 — End-to-end testing on pod (mostly sequential)

- [ ] **CK-9**   `pipeline.py` CLI run on `source/sample_official.mp4` (`--max-frames 6`)
- [ ] **CK-10**  `rp_handler.py --rp_serve_api` + `curl` with `test_input.json`
- [ ] **CK-11**  Verify every output format: `comp_mp4`, `comp_preview`, `fg_zip`, `matte_zip`, `processed_zip`
- [ ] **CK-12**  Perf report: s/frame, peak VRAM, image disk usage

## M4 — Serverless deploy (sequential)

- [ ] **CK-13**  `docker push` to GHCR (fallback: Docker Hub)
- [ ] **CK-14**  `runpodctl tpl create --serverless`
- [ ] **CK-15**  `runpodctl sls create` (+ optional network volume)
- [ ] **CK-16**  `/runsync` + `/run` smoke with `test_input.json`
- [ ] **CK-17**  End-user README with endpoint ID, example payloads, pricing note
