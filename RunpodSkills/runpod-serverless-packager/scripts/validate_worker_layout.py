#!/usr/bin/env python3
"""Validate that a RunPod worker folder has the expected handoff files."""

from __future__ import annotations

import argparse
from pathlib import Path


REQUIRED = [
    "Dockerfile",
    "rp_handler.py",
    "README.md",
    "test_input.json",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("worker_dir", type=Path)
    args = parser.parse_args()

    missing = [name for name in REQUIRED if not (args.worker_dir / name).exists()]
    if missing:
        print("MISSING:")
        for item in missing:
            print(f"- {item}")
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
