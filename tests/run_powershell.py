"""Run a PowerShell test inside an owned temporary directory, cleaning it on exit."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("--shell", required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    args = parser.parse_args()
    script = args.script.resolve()
    cache = args.cache_root.resolve()
    if not script.is_relative_to(ROOT) or not cache.is_relative_to(ROOT):
        raise ValueError("Test script and cache must stay inside this repository")
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="powershell-", dir=cache) as fixture:
        environment = dict(os.environ)
        environment["PHYSICAL_AI_TEST_SCRIPT"] = str(script)
        environment["PHYSICAL_AI_TEST_FIXTURE"] = fixture
        result = subprocess.run(
            [args.shell, "-NoProfile", "-File", str(script)],
            env=environment,
            check=False,
        )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
