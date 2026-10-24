"""Archive old output and optional work files after verifying every ZIP member.

Default is a preview. --apply writes a local ZIP under work/archive, verifies
its SHA-256 manifest, then removes only the matching archived source files.
Runtime certificates, referenced evidence and current logs stay in place.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_MARKERS = ('navigation.lock', 'step2-autotest.request', 'step2-autotest.running')
KEEP_OUTPUTS = (
    '.gitkeep', 'local-ai-validation.json', 'step3-final-verification.json',
    'step2-run.json', 'step2-run.log', 'step3-full-check.log',
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked_file(root, path):
    resolved = path.resolve()
    allowed = ((root / 'outputs').resolve(), (root / 'work').resolve())
    if path.is_symlink() or not any(resolved.is_relative_to(base) for base in allowed):
        raise ValueError(f'Archive source outside outputs/work: {path}')
    if any(parent.is_symlink() for parent in path.parents if parent != root):
        raise ValueError(f'Symlink ancestor is not supported: {path}')
    return resolved


def assert_idle(root):
    for name in ACTIVE_MARKERS:
        if (root / 'outputs' / name).exists():
            raise RuntimeError(f'Navigation or automatic test pending/running: {name}')


def evidence_paths(root):
    output = (root / 'outputs').resolve()
    keep = {output / name for name in KEEP_OUTPUTS}
    registry = json.loads((root / 'scripts/destinations.json').read_text(encoding='utf-8-sig'))
    for destination in registry['destinations']:
        references = [(path, False) for path in destination.get('historical_reports', [])]
        references += [(record['path'], True) for record in destination.get('qualification', {}).get('reports', [])]
        for reference, required in references:
            path = (root / reference).resolve()
            if not path.is_relative_to(output):
                raise ValueError(f'Evidence reference outside outputs: {reference}')
            if not path.is_file() and not required:
                continue
            if not path.is_file():
                raise FileNotFoundError(f'Referenced evidence is missing: {path}')
            keep.add(path)
    final = output / 'step3-final-verification.json'
    if final.exists():
        report = json.loads(final.read_text(encoding='utf-8-sig'))
        for record in report.get('integration_results', []):
            path = Path(record['path'])
            if not path.is_absolute():
                path = root / path
            path = path.resolve()
            if not path.is_relative_to(output):
                raise ValueError(f'Final verification reference is outside outputs: {path}')
            if not path.is_file():
                continue  # Detailed local logs are optional on a fresh checkout.
            # Keep the complete run, including its stop log and world evaluation.
            keep.update(p.resolve() for p in path.parent.rglob('*') if p.is_file())
    return keep


def plan_archive(root, include_work=False):
    root = root.resolve()
    assert_idle(root)
    keep = evidence_paths(root)
    sources = []
    for path in sorted((root / 'outputs').rglob('*')):
        if not path.is_file():
            continue
        checked = checked_file(root, path)
        if checked in keep or checked.is_relative_to((root / 'outputs/offline').resolve()):
            continue
        sources.append(path)
    if include_work and (root / 'work').exists():
        archive = (root / 'work/archive').resolve()
        for path in sorted((root / 'work').rglob('*')):
            if path.is_file() and not path.resolve().is_relative_to(archive):
                checked_file(root, path)
                sources.append(path)
    return sources


def remove_empty_directories(root):
    for base in (root / 'outputs', root / 'work'):
        if not base.exists():
            continue
        for path in sorted(base.rglob('*'), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir() and not path.is_symlink():
                checked_file(root, path)
                if not any(path.iterdir()):
                    path.rmdir()


def archive_files(root, sources):
    root = root.resolve()
    assert_idle(root)
    if not sources:
        return None
    # Resolve and validate every source before creating the archive or removing files.
    sources = [checked_file(root, path) for path in sources]
    records = []
    archive_dir = root / 'work/archive'
    if not archive_dir.resolve().is_relative_to((root / 'work').resolve()):
        raise ValueError('Archive directory must stay within project work/')
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
    archive = archive_dir / f'history-{stamp}.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sources:
            data = path.read_bytes()
            relative = path.relative_to(root).as_posix()
            bundle.writestr(relative, data)
            records.append({'path': relative, 'bytes': len(data), 'sha256': digest(data)})
        bundle.writestr('__archive_manifest__.json', json.dumps(records, indent=2) + '\n')
    with zipfile.ZipFile(archive) as bundle:
        for record in records:
            if digest(bundle.read(record['path'])) != record['sha256']:
                raise RuntimeError('Archive verification failed; source files were kept')
    # Verify the entire live snapshot before removal; concurrent changes abort the cleanup.
    assert_idle(root)
    for path, record in zip(sources, records):
        checked_file(root, path)
        if digest(path.read_bytes()) != record['sha256']:
            raise RuntimeError(f'Source changed during archive; sources were kept: {path}')
    for path, record in zip(sources, records):
        checked_file(root, path)
        if digest(path.read_bytes()) != record['sha256']:
            raise RuntimeError(f'Source changed before removal; recover earlier files from {archive}')
        path.unlink()
    remove_empty_directories(root)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Archive and remove verified old files')
    parser.add_argument('--include-work', action='store_true', help='Also archive local scratch files and test fixtures')
    args = parser.parse_args()
    sources = plan_archive(ROOT, args.include_work)
    print(f'{"ARCHIVE" if args.apply else "PREVIEW"}: {len(sources)} files, '
          f'{sum(path.stat().st_size for path in sources):,} bytes')
    if args.apply:
        archive = archive_files(ROOT, sources)
        print(f'Archive: {archive}' if archive else 'Nothing to archive.')
    else:
        for path in sources:
            print(path.relative_to(ROOT).as_posix())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
