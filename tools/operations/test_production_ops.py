import importlib.util
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


MODULE = Path(__file__).with_name('production_ops.py')


class ProductionOpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('production_ops', MODULE)
        cls.ops = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ops)

    def test_monitor_rejects_missing_stale_and_unverified_backup(self):
        now = datetime(2026, 10, 1, tzinfo=timezone.utc)
        disk = {'used_percent': 70, 'available_bytes': 6 * 1024 ** 3}
        health = {'environment': 'production', 'status': 'ok'}
        for backup in (None, {'restored': False, 'created_at': now.isoformat()},
                       {'restored': True, 'created_at': (now - timedelta(hours=27)).isoformat()}):
            report = self.ops.assess(disk, health, backup, now)
            self.assertEqual(report['severity'], 'critical')
            self.assertTrue(any(item.startswith('backup_') for item in report['issues']))

    def test_monitor_disk_boundaries_and_health(self):
        now = datetime(2026, 10, 1, tzinfo=timezone.utc)
        backup = {'restored': True, 'created_at': now.isoformat(), 'checksum_valid': True}
        health = {'environment': 'production', 'status': 'ok'}
        cases = [(79, 4 * 1024 ** 3, 'ok'), (80, 4 * 1024 ** 3, 'warning'),
                 (90, 4 * 1024 ** 3, 'critical'), (70, 3 * 1024 ** 3 - 1, 'critical')]
        for used, available, severity in cases:
            report = self.ops.assess({'used_percent': used, 'available_bytes': available}, health, backup, now)
            self.assertEqual(report['severity'], severity)
        self.assertIn('health_failed', self.ops.assess({'used_percent': 50, 'available_bytes': 8 * 1024 ** 3}, {}, backup, now)['issues'])

    def test_backup_restores_only_unique_rehearsal_database_and_reports_checksum(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []

            def run(args, **kwargs):
                calls.append(args)
                if 'pg_dump' in args:
                    kwargs['stdout'].write(b'PGDMP-test-data')
                return subprocess.CompletedProcess(args, 0, stdout=b'1\n')

            report = self.ops.backup(Path(folder), run=run, capacity_bytes=4 * 1024 ** 3)
            self.assertTrue(report['restored'])
            self.assertEqual(report['sha256'], '875f90f1f410b47eed017976da39c98a045c45b79a224a118bf3fa2519063494')
            restore = next(args for args in calls if 'pg_restore' in args)
            self.assertRegex(restore[restore.index('-d') + 1], r'^hxy_diy_ops_[0-9a-f]{24}$')
            self.assertTrue(any('DROP DATABASE' in str(args) for args in calls))
            metadata = json.loads((Path(folder) / 'backups/daily/latest.json').read_text())
            self.assertEqual(metadata['sha256'], report['sha256'])

    def test_backup_failure_cleans_rehearsal_without_publishing_success(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []

            def run(args, **kwargs):
                calls.append(args)
                if 'pg_dump' in args:
                    kwargs['stdout'].write(b'PGDMP-test-data')
                if 'pg_restore' in args:
                    raise subprocess.CalledProcessError(1, args)
                return subprocess.CompletedProcess(args, 0, stdout=b'1\n')

            with self.assertRaises(subprocess.CalledProcessError):
                self.ops.backup(Path(folder), run=run, capacity_bytes=4 * 1024 ** 3)
            self.assertTrue(any('DROP DATABASE' in str(args) for args in calls))
            self.assertFalse((Path(folder) / 'backups/daily/latest.json').exists())

    def test_low_capacity_stops_before_dump(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []
            with self.assertRaises(ValueError):
                self.ops.backup(Path(folder), run=lambda *args, **kwargs: calls.append(args), capacity_bytes=1)
            self.assertEqual(calls, [])

    def test_backup_manifest_rejects_corruption_and_path_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            daily = base / 'backups/daily'
            daily.mkdir(parents=True)
            (daily / 'test.dump').write_bytes(b'changed')
            (daily / 'latest.json').write_text(json.dumps({'file': 'test.dump', 'sha256': '0' * 64, 'restored': True}))
            self.assertFalse(self.ops.read_backup(base)['checksum_valid'])
            (daily / 'latest.json').write_text(json.dumps({'file': '../../outside.dump', 'restored': True}))
            self.assertIsNone(self.ops.read_backup(base))


if __name__ == '__main__':
    unittest.main()
