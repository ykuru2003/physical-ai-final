"""Explore candidates; enable only after three consecutive Gazebo world-position PASS runs."""
import argparse
import json

from destination_control import (ROOT, REGISTRY, digest, evaluate, fingerprint,
                                 load_registry, navigation_lock, report_passes, run_id, stop_robot)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids', nargs='+', default=['south_station', 'south_near', 'west_station'])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if not 3 <= args.repeats <= 10:
        parser.error('--repeats must be between 3 and 10')
    registry = load_registry()
    by_id = {d['id']: d for d in registry['destinations']}
    if len(set(args.ids)) != len(args.ids) or any(i not in by_id for i in args.ids):
        parser.error('Use distinct registered IDs')
    if args.check_only:
        print(json.dumps([{'id': i, 'goal': by_id[i]['goal'], 'repeats': args.repeats} for i in args.ids], indent=2))
        return 0
    batch = run_id()
    summary = {'type': 'GAZEBO_WORLD_QUALIFICATION', 'candidates': [], 'status': 'INCOMPLETE'}
    folder = ROOT / 'outputs/destination-qualification' / batch
    folder.mkdir(parents=True, exist_ok=True)
    with navigation_lock():
        try:
            initial = fingerprint()
            for ident in args.ids:
                destination = by_id[ident]
                # Invalidate old evidence before attempting requalification.
                destination.pop('qualification', None)
                destination['state'] = 'pending_current_runtime_qualification'
                REGISTRY.write_text(json.dumps(registry, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
                record = {'id': ident, 'goal': destination['goal'], 'reports': [], 'qualified': False}
                summary['candidates'].append(record)
                for index in range(args.repeats):
                    output = ROOT / 'outputs/step2-evaluation' / f'qualify-{batch}-{ident}-{index+1}'
                    print(f'Evaluating {ident} {index+1}/{args.repeats}: {destination["goal"]}', flush=True)
                    result = evaluate(destination['goal'], output)
                    path = output / 'evaluation.json'
                    record['reports'].append({'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(path)})
                    if not report_passes(result, destination['goal']):
                        break
                if fingerprint() != initial:
                    raise RuntimeError('Simulation/controller changed during qualification')
                if len(record['reports']) == args.repeats and all(
                        report_passes(json.loads((ROOT / r['path']).read_text()), destination['goal'])
                        for r in record['reports']):
                    if stop_robot(folder / 'stop.log') != 'CONFIRMED_STATIONARY':
                        raise RuntimeError('Cannot confirm stop; destination not qualified')
                    destination['state'] = 'qualified'
                    destination['qualification'] = {'fingerprint': initial, 'reports': record['reports'],
                                                    'provenance': 'repeated_world_evaluation'}
                    temporary = REGISTRY.with_suffix('.json.tmp')
                    temporary.write_text(json.dumps(registry, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
                    temporary.replace(REGISTRY)
                    record['qualified'] = True
                    summary['status'] = 'PASS'
                    break
            if summary['status'] != 'PASS':
                summary['status'] = 'FAIL'
        except (Exception, KeyboardInterrupt) as error:
            summary['reason'] = str(error) or 'Interrupted'
        finally:
            summary['stop'] = stop_robot(folder / 'stop.log')
            if summary['stop'] != 'CONFIRMED_STATIONARY':
                summary['status'] = 'STOP_UNCONFIRMED'
            (folder / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
