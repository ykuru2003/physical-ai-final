"""Single workshop command: python -m roboops download|validate|train|evaluate."""

from __future__ import annotations

import argparse
from pathlib import Path

from roboops.schema import DEFAULT_DATA, DEFAULT_RAW_ROOT


def _download(args: argparse.Namespace) -> None:
    if args.max_episodes < 1:
        raise SystemExit("--max-episodes must be at least 1")
    from roboops.download import download_dataset

    download_dataset(args.output, args.raw_root, args.max_episodes, force=args.force)


def _validate(args: argparse.Namespace) -> None:
    if not args.data.exists():
        raise SystemExit(f"Dataset not found: {args.data}\nRun: python -m roboops download")
    from roboops.data import load_validation_data
    from roboops.validation import validate

    checks = validate(load_validation_data(args.data))
    print("## Dataset Validation")
    print(f"Data: {args.data}\n")
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"{status}: {check.label} — {check.detail}")
    passed = all(check.passed for check in checks)
    print(f"\nRESULT: {'PASS' if passed else 'FAIL'}")
    if not passed:
        raise SystemExit(1)


def _train(args: argparse.Namespace) -> None:
    from roboops.config import load_yaml
    from roboops.training import run_training

    run_training(load_yaml(args.config))


def _evaluate(args: argparse.Namespace) -> None:
    from roboops.config import load_yaml
    from roboops.evaluation import run_evaluation

    metrics = run_evaluation(load_yaml(args.config), save_video=args.save_video)
    if metrics["result"] != "PASS":
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PushT workshop: download, validate, train and evaluate."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser("download", help="Download the pinned dataset and build an NPZ.")
    download.add_argument("--output", type=Path, default=DEFAULT_DATA)
    download.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    download.add_argument("--max-episodes", type=int, default=60)
    download.add_argument("--force", action="store_true")
    download.set_defaults(handler=_download)
    validate = commands.add_parser("validate", help="Check dataset fields, shapes and values.")
    validate.add_argument("--data", type=Path, default=DEFAULT_DATA)
    validate.set_defaults(handler=_validate)
    train = commands.add_parser("train", help="Train and save the configured ACT checkpoint.")
    train.add_argument("--config", type=Path, default=Path("configs/train_ci.yaml"))
    train.set_defaults(handler=_train)
    evaluate = commands.add_parser("evaluate", help="Evaluate a checkpoint with fixed PushT seeds.")
    evaluate.add_argument("--config", type=Path, default=Path("configs/eval_ci.yaml"))
    evaluate.add_argument("--save-video", action="store_true")
    evaluate.set_defaults(handler=_evaluate)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
