"""Consume a local request, wait for ROS, and run one logged STEP 2 test."""
import json
import subprocess
import sys
import time
from pathlib import Path


def main():
    output = Path('/workspace/outputs')
    request = output/'step2-autotest.request'
    if not request.exists():
        return 0
    request.rename(output/'step2-autotest.running')
    report = {'result': 'RUNNING', 'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    status = output/'step2-autotest-status.json'
    status.write_text(json.dumps(report, indent=2)+'\n')
    try:
        with (output/'step2-topic-readiness.log').open('w') as log:
            ready = subprocess.run([sys.executable, '-u', '/workspace/scripts/wait_step2_ready.py'], stdout=log, stderr=subprocess.STDOUT, timeout=135)
        if ready.returncode:
            report.update(result='FAIL', phase='readiness', exit_code=ready.returncode)
            return 1
        with (output/'step2-run.log').open('w') as log:
            run = subprocess.run([sys.executable, '-u', '/workspace/scripts/drive_to_goal_v3.py'], stdout=log, stderr=subprocess.STDOUT, timeout=260)
        report.update(result='PASS' if run.returncode == 0 else 'FAIL', phase='drive', exit_code=run.returncode)
        return run.returncode
    except Exception as error:
        report.update(result='FAIL', error=str(error))
        return 1
    finally:
        report['finished_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        status.write_text(json.dumps(report, indent=2)+'\n')
        (output/'step2-autotest.running').rename(output/'step2-autotest.completed')


if __name__ == '__main__':
    raise SystemExit(main())
