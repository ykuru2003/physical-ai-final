"""CLI entry point: load training settings, then run the reusable training workflow."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a small official LeRobot ACT for CI.")
    parser.add_argument("--config", type=Path, default=Path("configs/train_ci.yaml"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from roboops.config import load_yaml
    from roboops.training import run_training

    run_training(load_yaml(args.config))


if __name__ == "__main__":
    main()
