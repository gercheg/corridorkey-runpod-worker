# Docker Packaging Rules for RunPod Serverless

## Recommended Dockerfile shape

Use multi-stage builds:

1. `base`
   - CUDA runtime/devel image
   - system dependencies
   - `uv` or pinned package manager
   - Python version

2. `deps`
   - clone or copy upstream repo
   - apply compatibility patches
   - install locked dependencies

3. `models`
   - optional model prefetch
   - controlled by `SKIP_MODEL_PREFETCH`

4. `runtime`
   - copy worker code
   - set entrypoint
   - ensure shell scripts are executable and LF-normalized

## Windows checkout guard

Always defend against CRLF shell scripts:

```dockerfile
RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh
```

Add repo-level `.gitattributes`:

```text
*.sh text eol=lf
*.bash text eol=lf
Dockerfile text eol=lf
*.dockerfile text eol=lf
```

## Runtime entrypoint

The container should start exactly one RunPod serverless handler:

```bash
exec /path/to/.venv/bin/python -u /app/rp_handler.py
```

Provide a local API mode if useful:

```bash
SERVE_API_LOCALLY=true
```

## Model strategy

Prefer these defaults:

- development / first validation: `SKIP_MODEL_PREFETCH=1`
- production with stable model set: bake critical weights
- very large/changing models: use network volume or runtime download cache

When using Hugging Face:

```text
HF_HUB_DISABLE_TELEMETRY=1
HF_HUB_ENABLE_HF_TRANSFER=1
```

## Registry strategy

Production images must live in a persistent registry:

- DockerHub
- GHCR
- ECR/GAR

Temporary validation can use:

```text
ttl.sh/<unique-name>:24h
```

Never leave a production endpoint on `ttl.sh`.

## Local validation checklist

After build:

```powershell
docker run --rm --entrypoint <python> <image> -c "import rp_handler; print('ok')"
```

If local Docker has no GPU, only test imports/startup locally, then perform inference on RunPod.
