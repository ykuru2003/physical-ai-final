"""Run dependency-free offline checks locally or in GitHub Actions.

These checks never start ROS, Docker or Ollama and do not validate physical
arrival or real model inference. Those remain separate runtime checks.
"""
from pathlib import Path
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CHECKS = (
    'tests.test_archive_outputs',
    'tests.test_reference_runtime',
    'tests.test_world_evaluation',
    'tests.test_destination_control',
    'tests.offline_navigation',
)


def main():
    print('OFFLINE CHECKS: Python only; no Gazebo or real AI inference.', flush=True)
    for source in sorted([*(ROOT / 'scripts').rglob('*.py'), *(ROOT / 'tests').rglob('*.py')]):
        compile(source.read_text(encoding='utf-8-sig'), str(source), 'exec')
    ET.parse(ROOT / 'simulation/worlds/practice.sdf')
    print('Python syntax and world XML: PASS', flush=True)
    for index, name in enumerate(CHECKS, 1):
        print(f'[{index}/{len(CHECKS)}] {name}', flush=True)
        subprocess.run([sys.executable, '-u', '-m', name],
                       cwd=ROOT, env={**os.environ, 'PYTHONPATH': str(ROOT / 'scripts')},
                       check=True, timeout=120)
    print('OFFLINE CHECKS: PASS', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, SyntaxError, ImportError, ET.ParseError,
            subprocess.SubprocessError) as error:
        print(f'OFFLINE CHECKS: FAIL: {error}', file=sys.stderr)
        raise SystemExit(1)
