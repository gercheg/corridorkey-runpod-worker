"""Transparent-video helpers for CorridorKey outputs.

CorridorKey writes foreground frames and matte frames as image sequences. This
module turns those sequences into delivery-friendly alpha video formats:

- ProRes 4444 MOV (`transparent_mov`) for editorial / production pipelines.
- VP9 WebM with alpha (`transparent_webm`) for browser-oriented pipelines.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


FRAME_EXTS = (".png", ".exr", ".tif", ".tiff")


class AlphaSequenceError(RuntimeError):
    """Raised when an alpha-video sequence cannot be built."""


@dataclass(frozen=True)
class FrameSequence:
    directory: Path
    pattern: str
    frame_count: int
    extension: str

    @property
    def pattern_path(self) -> Path:
        return self.directory / self.pattern


def find_frame_sequence(directory: Path) -> FrameSequence:
    """Return an ffmpeg-compatible pattern for a numeric frame sequence."""
    frames = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in FRAME_EXTS
    )
    if not frames:
        raise AlphaSequenceError(f"No image frames found in {directory}")

    first = frames[0]
    stem = first.stem
    if not stem.isdigit():
        raise AlphaSequenceError(
            f"Expected numeric frame names in {directory}, got {first.name}"
        )

    width = len(stem)
    ext = first.suffix.lower()
    pattern = f"%0{width}d{ext}"
    return FrameSequence(
        directory=directory,
        pattern=pattern,
        frame_count=len(frames),
        extension=ext,
    )


def build_transparent_mov_command(
    *,
    fg_pattern: Path,
    matte_pattern: Path,
    fps: float,
    out_path: Path,
) -> list[str]:
    """Build a ProRes 4444 ffmpeg command from foreground + matte sequences."""
    return [
        "ffmpeg",
        "-y",
        "-framerate",
        f"{fps:g}",
        "-i",
        str(fg_pattern),
        "-framerate",
        f"{fps:g}",
        "-i",
        str(matte_pattern),
        "-filter_complex",
        "[1:v]format=gray[alpha];[0:v][alpha]alphamerge,format=yuva444p10le[out]",
        "-map",
        "[out]",
        "-c:v",
        "prores_ks",
        "-profile:v",
        "4",
        "-pix_fmt",
        "yuva444p10le",
        "-vendor",
        "apl0",
        str(out_path),
    ]


def build_transparent_webm_command(
    *,
    fg_pattern: Path,
    matte_pattern: Path,
    fps: float,
    out_path: Path,
) -> list[str]:
    """Build a VP9 WebM-alpha ffmpeg command from foreground + matte sequences."""
    return [
        "ffmpeg",
        "-y",
        "-framerate",
        f"{fps:g}",
        "-i",
        str(fg_pattern),
        "-framerate",
        f"{fps:g}",
        "-i",
        str(matte_pattern),
        "-filter_complex",
        "[1:v]format=gray[alpha];[0:v][alpha]alphamerge,format=yuva420p[out]",
        "-map",
        "[out]",
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuva420p",
        "-auto-alt-ref",
        "0",
        "-b:v",
        "0",
        "-crf",
        "30",
        str(out_path),
    ]


def encode_transparent_video(command: list[str]) -> bool:
    """Run ffmpeg and return whether encoding succeeded."""
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode == 0
