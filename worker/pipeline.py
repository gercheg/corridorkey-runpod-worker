"""CorridorKey pipeline wrapper for RunPod serverless.

Thin orchestration layer built on top of the vanilla CorridorKey modules.
We deliberately avoid re-using the interactive wizard from ``corridorkey_cli.py``
and drive the library functions (``clip_manager.run_inference``,
``clip_manager.run_birefnet``, ``clip_manager.generate_alphas``) directly.

The public entry point is ``process_job(job_dir, job_input) -> dict``.

Folder contract (prepared by rp_handler):
    <job_dir>/
        ClipsForInference/
            <clip_name>/
                Input.<ext>                        # original video or folder of frames
                AlphaHint/                         # optional pre-computed alpha
                    frame_0000.png
                    ...

Outputs land inside ``<clip_name>/Output`` (comp.mp4, FG/, Matte/, Comp/, Processed/).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger("corridorkey.pipeline")

# Path to the vendored / cloned CorridorKey source.
CORRIDORKEY_ROOT = Path(os.environ.get("CORRIDORKEY_ROOT", "/app/CorridorKey"))

if str(CORRIDORKEY_ROOT) not in sys.path:
    sys.path.insert(0, str(CORRIDORKEY_ROOT))

# ROCm env must be set before torch is imported; CorridorKey's CLI does the same.
from device_utils import setup_rocm_env  # noqa: E402

setup_rocm_env()

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

# The imports below rely on CORRIDORKEY_ROOT being on sys.path.
from clip_manager import (  # noqa: E402
    ClipEntry,
    InferenceSettings,
    generate_alphas,
    run_birefnet,
    run_inference,
)
from device_utils import resolve_device  # noqa: E402

BIREFNET_USAGE_DEFAULT = "General"
DEFAULT_IMAGE_SIZE = 2048
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".bmp")

SUPPORTED_ALPHA_SOURCES = {"birefnet", "gvm", "provided", "auto"}
SUPPORTED_OUTPUT_FORMATS = {"comp_mp4", "fg_zip", "matte_zip", "processed_zip", "comp_preview"}


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class JobError(Exception):
    """Raised when a job input cannot be processed."""


# ---------------------------------------------------------------------------
# Input resolution
# ---------------------------------------------------------------------------


def _download_to_file(url: str, dest: Path, timeout: int = 300) -> Path:
    """Stream a remote resource to disk."""
    logger.info("Downloading %s -> %s", url, dest)
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                if chunk:
                    fh.write(chunk)
    return dest


def _decode_base64_to_file(b64: str, dest: Path) -> Path:
    """Decode a base64 payload (optionally ``data:`` prefixed) to disk."""
    if b64.startswith("data:"):
        _, _, b64 = b64.partition(",")
    data = base64.b64decode(b64, validate=False)
    dest.write_bytes(data)
    return dest


def _resolve_input_blob(
    *,
    url: Optional[str],
    b64: Optional[str],
    local_path: Optional[str],
    dest: Path,
) -> Path:
    """Resolve any of url/base64/local into a file on disk at ``dest``."""
    if url:
        _download_to_file(url, dest)
        return dest
    if b64:
        _decode_base64_to_file(b64, dest)
        return dest
    if local_path:
        src = Path(local_path)
        if not src.exists():
            raise JobError(f"Local path does not exist inside the worker: {src}")
        if src.is_file():
            shutil.copy2(src, dest)
        else:
            # For directories we copy them wholesale next to ``dest`` (no rename).
            target = dest.parent / src.name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src, target)
            return target
        return dest
    raise JobError("No input blob provided (url/base64/local_path all empty)")


def _guess_video_ext(url: Optional[str], filename: Optional[str], default: str = ".mp4") -> str:
    for candidate in (filename, url):
        if not candidate:
            continue
        parsed = urlparse(candidate) if "://" in candidate else None
        name = parsed.path if parsed else candidate
        ext = os.path.splitext(name)[1].lower()
        if ext in VIDEO_EXTS:
            return ext
    return default


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------


def _build_inference_settings(payload: dict[str, Any]) -> InferenceSettings:
    """Translate user JSON settings into an InferenceSettings dataclass."""
    despill_raw = payload.get("despill_strength", 0.5)
    if isinstance(despill_raw, (int,)) and despill_raw > 1:
        despill_strength = max(0.0, min(10, float(despill_raw))) / 10.0
    else:
        despill_strength = max(0.0, min(1.0, float(despill_raw)))

    return InferenceSettings(
        input_is_linear=bool(payload.get("input_is_linear", False)),
        despill_strength=despill_strength,
        auto_despeckle=bool(payload.get("auto_despeckle", True)),
        despeckle_size=int(payload.get("despeckle_size", 400)),
        refiner_scale=float(payload.get("refiner_scale", 1.0)),
        generate_comp=bool(payload.get("generate_comp", True)),
        gpu_post_processing=bool(payload.get("gpu_post_processing", False)),
        image_size=int(payload.get("image_size", DEFAULT_IMAGE_SIZE)),
        tiled_inference=bool(payload.get("tiled_inference", False)),
    )


def _prepare_clip_folder(
    *,
    job_dir: Path,
    clip_name: str,
    video_input: Optional[dict[str, Any]],
    frames_input: Optional[dict[str, Any]],
    alpha_input: Optional[dict[str, Any]],
) -> Path:
    """Materialize the ``ClipsForInference/<clip_name>/`` layout expected by clip_manager.

    One of ``video_input`` or ``frames_input`` must be provided.
    ``alpha_input`` is optional (will be generated by BiRefNet/GVM if missing).
    """
    clips_root = job_dir / "ClipsForInference"
    clip_dir = clips_root / clip_name
    clip_dir.mkdir(parents=True, exist_ok=True)

    # 1. Input (video file or frame directory)
    if video_input:
        video_url = video_input.get("url")
        video_b64 = video_input.get("base64")
        video_local = video_input.get("path")
        ext = _guess_video_ext(video_url, video_input.get("filename"))
        target = clip_dir / f"Input{ext}"
        _resolve_input_blob(
            url=video_url, b64=video_b64, local_path=video_local, dest=target
        )
    elif frames_input:
        frames_url = frames_input.get("url")  # expects a zip
        frames_b64 = frames_input.get("base64")  # zip bytes
        frames_local = frames_input.get("path")
        input_dir = clip_dir / "Input"
        input_dir.mkdir(exist_ok=True)
        if frames_url or frames_b64:
            tmp_zip = clip_dir / "_frames.zip"
            _resolve_input_blob(url=frames_url, b64=frames_b64, local_path=None, dest=tmp_zip)
            with zipfile.ZipFile(tmp_zip) as zf:
                zf.extractall(input_dir)
            tmp_zip.unlink(missing_ok=True)
        elif frames_local:
            src = Path(frames_local)
            if src.is_dir():
                for f in src.iterdir():
                    if f.suffix.lower() in IMAGE_EXTS:
                        shutil.copy2(f, input_dir / f.name)
            else:
                raise JobError(f"frames.path must be a directory, got: {src}")
        else:
            raise JobError("frames input requires one of url/base64/path")
    else:
        raise JobError("Neither 'video' nor 'frames' input was provided")

    # 2. AlphaHint
    alpha_dir = clip_dir / "AlphaHint"
    alpha_dir.mkdir(exist_ok=True)
    if alpha_input:
        alpha_url = alpha_input.get("url")
        alpha_b64 = alpha_input.get("base64")
        alpha_local = alpha_input.get("path")
        alpha_kind = alpha_input.get("kind", "video")  # video or zip
        if alpha_kind == "zip":
            tmp_zip = clip_dir / "_alpha.zip"
            _resolve_input_blob(url=alpha_url, b64=alpha_b64, local_path=alpha_local, dest=tmp_zip)
            with zipfile.ZipFile(tmp_zip) as zf:
                zf.extractall(alpha_dir)
            tmp_zip.unlink(missing_ok=True)
        else:
            ext = _guess_video_ext(alpha_url, alpha_input.get("filename"))
            target = clip_dir / f"AlphaHint{ext}"
            _resolve_input_blob(
                url=alpha_url, b64=alpha_b64, local_path=alpha_local, dest=target
            )
            # Remove the empty AlphaHint/ folder so clip_manager picks up the video file
            try:
                alpha_dir.rmdir()
            except OSError:
                pass

    # Create hints directory required by clip_manager (even if unused)
    (clip_dir / "VideoMamaMaskHint").mkdir(exist_ok=True)

    return clip_dir


def _scan_single_clip(clip_dir: Path) -> ClipEntry:
    """Scan a single clip directory without invoking the global auto-organizer.

    clip_manager's ``scan_clips`` mutates ``CLIPS_DIR`` via module-level globals
    and hardcodes ``ClipsForInference``. Since each RunPod job gets its own
    workspace we want to bypass that and point straight at our prepared layout.
    """
    entry = ClipEntry(clip_dir.name, str(clip_dir))
    entry.find_assets()
    entry.validate_pair()
    return entry


def _ensure_alpha(
    clip: ClipEntry,
    *,
    alpha_source: str,
    birefnet_usage: str,
    birefnet_dilate: int,
    device: str,
) -> None:
    """Generate AlphaHint if missing."""
    if clip.alpha_asset is not None:
        logger.info("AlphaHint already present for %s", clip.name)
        return

    if alpha_source in ("auto", "birefnet"):
        logger.info("Generating AlphaHint via BiRefNet (%s)", birefnet_usage)
        run_birefnet(
            [clip],
            device=device,
            usage=birefnet_usage,
            dilate_radius=birefnet_dilate,
        )
    elif alpha_source == "gvm":
        logger.info("Generating AlphaHint via GVM")
        generate_alphas([clip], device=device)
    else:
        raise JobError(
            f"alpha_source='{alpha_source}' requires an explicit alpha input"
        )

    # Re-scan
    clip.alpha_asset = None
    clip.find_assets()
    if clip.alpha_asset is None:
        raise JobError("Alpha generation finished but no AlphaHint was produced")


def _zip_directory(src_dir: Path, dest_zip: Path) -> None:
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(src_dir):
            for name in files:
                full = Path(root) / name
                zf.write(full, arcname=full.relative_to(src_dir))


def _file_to_base64(path: Path) -> str:
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def _stitch_comp_video(comp_dir: Path, fps: float, out_path: Path) -> Optional[Path]:
    """Stitch Output/Comp PNG sequence into an MP4 via ffmpeg if available."""
    if not shutil.which("ffmpeg"):
        logger.warning("ffmpeg binary not found on PATH; skipping comp video")
        return None

    frames = sorted(p for p in comp_dir.iterdir() if p.suffix.lower() == ".png")
    if not frames:
        logger.warning("No comp frames in %s", comp_dir)
        return None

    stem = frames[0].stem
    if stem.isdigit():
        pattern = f"%0{len(stem)}d.png"
    else:
        pattern = "frame_%06d.png"
        # Normalize names so ffmpeg's sequencer can pick them up
        for i, f in enumerate(frames):
            target = comp_dir / (pattern % i)
            if f != target:
                f.rename(target)

    cmd = [
        "ffmpeg", "-y", "-framerate", f"{fps:g}",
        "-i", str(comp_dir / pattern),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        str(out_path),
    ]
    logger.info("Running ffmpeg: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg failed: %s", result.stderr[-2000:])
        return None
    return out_path


def _probe_fps(video_path: Path, default: float = 24.0) -> float:
    if not shutil.which("ffprobe"):
        return default
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "default=nokey=1:noprint_wrappers=1",
                str(video_path),
            ],
            text=True,
        ).strip()
        if "/" in out:
            num, den = out.split("/")
            den_f = float(den)
            return float(num) / den_f if den_f else default
        return float(out)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def process_job(job_dir: Path, job_input: dict[str, Any]) -> dict[str, Any]:
    """Run the full CorridorKey pipeline for a single job payload.

    Returns a dict containing output payloads (base64 / optional URLs) plus
    metadata. Raises JobError for recoverable input problems.
    """
    t_start = time.monotonic()
    job_dir.mkdir(parents=True, exist_ok=True)

    clip_name = (
        job_input.get("clip_name")
        or f"clip_{uuid.uuid4().hex[:8]}"
    ).strip() or f"clip_{uuid.uuid4().hex[:8]}"

    # Input resolution ------------------------------------------------------
    video_input = job_input.get("video")
    frames_input = job_input.get("frames")
    alpha_input = job_input.get("alpha_hint")

    # Back-compat: allow bare url / base64 at the top level
    if video_input is None and frames_input is None:
        if job_input.get("video_url") or job_input.get("video_base64") or job_input.get("video_path"):
            video_input = {
                "url": job_input.get("video_url"),
                "base64": job_input.get("video_base64"),
                "path": job_input.get("video_path"),
            }

    clip_dir = _prepare_clip_folder(
        job_dir=job_dir,
        clip_name=clip_name,
        video_input=video_input,
        frames_input=frames_input,
        alpha_input=alpha_input,
    )

    # Settings --------------------------------------------------------------
    settings_payload = job_input.get("settings") or {}
    settings = _build_inference_settings(settings_payload)

    alpha_source = settings_payload.get("alpha_source", "auto")
    if alpha_source not in SUPPORTED_ALPHA_SOURCES:
        raise JobError(
            f"Unknown alpha_source='{alpha_source}'. Expected one of: {sorted(SUPPORTED_ALPHA_SOURCES)}"
        )
    birefnet_usage = settings_payload.get("birefnet_usage", BIREFNET_USAGE_DEFAULT)
    birefnet_dilate = int(settings_payload.get("birefnet_dilate", 0))
    max_frames = settings_payload.get("max_frames")
    if max_frames is not None:
        max_frames = int(max_frames)

    output_formats = set(settings_payload.get("output_formats") or ["comp_mp4", "comp_preview"])
    unknown = output_formats - SUPPORTED_OUTPUT_FORMATS
    if unknown:
        raise JobError(f"Unknown output_formats: {sorted(unknown)}")

    device = resolve_device(settings_payload.get("device", "auto"))
    logger.info("Resolved device: %s | settings: %s | alpha_source=%s", device, settings, alpha_source)

    # Scan & ensure alpha ---------------------------------------------------
    clip = _scan_single_clip(clip_dir)
    _ensure_alpha(
        clip,
        alpha_source=alpha_source,
        birefnet_usage=birefnet_usage,
        birefnet_dilate=birefnet_dilate,
        device=device,
    )

    # Inference -------------------------------------------------------------
    t_infer = time.monotonic()
    run_inference(
        [clip],
        device=device,
        backend="torch",
        max_frames=max_frames,
        settings=settings,
    )
    infer_seconds = time.monotonic() - t_infer

    # Collect outputs -------------------------------------------------------
    out_dir = clip_dir / "Output"
    fg_dir = out_dir / "FG"
    matte_dir = out_dir / "Matte"
    comp_dir = out_dir / "Comp"
    proc_dir = out_dir / "Processed"

    frame_count = len(list(comp_dir.glob("*.png"))) if comp_dir.exists() else 0
    metadata = {
        "clip_name": clip.name,
        "frame_count": frame_count,
        "input_frames": clip.input_asset.frame_count if clip.input_asset else 0,
        "alpha_frames": clip.alpha_asset.frame_count if clip.alpha_asset else 0,
        "input_kind": clip.input_asset.type if clip.input_asset else None,
        "device": device,
        "settings": {
            "input_is_linear": settings.input_is_linear,
            "despill_strength": settings.despill_strength,
            "auto_despeckle": settings.auto_despeckle,
            "despeckle_size": settings.despeckle_size,
            "refiner_scale": settings.refiner_scale,
            "image_size": settings.image_size,
            "alpha_source": alpha_source,
        },
        "inference_seconds": round(infer_seconds, 3),
    }

    results: dict[str, Any] = {"status": "success", "metadata": metadata}

    # Comp preview (first PNG)
    if "comp_preview" in output_formats and comp_dir.exists():
        preview_candidates = sorted(comp_dir.glob("*.png"))
        if preview_candidates:
            results["comp_preview_png_base64"] = _file_to_base64(preview_candidates[0])

    # Comp MP4 (only meaningful when source was a video)
    if "comp_mp4" in output_formats and comp_dir.exists() and clip.input_asset and clip.input_asset.type == "video":
        fps = _probe_fps(Path(clip.input_asset.path))
        comp_mp4 = out_dir / f"{clip.name}_comp.mp4"
        if _stitch_comp_video(comp_dir, fps, comp_mp4):
            results["comp_mp4_base64"] = _file_to_base64(comp_mp4)
            results["comp_mp4_path"] = str(comp_mp4)
            metadata["fps"] = fps

    # Zipped sequences
    if "fg_zip" in output_formats and fg_dir.exists():
        zp = out_dir / "FG.zip"
        _zip_directory(fg_dir, zp)
        results["fg_zip_base64"] = _file_to_base64(zp)

    if "matte_zip" in output_formats and matte_dir.exists():
        zp = out_dir / "Matte.zip"
        _zip_directory(matte_dir, zp)
        results["matte_zip_base64"] = _file_to_base64(zp)

    if "processed_zip" in output_formats and proc_dir.exists():
        zp = out_dir / "Processed.zip"
        _zip_directory(proc_dir, zp)
        results["processed_zip_base64"] = _file_to_base64(zp)

    results["metadata"]["total_seconds"] = round(time.monotonic() - t_start, 3)
    results["output_dir"] = str(out_dir)

    return results


# ---------------------------------------------------------------------------
# CLI helper (runs the same pipeline against a local file — handy for smoke tests)
# ---------------------------------------------------------------------------


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="CorridorKey pipeline smoke test")
    parser.add_argument("--video", type=str, help="Path to an input video")
    parser.add_argument("--alpha", type=str, help="Optional path to AlphaHint video/zip")
    parser.add_argument("--job-dir", type=str, default="./_ck_job",
                        help="Scratch directory for the job")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--image-size", type=int, default=DEFAULT_IMAGE_SIZE)
    parser.add_argument("--alpha-source", choices=sorted(SUPPORTED_ALPHA_SOURCES), default="auto")
    parser.add_argument("--birefnet-usage", default=BIREFNET_USAGE_DEFAULT)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--output-json", default=None, help="Write result metadata to this JSON file")
    args = parser.parse_args()

    if not args.video:
        parser.error("--video is required")

    payload = {
        "clip_name": Path(args.video).stem,
        "video": {"path": args.video},
        "settings": {
            "alpha_source": args.alpha_source,
            "birefnet_usage": args.birefnet_usage,
            "device": args.device,
            "max_frames": args.max_frames,
            "image_size": args.image_size,
            "output_formats": ["comp_mp4", "comp_preview"],
        },
    }
    if args.alpha:
        payload["alpha_hint"] = {"path": args.alpha, "kind": "video"}

    job_dir = Path(args.job_dir)
    if job_dir.exists():
        shutil.rmtree(job_dir)
    result = process_job(job_dir, payload)

    # Don't dump base64 blobs to stdout
    slim = {
        k: v for k, v in result.items()
        if not (isinstance(v, str) and len(v) > 1_000_000)
    }
    slim["_omitted_large_keys"] = [k for k, v in result.items() if isinstance(v, str) and len(v) > 1_000_000]
    print(json.dumps(slim, indent=2))

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(slim, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    _cli()
