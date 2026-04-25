"""RunPod serverless handler for CorridorKey.

The handler accepts a video (via URL, base64, or local path), runs the
CorridorKey pipeline (optional BiRefNet/GVM alpha hint generation + inference)
and returns the composited output as base64 (default) or an S3/HTTP URL
when ``BUCKET_ENDPOINT_URL`` is configured.

Expected input schema::

    {
        "input": {
            "clip_name": "my_shot",                 // optional
            "video": {                              // one of: video|frames is required
                "url": "https://...",               // OR
                "base64": "<b64 string>",           // OR
                "path": "/runpod-volume/foo.mp4",
                "filename": "foo.mp4"               // optional (helps ext sniffing)
            },
            "frames": {                             // alternative to ``video``
                "url": "https://.../frames.zip",
                "base64": "...",
                "path": "/runpod-volume/frames/"
            },
            "alpha_hint": {                         // optional pre-computed alpha
                "kind": "video" | "zip",
                "url": "...", "base64": "...", "path": "..."
            },
            "settings": {
                "alpha_source": "auto" | "birefnet" | "gvm" | "provided",
                "birefnet_usage": "General",        // any value from BiRefNetModule.wrapper
                "birefnet_dilate": 0,
                "input_is_linear": false,
                "despill_strength": 0.5,            // 0..1 (or 0..10 int; it's auto-normalized)
                "auto_despeckle": true,
                "despeckle_size": 400,
                "refiner_scale": 1.0,
                "image_size": 2048,                 // 512 | 1024 | 2048
                "tiled_inference": false,
                "generate_comp": true,
                "max_frames": null,
                "device": "auto" | "cuda" | "cpu",
                "output_formats": ["comp_mp4", "comp_preview", "fg_zip", "matte_zip", "processed_zip"]
            }
        }
    }

Output schema::

    {
        "status": "success" | "error",
        "metadata": { ... },
        "comp_mp4_base64": "...",
        "comp_mp4_url": "https://...",              // when S3 upload is enabled
        "transparent_mov_base64": "...",            // ProRes 4444 alpha video
        "transparent_webm_base64": "...",           // VP9 alpha video
        "comp_preview_png_base64": "...",
        "fg_zip_base64": "...",                     // only if requested
        "matte_zip_base64": "...",
        "processed_zip_base64": "..."
    }
"""

from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any

import runpod
from runpod.serverless.utils import rp_upload  # type: ignore

# Ensure the worker code is importable when invoked by runpod runtime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline import JobError, process_job  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("corridorkey.handler")

REFRESH_WORKER = os.environ.get("REFRESH_WORKER", "false").lower() == "true"
BUCKET_ENDPOINT_URL = os.environ.get("BUCKET_ENDPOINT_URL")
MAX_INLINE_MP4_BYTES = int(os.environ.get("MAX_INLINE_MP4_BYTES", 80 * 1024 * 1024))  # 80 MB default

JOB_WORKSPACE_ROOT = Path(os.environ.get("CORRIDORKEY_JOB_ROOT", "/tmp/corridorkey_jobs"))
JOB_WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Output transformation
# ---------------------------------------------------------------------------


def _upload_if_configured(job_id: str, local_path: str, local_key: str) -> str | None:
    """Try to upload to the configured S3 bucket. Returns URL or None."""
    if not BUCKET_ENDPOINT_URL:
        return None
    bucket = os.environ.get("BUCKET_NAME", "corridorkey")
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if access_key and secret_key:
        try:
            import boto3
            from botocore.config import Config

            prefix = os.environ.get("S3_PREFIX", "corridorkey").strip("/")
            object_key = "/".join(part for part in (prefix, job_id, local_key) if part)
            client = boto3.client(
                "s3",
                endpoint_url=BUCKET_ENDPOINT_URL,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=os.environ.get("S3_REGION", "auto"),
                config=Config(retries={"max_attempts": 5, "mode": "standard"}),
            )
            content_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
            client.upload_file(
                local_path,
                bucket,
                object_key,
                ExtraArgs={"ContentType": content_type},
            )
            public_base = os.environ.get("S3_PUBLIC_BASE_URL")
            if public_base:
                return f"{public_base.rstrip('/')}/{object_key}"
            return f"{BUCKET_ENDPOINT_URL.rstrip('/')}/{bucket}/{object_key}"
        except Exception as exc:
            logger.warning("generic S3 upload failed for %s: %s", local_path, exc)

    try:
        url = rp_upload.upload_file_to_bucket(
            file_name=os.path.basename(local_path),
            file_location=local_path,
            bucket_name=bucket,
        )
        return url
    except AttributeError:
        # Older SDKs expose upload_image only
        try:
            return rp_upload.upload_image(job_id, local_path)
        except Exception as exc:
            logger.warning("rp_upload fallback failed for %s: %s", local_path, exc)
            return None
    except Exception as exc:
        logger.warning("rp_upload failed for %s: %s", local_path, exc)
        return None


