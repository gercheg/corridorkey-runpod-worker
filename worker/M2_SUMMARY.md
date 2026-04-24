# M2 Summary - CorridorKey RunPod Build

## Pod Info
- **POD_ID**: `197fn14tqy0md6`
- **Name**: corridorkey-build
- **Cloud**: SECURE (COMMUNITY had no capacity for RTX 4090 at request time)
- **Data Center**: EU-RO-1 (Romania)
- **GPU**: NVIDIA GeForce RTX 4090 (24 GB VRAM)
- **vCPU/RAM/Disk**: 16 vCPU / 61 GB RAM / 100 GB container + 50 GB /workspace volume
- **Cost**: `\.69/hr` (SECURE tier)
- **Created (UTC)**: 2026-04-24 10:53:46

## SSH Endpoint
- **Host**: `213.173.108.96`
- **Port**: `12208`
- **User**: `root`
- **Private key (used)**: `%USERPROFILE%\.ssh\id_ed25519` (fingerprint SHA256:iAGWCXFee3WWTJ9FTiFjWUlQMta/B1xtyqJXn5bxjeQ -> registered key `gercheggRunpod@gmail.com`)
- **Note**: `gerchegg@gmail.com` (primary) had no matching private key locally; used the secondary `gercheggRunpod` key instead; `C:\Users\gerch\.runpod\ssh\RunPod-Key-Go` exists but has Windows ACL issues (OpenSSH refuses the key).
- **Public IP support**: yes (supportPublicIp=true on machine)

### Re-SSH command (copy-paste)
`ssh -i %USERPROFILE%\.ssh\id_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL -p 12208 root@213.173.108.96`

## Environment on Pod
- Image: `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`
- Python: `3.12.3` (system); `3.13` (venv created by uv sync)
- NVIDIA driver: `580.95.05`; CUDA (runtime): `13.0`
- uv: `0.9.0` (preinstalled in image)
- torch: `2.8.0+cu128`; `torch.cuda.is_available() = True`; device = `NVIDIA GeForce RTX 4090`
- /workspace filesystem: `mfs#euro-2.runpod.net:9421` (~2.1 PB shared, 711 TB free)

## Workspace Layout (/workspace on pod)
- `CorridorKey/` - cloned from https://github.com/nikopueringer/CorridorKey.git at commit `422f9999d1d83323534d2da9d776086a3134050d`
- `worker/` - our code: `pipeline.py, rp_handler.py, download_models.py, start.sh, test_input.json`
- `source/` - test clips (`sample_official.mp4` 8.4 MB + `sample_extra.mp4` 968 KB + `CHECKSUMS.txt` + `MANIFEST.json` + `.gitkeep`)

## uv sync result
- `uv sync --frozen --no-dev --extra cuda` -> PASS (frozen lock honored, NO fallback needed).
- Followed by `uv pip install 'runpod>=1.7,<2' 'hf_transfer>=0.1.6' boto3` (runpod==1.9.0 installed).

## Smoke Test
- `from pipeline import ...` -> **OK** (`VERSION` attribute not present, but module imported cleanly; module exposes `process_job`).
- `import rp_handler` -> **OK**.
- Both imports took ~150 s total (dominated by torch cold import).

## Model Prefetch (BiRefNet General, --skip-corridorkey)
- HF snapshot_download succeeded (9 files fetched in 2.5 s once the auth warning was noted; total wall time 1m41s incl. first torch import).
- `BiRefNetModule/checkpoints/BiRefNet/model.safetensors`: **424 MB**
- Total `BiRefNetModule/checkpoints` size: **429 MB**
- `CorridorKeyModule/checkpoints` size: **512 bytes** (skipped; still empty placeholder).
- Logged to `/workspace/worker/download_models.log` on the pod.
- HF warned about missing `HF_TOKEN` (downloads worked anonymously, but M3 should set HF_TOKEN for higher rate limits).

## Uptime & Spend (approx.)
- Uptime at summary time: ~20 min (`0.34 h`).
- Spend so far: `0.69 * 0.34` ~= **`\.23`**.
- Budget remaining for M2+M3 (`\.00` cap): ~`\.77`, i.e. ~6.9 h of headroom at `\.69/hr`.

## Handover notes for M3
- Pod is alive and NOT to be deleted.
- CorridorKey venv lives at `/workspace/CorridorKey/.venv` (bin: `.venv/bin/python`).
- Environment vars to set per run: `CORRIDORKEY_ROOT=/workspace/CorridorKey`, `OPENCV_IO_ENABLE_OPENEXR=1`, `HF_HUB_ENABLE_HF_TRANSFER=1`, and ideally `HF_TOKEN` for the remaining model pulls.
- Full CorridorKey checkpoint (`CorridorKeyModule/checkpoints`) still needs to be downloaded by M3 (`download_models.py` without `--skip-corridorkey`), as it is the large one.

M2_RESULT_LINE_INLINE: PASS
