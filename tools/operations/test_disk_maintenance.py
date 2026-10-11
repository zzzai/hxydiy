import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


MODULE = Path(__file__).resolve().parents[2] / 'deploy/diy/disk_maintenance.py'
SPEC = importlib.util.spec_from_file_location('disk_maintenance', MODULE)
OPS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OPS)
NAME = 'github-0123456789ab-1234'
CURRENT = 'github-abcdef012345-5678'
STATE = {'containers': ['container-id'], 'paths': []}


class DiskMaintenanceTests(unittest.TestCase):
    def link_current(self, target):
        link = self.root / 'current'
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
                           check=True, capture_output=True)
        else:
            link.symlink_to(target, target_is_directory=True)

    def unlink_current(self):
        if os.name == 'nt':
            os.rmdir(self.root / 'current')
        else:
            (self.root / 'current').unlink()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        for name in ('workspaces', 'releases', 'backups'):
            (self.root / name).mkdir()
        (self.root / 'releases' / CURRENT).mkdir()
        self.link_current(self.root / 'releases' / CURRENT)
        self.workspace = self.root / 'workspaces' / NAME
        self.release = self.root / 'releases' / NAME
        for directory in (self.workspace, self.release):
            directory.mkdir()
            (directory / 'source.txt').write_text('exact content')
        (self.release / 'MANIFEST.sha256').write_text(OPS.digest(self.release / 'source.txt') + '  ./source.txt\n')
        self.age()

    def age(self):
        for path in [self.workspace, *self.workspace.rglob('*')]:
            os.utime(path, (time.time() - OPS.MIN_AGE - 60,) * 2)

    def plan(self):
        return OPS.preview(self.root, state=STATE)

    def test_preview_is_read_only_and_apply_keeps_installed_release_and_backup(self):
        backup = self.root / 'backups' / 'important.dump'
        backup.write_text('do not touch')
        plan = self.plan()
        self.assertEqual(len(plan['candidates']), 1)
        self.assertTrue(self.workspace.is_dir())
        report = OPS.apply(self.root, plan, state_reader=lambda: STATE)
        self.assertEqual(report['removed_count'], 1)
        self.assertFalse(self.workspace.exists())
        self.assertEqual((self.release / 'source.txt').read_text(), 'exact content')
        self.assertTrue(backup.exists())

    def test_modified_or_extra_files_are_never_candidates(self):
        for name in ('source.txt', 'extra.txt'):
            with self.subTest(name=name):
                (self.workspace / name).write_text('unique work')
                self.age()
                self.assertEqual(self.plan()['candidates'], [])
                (self.workspace / 'source.txt').write_text('exact content')
                (self.workspace / 'extra.txt').unlink(missing_ok=True)
                self.age()

    def test_current_missing_release_bad_manifest_and_recent_workspace_are_protected(self):
        self.unlink_current()
        self.link_current(self.release)
        self.assertEqual(self.plan()['candidates'], [])
        self.unlink_current()
        self.link_current(self.root / 'releases' / CURRENT)
        manifest = self.release / 'MANIFEST.sha256'
        manifest.write_text('0' * 64 + '  ./source.txt\n')
        self.assertEqual(self.plan()['candidates'], [])
        manifest.write_text(OPS.digest(self.release / 'source.txt') + '  ./source.txt\n')
        os.utime(self.workspace, None)
        self.assertEqual(self.plan()['candidates'], [])
        self.age()
        (self.release / 'source.txt').unlink()
        self.assertEqual(self.plan()['candidates'], [])

    def test_traversal_and_changed_plan_abort_before_removal(self):
        plan = self.plan()
        plan['candidates'][0]['name'] = '../../backups'
        with self.assertRaises(ValueError):
            OPS.apply(self.root, plan, state_reader=lambda: STATE)
        plan = self.plan()
        (self.workspace / 'source.txt').write_text('changed')
        with self.assertRaises(ValueError):
            OPS.apply(self.root, plan, state_reader=lambda: STATE)
        self.assertTrue(self.workspace.exists())

    def test_active_process_mount_or_changed_container_blocks_removal(self):
        plan = self.plan()
        states = [dict(STATE, paths=[str(self.workspace / 'source.txt')]),
                  dict(STATE, mounts=[str(self.root / 'workspaces')]),
                  dict(STATE, containers=['different-container'])]
        for state in states:
            with self.subTest(state=state), self.assertRaises(ValueError):
                OPS.apply(self.root, plan, state_reader=lambda: state)
            self.assertTrue(self.workspace.exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink coverage runs on the isolated Linux fixture')
    def test_symlink_files_are_protected(self):
        (self.workspace / 'link').symlink_to(self.release / 'source.txt')
        self.assertEqual(self.plan()['candidates'], [])

    def test_sensitive_files_are_protected(self):
        (self.workspace / '.env').write_text('private')
        self.age()
        self.assertEqual(self.plan()['candidates'], [])

    def test_invalid_root_or_age_or_duplicate_target_is_rejected(self):
        for key, value in [('root', '/'), ('cutoff', time.time())]:
            plan = self.plan()
            plan[key] = value
            with self.assertRaises(ValueError):
                OPS.apply(self.root, plan, state_reader=lambda: STATE)
        plan = self.plan()
        plan['candidates'] *= 2
        with self.assertRaises(ValueError):
            OPS.apply(self.root, plan, state_reader=lambda: STATE)


if __name__ == '__main__':
    unittest.main()
