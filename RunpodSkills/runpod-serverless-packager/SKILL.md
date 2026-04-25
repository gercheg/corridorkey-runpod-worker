---
name: runpod-serverless-packager
description: Packages repositories, Hugging Face models, or AI pipelines into production RunPod Serverless workers. Use when the user asks to dockerize a repo/model for RunPod, create a serverless endpoint, publish Docker images, test GPU inference, compare GPU prices, or build Dify/Loremax integrations around RunPod workers.
---

# RunPod Serverless Packager

## Use This Skill When

- A user gives a GitHub repo, local repo, or Hugging Face model and asks to run it on RunPod Serverless.
- A task mentions Docker, RunPod endpoint/template, GPU selection, serverless worker, `runpodctl`, GHCR/DockerHub, or Dify plugin integration.
- The desired output is a repeatable deployment pipeline, not just a one-off pod experiment.

## Operating Principles

1. **Preflight first, then action.**
   Check repo shape, model size, GPU/memory needs, registry auth, RunPod balance/endpoint state, and test data before creating infrastructure.

2. **Build a reusable worker contract.**
   The worker must have a documented input schema, output schema, local smoke path, serverless handler, Dockerfile, deploy scripts, and test payloads.

3. **Prefer URL artifacts over inline base64 for production.**
   Inline base64 is acceptable for tiny smoke tests. Production outputs should be uploaded to S3/R2 and returned as URLs.

4. **Never commit secrets or bulky generated media.**
   Put secrets in `config/` templates or external credential stores. Put generated media in CDN/S3 and commit manifests with URLs.

5. **Verify with real jobs.**
   A Docker build is not enough. Run at least one RunPod Serverless job with realistic input, record timings, output URLs, and health state.

## Default Workflow

1. **Repository/model audit**
   - Identify entry points, model weights, runtime dependencies, GPU requirements, and test inputs.
   - For details, see [repo-audit.md](references/repo-audit.md).

2. **Worker design**
   - Define RunPod payload, outputs, artifact strategy, timeout model, and Dify/Loremax contract.
   - For the output contract pattern, see [output-contracts.md](references/output-contracts.md).

3. **Docker packaging**
   - Create a CUDA-compatible Dockerfile, pin Python/dependency tooling, prefetch or mount models, and handle Windows LF/CRLF issues.
   - For packaging rules, see [docker-runpod.md](references/docker-runpod.md).

4. **Endpoint deployment**
   - Create/update RunPod template and serverless endpoint with `workersMin=0`, `workersMax=1` unless load testing.
   - Compare GPU price/performance before choosing the production endpoint.
   - For commands and price testing, see [runpod-deploy.md](references/runpod-deploy.md).

5. **Dify plugin handoff**
   - Document exact request payload, polling loop, output fields, retries, and final Dify node contract.
   - For a complete pattern, see [dify-plugin.md](references/dify-plugin.md).

6. **Evidence and handoff**
   - Commit code/docs/manifests.
   - Publish reports to CDN when useful.
   - Record Docker image tags, endpoint IDs, job IDs, timings, costs, and output URLs.

## Required Deliverables

For every packaged RunPod worker, produce:

- `worker/Dockerfile`
- `worker/rp_handler.py` or equivalent RunPod entrypoint
- `worker/README.md`
- `worker/test_input.json`
- deploy script or documented `runpodctl` commands
- smoke-test script or reusable client
- `deploy/endpoint.json` with endpoint/image/job records
- Dify payload examples when a Dify integration is requested
- `.gitignore` rules for generated media and job responses

## Registry Rules

- Use DockerHub/GHCR/ECR for production.
- `ttl.sh` is allowed only for short validation and must be documented as temporary.
- If DockerHub push fails with `insufficient_scope`, ask the user to run:

```powershell
docker login -u <dockerhub-user>
docker push <image>:<tag>
```

For PAT auth:

```powershell
$env:DOCKERHUB_PAT = "<token>"
$env:DOCKERHUB_PAT | docker login -u <dockerhub-user> --password-stdin
```

## Skill Anatomy Rules

Keep this `SKILL.md` concise. Put detailed scenarios in `references/`, utility code in `scripts/`, reusable templates in `assets/`, local auth templates in `config/`, and scratch state in `cache/`.

Use the scripts only as helpers; do not store secrets or generated binary outputs in this skill.
