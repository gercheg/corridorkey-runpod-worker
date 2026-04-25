"""Small client used by a Dify plugin/tool to call CorridorKey on RunPod.

The code intentionally has no project-local imports, so it can be copied into a
Dify plugin action, a Dify Workflow Code node, or a standalone smoke-test script.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_ENDPOINT_ID = "68ik5lhd4hz97d"  # RTX 6000 Ada 48GB endpoint.


class RunPodError(RuntimeError):
    pass


def submit_job(endpoint_id: str, api_key: str, payload: dict[str, Any]) -> str:
    url = f"https://api.runpod.ai/v2/{endpoint_id}/run"
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    job_id = data.get("id")
    if not job_id:
        raise RunPodError(f"RunPod /run response has no id: {data}")
    return job_id


def get_status(endpoint_id: str, api_key: str, job_id: str) -> dict[str, Any]:
    url = f"https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}"
    response = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=60)
    response.raise_for_status()
    return response.json()


def wait_for_completion(
    endpoint_id: str,
    api_key: str,
    job_id: str,
    *,
    interval_s: int = 20,
    timeout_s: int = 3600,
) -> dict[str, Any]:
    started = time.monotonic()
    while True:
        status = get_status(endpoint_id, api_key, job_id)
        state = status.get("status")
        if state in {"COMPLETED", "FAILED", "CANCELLED"}:
            return status
        if time.monotonic() - started > timeout_s:
            raise TimeoutError(f"RunPod job {job_id} did not finish within {timeout_s}s")
        time.sleep(interval_s)


def decode_outputs(result: dict[str, Any], output_dir: Path) -> dict[str, str]:
    """Decode inline base64 fields into files and return local paths.

    Dify production deployments should prefer URL outputs via worker-side S3
    offload. Inline base64 is convenient for smoke tests and short clips.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output = result.get("output") or result
    saved: dict[str, str] = {}

    mapping = {
        "comp_mp4_base64": "comp.mp4",
        "comp_preview_png_base64": "comp_preview.png",
        "fg_zip_base64": "FG.zip",
        "matte_zip_base64": "Matte.zip",
        "processed_zip_base64": "Processed.zip",
    }
    for key, filename in mapping.items():
        value = output.get(key)
        if not value:
            continue
        path = output_dir / filename
        path.write_bytes(base64.b64decode(value))
        saved[key] = str(path)
    return saved


def build_payload(
    video_url: str,
    *,
    clip_name: str = "dify_corridorkey_job",
    filename: str = "input.mp4",
    output_formats: list[str] | None = None,
    image_size: int = 1024,
    alpha_source: str = "birefnet",
    despill_strength: float = 0.5,
    despeckle_size: int = 400,
    max_frames: int | None = None,
) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "alpha_source": alpha_source,
        "birefnet_usage": "General",
        "birefnet_dilate": 0,
        "input_is_linear": False,
        "despill_strength": despill_strength,
        "auto_despeckle": True,
        "despeckle_size": despeckle_size,
        "refiner_scale": 1.0,
        "image_size": image_size,
        "generate_comp": True,
        "device": "auto",
        "output_formats": output_formats or ["comp_mp4", "comp_preview"],
    }
    if max_frames is not None:
        settings["max_frames"] = max_frames

    return {
        "input": {
            "clip_name": clip_name,
            "video": {"url": video_url, "filename": filename},
            "settings": settings,
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit a CorridorKey job to RunPod")
    parser.add_argument("--endpoint-id", default=os.environ.get("RUNPOD_ENDPOINT_ID", DEFAULT_ENDPOINT_ID))
    parser.add_argument("--api-key", default=os.environ.get("RUNPOD_API_KEY"))
    parser.add_argument("--video-url", help="Input video URL")
    parser.add_argument("--payload", type=Path, help="Existing JSON payload file")
    parser.add_argument("--output-dir", type=Path, default=Path("corridorkey_out"))
    parser.add_argument("--alpha-assets", action="store_true", help="Request FG/Matte/Processed zip outputs")
    parser.add_argument("--max-frames", type=int)
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("RUNPOD_API_KEY is required")

    if args.payload:
        payload = json.loads(args.payload.read_text(encoding="utf-8"))
    elif args.video_url:
        formats = ["comp_mp4", "comp_preview"]
        if args.alpha_assets:
            formats += ["fg_zip", "matte_zip", "processed_zip"]
        payload = build_payload(args.video_url, output_formats=formats, max_frames=args.max_frames)
    else:
        raise SystemExit("Provide either --payload or --video-url")

    job_id = submit_job(args.endpoint_id, args.api_key, payload)
    print(f"submitted job_id={job_id}")
    result = wait_for_completion(args.endpoint_id, args.api_key, job_id)
    print(json.dumps({k: result.get(k) for k in ("id", "status", "delayTime", "executionTime")}, indent=2))

    if result.get("status") != "COMPLETED":
        print(json.dumps(result, indent=2)[:4000])
        return 1

    saved = decode_outputs(result, args.output_dir)
    if saved:
        print("decoded outputs:")
        for key, path in saved.items():
            print(f"  {key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
