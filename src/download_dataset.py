"""CLI entry point: materialize a pinned subset of the PushT demonstration dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

from roboops.schema import DEFAULT_DATA, DEFAULT_RAW_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a small state-only LeRobot PushT dataset."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument(
        "--max-episodes",
        type=int,
        default=60,
        help="Number of episodes to materialize (default: 60 of 206).",
    )
    parser.add_argument(
        "--force", action="store_true", help="Replace the processed NPZ if it exists."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_episodes < 1:
        raise SystemExit("--max-episodes must be at least 1")
    from roboops.download import download_dataset

    download_dataset(args.output, args.raw_root, args.max_episodes, force=args.force)


if __name__ == "__main__":
    main()
