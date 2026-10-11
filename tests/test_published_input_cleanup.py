import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('cleanup_inputs', ROOT / 'deploy/diy/cleanup-published-inputs.py')
OPS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OPS)
NAME = 'github-0123456789ab-1234'
STATE = {'paths': [], 'mounts': []}


class PublishedInputCleanupTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.workspace = self.root / 'workspaces' / NAME
        self.release = self.root / 'releases' / NAME
        self.upload = self.root / 'incoming' / NAME
        for directory in (self.workspace, self.release, self.upload):
            directory.mkdir(parents=True)
        for directory in (self.workspace, self.release):
            (directory / 'source.txt').write_text('deployed content')
        (self.release / 'MANIFEST.sha256').write_text(OPS.ops.digest(self.release / 'source.txt') + '  ./source.txt\n')
        if os.name == 'nt':
            import subprocess
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(self.root / 'current'), str(self.release)],
                           check=True, capture_output=True)
        else:
            (self.root / 'current').symlink_to(self.release, target_is_directory=True)
        self.archive = self.upload / (NAME + '.tar.gz')
        self.archive.write_bytes(b'verified upload')
        (self.upload / (self.archive.name + '.sha256')).write_text(OPS.ops.digest(self.archive) + '  ' + self.archive.name)
        self.backup = self.root / 'backups' / 'database.dump'
        self.backup.parent.mkdir()
        self.backup.write_text('preserved')

    def test_removes_only_the_successful_current_input_and_preserves_release_and_backups(self):
        report = OPS.cleanup(self.root, NAME, state_reader=lambda: STATE)
        self.assertEqual(report['cleanup'], 'completed')
        self.assertFalse(self.workspace.exists())
        self.assertFalse(self.upload.exists())
        self.assertTrue(self.release.exists())
        self.assertTrue(self.backup.exists())

    def test_failed_or_different_release_is_not_cleaned(self):
        with self.assertRaises(ValueError):
            OPS.cleanup(self.root, 'github-abcdef012345-9999', state_reader=lambda: STATE)
        self.assertTrue(self.workspace.exists())
        self.assertTrue(self.archive.exists())

    def test_changed_workspace_corrupt_upload_or_extra_files_preserve_all_inputs(self):
        changes = [(self.workspace / 'source.txt', b'changed'),
                   (self.archive, b'corrupt'), (self.upload / 'extra.txt', b'unique')]
        for path, value in changes:
            original = path.read_bytes() if path.exists() else None
            path.write_bytes(value)
            with self.subTest(path=path), self.assertRaises(ValueError):
                OPS.cleanup(self.root, NAME, state_reader=lambda: STATE)
            self.assertTrue(self.workspace.exists())
            if original is None:
                path.unlink()
            else:
                path.write_bytes(original)

    def test_active_input_is_not_cleaned(self):
        with self.assertRaises(ValueError):
            OPS.cleanup(self.root, NAME, state_reader=lambda: dict(STATE, paths=[str(self.archive)]))
        self.assertTrue(self.workspace.exists())
        self.assertTrue(self.archive.exists())


if __name__ == '__main__':
    unittest.main()
