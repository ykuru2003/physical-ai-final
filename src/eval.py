"""CLI entry point: evaluate a saved checkpoint with the configured PushT seeds."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the official LeRobot ACT in PushT.")
    parser.add_argument("--config", type=Path, default=Path("configs/eval_ci.yaml"))
    parser.add_argument("--save-video", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from roboops.config import load_yaml
    from roboops.evaluation import run_evaluation

    metrics = run_evaluation(load_yaml(args.config), save_video=args.save_video)
    if metrics["result"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
