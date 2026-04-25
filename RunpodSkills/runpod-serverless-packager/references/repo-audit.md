# Repository / Model Audit

Use this checklist before writing Docker or creating RunPod infrastructure.

## Inputs to collect

- Source type:
  - GitHub repo
  - local repo
  - Hugging Face model/dataset/Space
  - mixed pipeline with external services
- License and redistribution constraints.
- Runtime entry point:
  - CLI command
  - Python function
  - web server
  - notebook/demo script
- Required GPU stack:
  - CUDA version
  - PyTorch/TensorFlow version
  - VRAM target
  - native libraries such as ffmpeg/OpenCV/system packages
- Model assets:
  - baked into image
  - downloaded on cold start
  - mounted from RunPod network volume
  - fetched from Hugging Face with token
- Test inputs:
  - small smoke input
  - realistic production input
  - edge-case input

## Output contract questions

- What is the user-facing artifact?
- Is a browser preview needed?
- Are raw assets needed for downstream composition?
- Should the worker return inline base64, URLs, or both?
- Is output expected to fit inside RunPod response limits?

## Risk checks

- Does upstream code require `trust_remote_code=True`?
- Does the repo assume interactive prompts or local paths?
- Does it write outputs relative to current working directory?
- Does it require LF shell scripts inside Linux containers?
- Are model downloads too large for cold starts?
- Does the output include large binary payloads that must be externalized?

## Minimum smoke test

Before endpoint deployment, verify:

```text
import path works
handler imports
model preload path works or degrades predictably
one tiny input completes
output files exist and can be decoded/probed
```

Record all substitutions if the original test data is unavailable.
