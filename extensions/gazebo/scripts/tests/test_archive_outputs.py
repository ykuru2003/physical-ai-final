"""Preservation and recovery contracts for local output archiving."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import archive_outputs as cleanup


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        fixture_root = (cleanup.ROOT / '.cache/test-runs').resolve()
        fixture_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=fixture_root)
        assert Path(self.temp.name).resolve().is_relative_to(fixture_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'scripts').mkdir()
        (self.root / '.cache/offline').mkdir(parents=True)
        (self.root / 'outputs/step2-evaluation/qualified').mkdir(parents=True)
        self.registry = self.root / 'scripts/destinations.json'
        self.registry.write_text(json.dumps({'destinations': [{'qualification': {'reports': [
            {'path': 'outputs/step2-evaluation/qualified/evaluation.json'},
        ]}}]}), encoding='utf-8')
        self.evidence = self.root / 'outputs/step2-evaluation/qualified/evaluation.json'
        self.evidence.write_bytes(b'actual evidence')
        self.current = self.root / 'outputs/local-ai-validation.json'
        self.current.write_bytes(b'current certificate')
        self.old = self.root / 'outputs/old.log'
        self.old.write_bytes(b'old log\x00\xff')
        (self.root / '.cache/offline/latest.json').write_text('{}', encoding='utf-8')

    def test_preview_preserves_evidence_certificates_and_latest_results_without_writes(self):
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*'))
        self.assertEqual(cleanup.plan_archive(self.root), [self.old])
        after = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*'))
        self.assertEqual(before, after)

    def test_verified_archive_is_recoverable_and_preserves_current_files(self):
        original = self.old.read_bytes()
        archive = cleanup.archive_files(self.root, cleanup.plan_archive(self.root))
        self.assertFalse(self.old.exists())
        self.assertEqual(self.evidence.read_bytes(), b'actual evidence')
        self.assertEqual(self.current.read_bytes(), b'current certificate')
        with zipfile.ZipFile(archive) as bundle:
            self.assertEqual(bundle.read('outputs/old.log'), original)
            manifest = json.loads(bundle.read('__archive_manifest__.json'))
            self.assertEqual(manifest[0]['sha256'], cleanup.digest(original))
        self.assertEqual(cleanup.plan_archive(self.root, include_work=True), [])

    def test_active_navigation_blocks_preview_and_apply(self):
        for name in cleanup.ACTIVE_MARKERS:
            marker = self.root / 'outputs' / name
            marker.touch()
            with self.subTest(marker=name), self.assertRaises(RuntimeError):
                cleanup.plan_archive(self.root)
            with self.assertRaises(RuntimeError):
                cleanup.archive_files(self.root, [self.old])
            marker.unlink()
        self.assertTrue(self.old.exists())

    def test_missing_optional_history_does_not_block_a_fresh_checkout(self):
        registry = json.loads(self.registry.read_text(encoding='utf-8'))
        registry['destinations'][0]['historical_reports'] = ['outputs/old-run/evaluation.json']
        self.registry.write_text(json.dumps(registry), encoding='utf-8')
        self.assertEqual(cleanup.plan_archive(self.root), [self.old])

    def test_optional_summary_logs_are_portable_but_cannot_escape_outputs(self):
        summary = self.root / 'outputs/step3-final-verification.json'
        summary.write_text(json.dumps({'integration_results': [
            {'path': 'outputs/language-goals/old-run/selection.json'},
        ]}), encoding='utf-8')
        self.assertEqual(cleanup.plan_archive(self.root), [self.old])
        summary.write_text(json.dumps({'integration_results': [
            {'path': 'scripts/destinations.json'},
        ]}), encoding='utf-8')
        with self.assertRaises(ValueError):
            cleanup.plan_archive(self.root)

    def test_outside_evidence_or_source_is_rejected(self):
        self.registry.write_text(json.dumps({'destinations': [{'historical_reports': [
            '../outside.json',
        ]}]}), encoding='utf-8')
        with self.assertRaises(ValueError):
            cleanup.plan_archive(self.root)
        with self.assertRaises(ValueError):
            cleanup.archive_files(self.root, [self.registry])
        self.assertTrue(self.old.exists())

    def test_concurrent_change_aborts_before_removing_sources(self):
        original_read = Path.read_bytes
        reads = 0

        def read(path):
            nonlocal reads
            if path == self.old:
                reads += 1
                if reads == 2:
                    path.write_bytes(b'new live data')
            return original_read(path)

        with patch.object(Path, 'read_bytes', read), self.assertRaises(RuntimeError):
            cleanup.archive_files(self.root, [self.old])
        self.assertEqual(self.old.read_bytes(), b'new live data')

    def test_work_is_opt_in_and_existing_archives_are_never_rearchived(self):
        work = self.root / 'work'
        work.mkdir()
        scratch = work / 'scratch.txt'
        scratch.write_text('backup', encoding='utf-8')
        (work / 'archive').mkdir()
        (work / 'archive/previous.zip').write_bytes(b'previous archive')
        self.assertNotIn(scratch, cleanup.plan_archive(self.root))
        self.assertIn(scratch, cleanup.plan_archive(self.root, include_work=True))
        archive = cleanup.archive_files(self.root, cleanup.plan_archive(self.root, include_work=True))
        self.assertFalse(scratch.exists())
        self.assertTrue((work / 'archive/previous.zip').exists())
        with zipfile.ZipFile(archive) as bundle:
            self.assertEqual(bundle.read('work/scratch.txt'), b'backup')


if __name__ == '__main__':
    unittest.main()