def _maybe_externalize_outputs(job_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """When S3 is configured upload big artifacts; otherwise respect the inline cap."""
    if not BUCKET_ENDPOINT_URL:
        # Enforce the inline cap even without S3 — if file is too big we drop
        # the base64 and expose only the in-container path.
        mp4_b64 = result.get("comp_mp4_base64")
        mp4_path = result.get("comp_mp4_path")
        if mp4_b64 and mp4_path and os.path.exists(mp4_path):
            size = os.path.getsize(mp4_path)
            if size > MAX_INLINE_MP4_BYTES:
                logger.warning(
                    "comp_mp4 is %.1f MB; above MAX_INLINE_MP4_BYTES. Dropping base64 payload.",
                    size / (1024 * 1024),
                )
                result.pop("comp_mp4_base64", None)
                result.setdefault("warnings", []).append(
                    f"comp_mp4 ({size} bytes) exceeds MAX_INLINE_MP4_BYTES ({MAX_INLINE_MP4_BYTES})"
                )
        return result

    # S3 path for video payloads.
    for base_key, path_key, filename in (
        ("comp_mp4", "comp_mp4_path", "comp.mp4"),
        ("transparent_mov", "transparent_mov_path", "transparent.mov"),
        ("transparent_webm", "transparent_webm_path", "transparent.webm"),
    ):
        local_path = result.get(path_key)
        if local_path and os.path.exists(local_path):
            url = _upload_if_configured(job_id, local_path, filename)
            if url:
                result[f"{base_key}_url"] = url
                result.pop(f"{base_key}_base64", None)

    # Image preview and zip payloads — upload each and replace inline base64.
    preview_path = result.get("comp_preview_png_path")
    if preview_path and os.path.exists(preview_path):
        url = _upload_if_configured(job_id, preview_path, "comp_preview.png")
        if url:
            result["comp_preview_png_url"] = url
            result.pop("comp_preview_png_base64", None)

    for key, filename in (
        ("fg_zip_base64", "FG.zip"),
        ("matte_zip_base64", "Matte.zip"),
        ("processed_zip_base64", "Processed.zip"),
    ):
        path_key = key.replace("_base64", "_path")
        local = result.get(path_key)
        if local and os.path.exists(local):
            url = _upload_if_configured(job_id, local, filename)
            if url:
                result[key.replace("_base64", "_url")] = url
                result.pop(key, None)

    return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_job(job_input: Any) -> tuple[dict[str, Any] | None, str | None]:
    if job_input is None:
        return None, "Missing 'input' in job payload"
    if isinstance(job_input, str):
        import json
        try:
            job_input = json.loads(job_input)
        except json.JSONDecodeError as exc:
            return None, f"Invalid JSON string in 'input': {exc}"
    if not isinstance(job_input, dict):
        return None, f"'input' must be a dict, got {type(job_input).__name__}"

    if not any(
        job_input.get(k) for k in ("video", "frames", "video_url", "video_base64", "video_path")
    ):
        return None, "No video/frames payload provided"

    return job_input, None


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


def handler(job: dict[str, Any]) -> dict[str, Any]:
    job_id = job.get("id") or "local"
    raw_input = job.get("input")

    validated, err = _validate_job(raw_input)
    if err:
        logger.error("Validation failed: %s", err)
        return {"status": "error", "error": err, "refresh_worker": REFRESH_WORKER}

    job_dir = JOB_WORKSPACE_ROOT / f"job_{job_id}"
    if job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Starting job %s in %s", job_id, job_dir)
        result = process_job(job_dir, validated)
        result = _maybe_externalize_outputs(job_id, result)
        result["refresh_worker"] = REFRESH_WORKER
        return result
    except JobError as exc:
        logger.error("Job input error: %s", exc)
        return {
            "status": "error",
            "error": str(exc),
            "error_kind": "input",
            "refresh_worker": REFRESH_WORKER,
        }
    except Exception as exc:  # pragma: no cover - defensive guard
        tb = traceback.format_exc()
        logger.exception("Job %s failed", job_id)
        return {
            "status": "error",
            "error": str(exc),
            "error_kind": "runtime",
            "traceback": tb,
            "refresh_worker": REFRESH_WORKER,
        }
    finally:
        # Clean up scratch space unless the user explicitly asked us to keep it
        if os.environ.get("CORRIDORKEY_KEEP_JOB_DIR", "0") != "1":
            try:
                shutil.rmtree(job_dir, ignore_errors=True)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    logger.info(
        "Starting CorridorKey RunPod handler | REFRESH_WORKER=%s BUCKET=%s",
        REFRESH_WORKER,
        bool(BUCKET_ENDPOINT_URL),
    )
    runpod.serverless.start({"handler": handler})
