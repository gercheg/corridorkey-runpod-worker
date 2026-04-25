#!/usr/bin/env python3
"""Estimate RunPod job cost from execution seconds and GPU hourly price."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-seconds", type=float, required=True)
    parser.add_argument("--hourly-price", type=float, required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    cost = args.execution_seconds * args.hourly_price / 3600 * args.workers
    print(f"{cost:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
