from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from transparent_video import (
    AlphaSequenceError,
    build_transparent_mov_command,
    build_transparent_webm_command,
    find_frame_sequence,
)


class TransparentVideoCommandTests(unittest.TestCase):
    def test_finds_numeric_png_sequence_pattern(self) -> None:
        with TemporaryDirectory() as tmp:
            frame_dir = Path(tmp)
            (frame_dir / "00000.png").write_bytes(b"")
            (frame_dir / "00001.png").write_bytes(b"")

            sequence = find_frame_sequence(frame_dir)

            self.assertEqual(sequence.pattern, "%05d.png")
            self.assertEqual(sequence.frame_count, 2)

    def test_raises_when_sequence_is_empty(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(AlphaSequenceError):
                find_frame_sequence(Path(tmp))

    def test_builds_prores_4444_command_with_alpha_merge(self) -> None:
        fg = Path("/tmp/out/FG")
        matte = Path("/tmp/out/Matte")
        out = Path("/tmp/out/transparent.mov")

        command = build_transparent_mov_command(
            fg_pattern=fg / "%05d.png",
            matte_pattern=matte / "%05d.png",
            fps=24,
            out_path=out,
        )

        joined = " ".join(map(str, command))
        self.assertIn("alphamerge", joined)
        self.assertIn("prores_ks", command)
        self.assertIn("yuva444p10le", command)
        self.assertEqual(command[-1], str(out))

    def test_builds_webm_vp9_alpha_command(self) -> None:
        fg = Path("/tmp/out/FG")
        matte = Path("/tmp/out/Matte")
        out = Path("/tmp/out/transparent.webm")

        command = build_transparent_webm_command(
            fg_pattern=fg / "%05d.png",
            matte_pattern=matte / "%05d.png",
            fps=30,
            out_path=out,
        )

        joined = " ".join(map(str, command))
        self.assertIn("alphamerge", joined)
        self.assertIn("libvpx-vp9", command)
        self.assertIn("yuva420p", command)
        self.assertIn("-auto-alt-ref", command)
        self.assertEqual(command[-1], str(out))


if __name__ == "__main__":
    unittest.main()
