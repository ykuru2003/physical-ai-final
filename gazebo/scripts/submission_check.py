"""Qualify the east goal, validate the real local model, then run three trials."""

import argparse
import json
import subprocess
import sys

import destination_control as dc
from task_results import navigation_succeeded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=dc.default_model())
    parser.add_argument("--port", type=int, default=dc.default_port())
    args = parser.parse_args()
    folder = dc.ROOT / "outputs/submission-check" / dc.run_id()
    folder.mkdir(parents=True)
    summary = {"status": "INCOMPLETE", "model": args.model, "trials": []}
    try:
        # Reuse current physical evidence only when all hashes/reports match.
        registry = dc.load_registry()
        east = next(d for d in registry["destinations"] if d["id"] == "east_station")
        if not dc.qualified(east):
            subprocess.run(
                [
                    sys.executable,
                    str(dc.ROOT / "scripts/qualify_destinations.py"),
                    "--ids",
                    "east_station",
                    "--repeats",
                    "3",
                ],
                cwd=dc.ROOT,
                check=True,
            )
        subprocess.run(
            [
                sys.executable,
                str(dc.ROOT / "scripts/validate_local_ai.py"),
                "--model",
                args.model,
                "--port",
                str(args.port),
            ],
            cwd=dc.ROOT,
            check=True,
        )
        east = next(
            d for d in dc.load_registry()["destinations"] if d["id"] == "east_station"
        )
        summary["goal"] = east["goal"]
        for trial in range(1, 4):
            output = folder / f"trial-{trial}"
            with dc.navigation_lock():
                audit = dc.run_instruction(
                    "東側の資材受け渡し場所へ行って",
                    dc.load_registry(),
                    output,
                    execute=True,
                    model=args.model,
                    port=args.port,
                )
            passed = navigation_succeeded(
                audit, destination="east_station", goal=east["goal"]
            )
            summary["trials"].append(
                {
                    "trial": trial,
                    "passed": passed,
                    "path": (output / "selection.json").relative_to(dc.ROOT).as_posix(),
                    "error_m": audit.get("world_evaluation", {}).get(
                        "world_goal_error_m"
                    ),
                }
            )
            if not passed:
                raise RuntimeError(f"Trial {trial} failed; inspect {output}")
        summary["status"] = "PASS"
    except (Exception, KeyboardInterrupt) as error:
        summary["reason"] = str(error) or "Interrupted"
    finally:
        (folder / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"Results: {folder}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
