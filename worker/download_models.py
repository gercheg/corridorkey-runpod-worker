"""Pre-download model weights at image build time.

Baking the weights into the image yields fast cold-starts on RunPod serverless
(no per-request HuggingFace download). Override ``CORRIDORKEY_SKIP_MODEL_PREFETCH=1``
to skip this step when building a thin "code-only" image meant to load weights
from a network volume at runtime.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("corridorkey.download_models")

CORRIDORKEY_ROOT = Path(os.environ.get("CORRIDORKEY_ROOT", "/app/CorridorKey"))
if str(CORRIDORKEY_ROOT) not in sys.path:
    sys.path.insert(0, str(CORRIDORKEY_ROOT))

# Move into the CorridorKey root so every module that relies on the relative
# ``CorridorKeyModule/checkpoints/`` path resolves to the correct directory.
os.chdir(CORRIDORKEY_ROOT)


def download_corridorkey() -> None:
    """Trigger the built-in HuggingFace auto-download for the CorridorKey engine."""
    from CorridorKeyModule.backend import _ensure_torch_checkpoint  # noqa: WPS437

    target = _ensure_torch_checkpoint()
    logger.info("CorridorKey checkpoint ready at %s", target)


def download_birefnet(usage: str = "General") -> None:
    """Cache the BiRefNet weights used by our default alpha hint generator."""
    from BiRefNetModule.wrapper import usage_to_weights_file
    from huggingface_hub import snapshot_download

    repo_name = usage_to_weights_file[usage]
    repo_id = f"ZhengPeng7/{repo_name}"
    model_local_dir = CORRIDORKEY_ROOT / "BiRefNetModule" / "checkpoints" / repo_name
    logger.info("Downloading BiRefNet %s -> %s", repo_id, model_local_dir)
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(model_local_dir),
        local_dir_use_symlinks=False,
    )
    logger.info("BiRefNet %s ready", usage)


def main() -> int:
    if os.environ.get("CORRIDORKEY_SKIP_MODEL_PREFETCH") == "1":
        logger.info("CORRIDORKEY_SKIP_MODEL_PREFETCH=1; skipping model prefetch")
        return 0

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--birefnet",
        action="append",
        default=None,
        help="BiRefNet usage key to cache. Can be passed multiple times. "
             "Defaults to just 'General'.",
    )
    parser.add_argument(
        "--skip-corridorkey",
        action="store_true",
        help="Skip CorridorKey weight download",
    )
    parser.add_argument(
        "--skip-birefnet",
        action="store_true",
        help="Skip BiRefNet weight download entirely",
    )
    args = parser.parse_args()

    if not args.skip_corridorkey:
        download_corridorkey()

    if not args.skip_birefnet:
        usages = args.birefnet or ["General"]
        for usage in usages:
            try:
                download_birefnet(usage)
            except Exception as exc:
                logger.error("Failed to download BiRefNet %s: %s", usage, exc)
                return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
