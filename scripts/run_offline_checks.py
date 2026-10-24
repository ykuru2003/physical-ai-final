"""Run dependency-free offline checks locally or in GitHub Actions.

These checks never start ROS, Docker or Ollama and do not validate physical
arrival or real model inference. Those remain separate runtime checks.
"""
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CHECKS = (
    'test_step2_evaluation.py',
    'test_destination_control.py',
    'test_step2_offline.py',
    'test_step2_v4_offline.py',
)


def main():
    print('OFFLINE CHECKS: Python only; no Gazebo or real AI inference.', flush=True)
    for source in sorted((ROOT / 'scripts').rglob('*.py')):
        compile(source.read_text(encoding='utf-8-sig'), str(source), 'exec')
    ET.parse(ROOT / 'simulation/worlds/practice.sdf')
    print('Python syntax and world XML: PASS', flush=True)
    (ROOT / 'outputs').mkdir(exist_ok=True)
    for index, name in enumerate(CHECKS, 1):
        print(f'[{index}/{len(CHECKS)}] {name}', flush=True)
        subprocess.run([sys.executable, '-u', str(ROOT / 'scripts' / name)],
                       cwd=ROOT, check=True, timeout=120)
    print('OFFLINE CHECKS: PASS', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, SyntaxError, ImportError, ET.ParseError,
            subprocess.SubprocessError) as error:
        print(f'OFFLINE CHECKS: FAIL: {error}', file=sys.stderr)
        raise SystemExit(1)
