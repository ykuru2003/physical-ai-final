"""CLI entry point: print named dataset quality checks and return a failing exit code."""

from __future__ import annotations

import argparse
from pathlib import Path

from roboops.schema import DEFAULT_DATA


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run beginner-friendly dataset quality checks.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    return parser.parse_args()


def validate(values):
    """Compatibility import for existing callers; the implementation lives in roboops.validation."""
    from roboops.validation import validate as validate_data

    return validate_data(values)


def main() -> None:
    args = parse_args()
    from roboops.data import load_validation_data

    if not args.data.exists():
        raise SystemExit(f"Dataset not found: {args.data}\nRun: python src/download_dataset.py")
    checks = validate(load_validation_data(args.data))
    print("## Dataset Validation")
    print(f"Data: {args.data}")
    print()
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"{status}: {check.label} — {check.detail}")
    passed = all(check.passed for check in checks)
    print()
    print(f"RESULT: {'PASS' if passed else 'FAIL'}")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
