#!/usr/bin/env bash
# Container entrypoint for the CorridorKey RunPod serverless worker.
set -euo pipefail

# tcmalloc gives us better allocator behaviour in long-running inference loops.
TCMALLOC="$(ldconfig -p 2>/dev/null | grep -Po 'libtcmalloc\.so\.\d' | head -n 1 || true)"
if [[ -n "${TCMALLOC}" ]]; then
    export LD_PRELOAD="${TCMALLOC}"
fi

# CorridorKey needs EXR I/O in OpenCV at runtime.
export OPENCV_IO_ENABLE_OPENEXR="${OPENCV_IO_ENABLE_OPENEXR:-1}"
export PYTHONUNBUFFERED=1

# Point at the vendored CorridorKey source tree (see Dockerfile).
export CORRIDORKEY_ROOT="${CORRIDORKEY_ROOT:-/app/CorridorKey}"

# Always run the handler from the CorridorKey working directory — some
# clip_manager internals resolve paths relative to the cwd.
cd "${CORRIDORKEY_ROOT}"

if [[ "${SERVE_API_LOCALLY:-false}" == "true" || "${SERVER_INPOD:-false}" == "true" ]]; then
    echo "[corridorkey-worker] Starting handler in local API mode"
    exec "${CORRIDORKEY_ROOT}/.venv/bin/python" -u /app/rp_handler.py --rp_serve_api --rp_api_host=0.0.0.0
fi

echo "[corridorkey-worker] Starting RunPod serverless handler"
exec "${CORRIDORKEY_ROOT}/.venv/bin/python" -u /app/rp_handler.py
