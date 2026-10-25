"""Verify local-AI navigation and execute one-shot ROS launch requests."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import destination_control as dc


def run_requested_drive():
    output = Path('/workspace/outputs')
    request = output/'navigation-request.request'
    if not request.exists():
        return 0
    request.rename(output/'navigation-request.running')
    report = {'result': 'RUNNING', 'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    status = output/'navigation-request-status.json'
    status.write_text(json.dumps(report, indent=2)+'\n')
    try:
        with (output/'sensor-readiness.log').open('w') as log:
            ready = subprocess.run([sys.executable, '-u', '/workspace/scripts/wait_for_sensors.py'], stdout=log, stderr=subprocess.STDOUT, timeout=135)
        if ready.returncode:
            report.update(result='FAIL', phase='readiness', exit_code=ready.returncode)
            return 1
        with (output/'navigation-run.log').open('w') as log:
            run = subprocess.run([sys.executable, '-u', '/workspace/scripts/reference_navigation.py', '--profile', 'baseline'], stdout=log, stderr=subprocess.STDOUT, timeout=260)
        report.update(result='PASS' if run.returncode == 0 else 'FAIL', phase='drive', exit_code=run.returncode)
        return run.returncode
    except Exception as error:
        report.update(result='FAIL', error=str(error))
        return 1
    finally:
        report['finished_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        status.write_text(json.dumps(report, indent=2)+'\n')
        (output/'navigation-request.running').rename(output/'navigation-request.completed')



def command(script, *arguments):
    subprocess.run([sys.executable, str(dc.ROOT/'scripts'/script), *arguments], cwd=dc.ROOT, check=True)


def check_navigation(ident, text, registry, model='gpt-oss:20b'):
    output = dc.ROOT/'outputs/language-goals'/dc.run_id()
    with dc.navigation_lock():
        audit = dc.run_instruction(text, registry, output, execute=True, model=model)
    destination = next(d for d in registry['destinations'] if d['id'] == ident)
    if (audit['status'] != 'PASS' or audit.get('destination') != ident
            or audit.get('selection', {}).get('destination_id') != ident
            or audit.get('movement_started') is not True
            or not dc.report_passes(audit.get('world_evaluation', {}), destination['goal'])
            or audit.get('final_stop') != 'CONFIRMED_STATIONARY'):
        raise RuntimeError(f'Natural-language navigation check failed for {ident}; see {output}')


def check_unknown(registry, model='gpt-oss:20b'):
    output = dc.ROOT/'outputs/language-goals'/dc.run_id()
    with dc.navigation_lock():
        audit = dc.run_instruction('登録されていないコンビニに行って', registry, output, execute=True, model=model)
    if (audit['status'] != 'REJECTED' or audit.get('movement_started') is not False
            or audit.get('selection', {}).get('decision') not in ('unknown', 'clarify', 'stop')
            or audit.get('initial_stop') != 'CONFIRMED_STATIONARY'
            or audit.get('final_stop') != 'CONFIRMED_STATIONARY'):
        raise RuntimeError(f'Unknown-instruction real AI/stop check failed; see {output}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', choices=('verify', 'requested-drive'), default='verify')
    parser.add_argument('--model', default='qwen3:1.7b', help='Exact name of an already installed local model')
    parser.add_argument('--recheck-ai', action='store_true', help='Repeat even an already-passed real AI certificate')
    parser.add_argument('--recheck-navigation', action='store_true', help='Repeat even already-qualified physical runs')
    args = parser.parse_args()
    if args.action == 'requested-drive':
        return run_requested_drive()
    # Fail before simulator restart when either local service is unavailable.
    print('[1/6] Checking installed local AI and Docker...', flush=True)
    installed = dc.local_request(11434, '/api/tags', timeout=5)
    found = next((m for m in installed.get('models', []) if m.get('name') == args.model and not m.get('remote_host')), None)
    if found is None:
        raise RuntimeError(f'Installed local {args.model} unavailable; no download attempted')
    subprocess.run(['docker', 'compose', 'ps', '--status', 'running'], cwd=dc.ROOT, check=True)
    registry = dc.load_registry()
    east = next(d for d in registry['destinations'] if d['id'] == 'east_station')
    if not args.recheck_navigation and dc.qualified(east):
        print('[2/6] Reusing verified three-run east PASS evidence; no repeat drives.', flush=True)
    else:
        print('[2/6] Evaluating east destination three times...', flush=True)
        command('qualify_destinations.py', '--ids', 'east_station')
    registry = dc.load_registry()
    if not args.recheck_navigation and any(dc.qualified(d) for d in registry['destinations'] if d['id'] != 'east_station'):
        print('[3/6] Reusing verified three-run second-destination PASS evidence.', flush=True)
    else:
        print('[3/6] Searching and evaluating a second destination...', flush=True)
        command('qualify_destinations.py')
    if not args.recheck_ai and dc.language_validated(dc.load_registry(), {'model': args.model, 'model_digest': found.get('digest')}):
        print('[4/6] Reusing verified real-AI PASS evidence for the same model and code.', flush=True)
    else:
        print('[4/6] Testing real local-AI instructions and additional paraphrases...', flush=True)
        command('validate_local_ai.py', '--model', args.model)
    registry = dc.load_registry()
    second = next((d for d in registry['destinations'] if d['id'] != 'east_station' and dc.qualified(d)), None)
    if second is None:
        raise RuntimeError('No second qualified destination')
    instructions = {'east_station': '東側の資材受け渡し場所に行ってください',
                    'south_station': '南東の点検場所まで向かってください',
                    'south_near': '南側の手前の待機所へ移動してください',
                    'west_station': '西側の待機所へ移動してください'}
    print('[5/6] Evaluating language-to-navigation for both destinations...', flush=True)
    for ident in ('east_station', second['id']):
        check_navigation(ident, instructions[ident], dc.load_registry(), model=args.model)
    print('[6/6] Checking real unknown-instruction rejection and stationary stop...', flush=True)
    check_unknown(dc.load_registry(), model=args.model)
    print('NAVIGATION CHECKS: PASS; see outputs/ for individual evidence logs.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as error:
        print(f'NAVIGATION CHECKS: INCOMPLETE: {error}', file=sys.stderr)
        raise SystemExit(1)
