# syntax=docker/dockerfile:1.7
#
# CorridorKey — RunPod Serverless worker
# =====================================
#
# Build stages:
#   base        : CUDA 12.8 + cuDNN + system deps + uv + Python 3.11
#   deps        : uv-sync of CorridorKey Python deps (CUDA extra) + runpod SDK
#   models      : pre-download the CorridorKey + BiRefNet weights (baked in)
#   runtime     : thin final layer with just the handler and start script
#
# Tunables:
#   CORRIDORKEY_REF        git ref/branch/tag/commit to check out (default: main)
#   BIREFNET_USAGES        space-separated list of BiRefNet usages to prefetch
#                           (default: "General")
#   SKIP_MODEL_PREFETCH    if "1", skip weight downloads (thinner image,
#                           relies on network-volume / runtime download)
#

ARG CUDA_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04
ARG PYTHON_VERSION=3.11

# ---------------------------------------------------------------------------
# Stage 1: base — CUDA runtime + system deps + uv + Python
# ---------------------------------------------------------------------------
FROM ${CUDA_IMAGE} AS base

ARG PYTHON_VERSION
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    PATH="/root/.local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl wget ca-certificates \
      ffmpeg \
      libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
      libgoogle-perftools4 \
    && rm -rf /var/lib/apt/lists/*

# uv gives us deterministic deps + auto-managed Python 3.11.
# Pin to a concrete patch so a moving :0.7 tag can't surprise us.
COPY --from=ghcr.io/astral-sh/uv:0.7.22 /uv /usr/local/bin/uv
RUN uv --version && uv python install ${PYTHON_VERSION}

# ---------------------------------------------------------------------------
# Stage 2: deps — clone CorridorKey and install its Python dependencies
# ---------------------------------------------------------------------------
FROM base AS deps

ARG CORRIDORKEY_REF=main
ARG PYTHON_VERSION
ENV CORRIDORKEY_ROOT=/app/CorridorKey

WORKDIR /app
# Retry git clone to survive transient github.com 429/TLS hiccups.
RUN for i in 1 2 3; do \
      git clone https://github.com/nikopueringer/CorridorKey.git ${CORRIDORKEY_ROOT} && break || sleep 5; \
    done \
    && cd ${CORRIDORKEY_ROOT} && git checkout ${CORRIDORKEY_REF} && git rev-parse HEAD > /app/CORRIDORKEY_COMMIT

# Upstream BiRefNet wrapper hard-codes `trust_remote_code=False`, but
# ZhengPeng7/BiRefNet ships custom modelling code. Without this flip the
# alpha-hint generator aborts at "no AlphaHint was produced" (verified on M3).
RUN sed -i 's/trust_remote_code=False/trust_remote_code=True/g' \
        ${CORRIDORKEY_ROOT}/BiRefNetModule/wrapper.py \
    && grep -n 'trust_remote_code' ${CORRIDORKEY_ROOT}/BiRefNetModule/wrapper.py

WORKDIR ${CORRIDORKEY_ROOT}

# CorridorKey ships a pinned uv.lock — honour it. The cuda extra installs the
# GPU PyTorch wheels from the pytorch index declared in pyproject.toml.
# uv resolves its managed interpreter itself; just give it the major.minor.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra cuda --python ${PYTHON_VERSION:-3.11}

# Install RunPod SDK + hf_transfer (faster HF downloads) + boto3 into the same venv.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-cache "runpod>=1.7,<2" "hf_transfer>=0.1.6" boto3

# ---------------------------------------------------------------------------
# Stage 3: models — bake the weights into the image (optional)
# ---------------------------------------------------------------------------
FROM deps AS models

ARG BIREFNET_USAGES="General"
ARG SKIP_MODEL_PREFETCH=0
ENV HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HUB_ENABLE_HF_TRANSFER=1

COPY download_models.py /app/download_models.py

RUN --mount=type=cache,target=/root/.cache/huggingface \
    set -eux; \
    if [ "${SKIP_MODEL_PREFETCH}" = "1" ]; then \
        echo "Skipping model prefetch (SKIP_MODEL_PREFETCH=1)"; \
    else \
        cd ${CORRIDORKEY_ROOT} && \
        args=""; \
        for usage in ${BIREFNET_USAGES}; do args="${args} --birefnet ${usage}"; done; \
        uv run python /app/download_models.py ${args}; \
    fi

# ---------------------------------------------------------------------------
# Stage 4: runtime — final thin image
# ---------------------------------------------------------------------------
FROM models AS runtime

ENV OPENCV_IO_ENABLE_OPENEXR=1 \
    CORRIDORKEY_DEVICE=auto \
    CORRIDORKEY_JOB_ROOT=/tmp/corridorkey_jobs \
    LOG_LEVEL=INFO

COPY pipeline.py /app/pipeline.py
COPY rp_handler.py /app/rp_handler.py
COPY start.sh /app/start.sh
COPY test_input.json /app/test_input.json
RUN chmod +x /app/start.sh

WORKDIR ${CORRIDORKEY_ROOT}
CMD ["/app/start.sh"]
