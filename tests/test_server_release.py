"""Focused isolated tests for the server-controlled release entry.

These tests never build business source or touch production. They exercise the
entry's gates with tiny fixtures and a guarded run double that refuses to call
deploy-production.sh unless a test explicitly allows the single dispatch.
"""
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'server_release', ROOT / 'deploy/diy/server_release.py')
SR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SR)

PREV_RELEASE = 'github-386b572ce599-43589601497'


def make_root(tmp: Path) -> Path:
    root = tmp / 'release-root'
    (root / 'workspaces').mkdir(parents=True)
    (root / 'releases').mkdir()
    (root / 'release-records').mkdir()
    prev = root / 'releases' / PREV_RELEASE
    (prev / 'admin-react' / 'dist').mkdir(parents=True)
    (prev / 'admin-react' / 'dist' / 'staff-learning-build.json').write_text(
        '{"enabled": true, "commit": "386b572ce59938e4ef87a7ae840a158d994e22cf"}\n',
        encoding='utf-8')
    (root / 'current').symlink_to(prev, target_is_directory=True)
    return root


def make_source_tree(directory: Path) -> None:
    (directory / 'hxy-server').mkdir(parents=True)
    (directory / 'hxy-server' / 'requirements.txt').write_text('flask\n', encoding='utf-8')
    (directory / 'hxy-server' / 'alembic' / 'versions').mkdir(parents=True)
    (directory / 'hxy-server' / 'alembic' / 'versions' / 'x.py').write_text('', encoding='utf-8')
    (directory / 'diy-web' / 'dist').mkdir(parents=True)
    (directory / 'diy-web' / 'dist' / 'index.html').write_text('<html>diy</html>\n', encoding='utf-8')
    (directory / 'admin-react' / 'dist').mkdir(parents=True)
    (directory / 'admin-react' / 'dist' / 'index.html').write_text('<html>admin</html>\n', encoding='utf-8')
    (directory / 'deploy' / 'diy').mkdir(parents=True)
    for name in ('deploy-production.sh', 'create-release.sh', 'activate-release.sh',
                 'check-capacity.sh'):
        script = directory / 'deploy' / 'diy' / name
        script.write_text('#!/bin/bash\n', encoding='utf-8')
        script.chmod(0o755)
    (directory / 'deploy' / 'diy' / 'docker-compose.hxy.yml').write_text(
        'services: {}\n', encoding='utf-8')


def make_git_repo(tmp: Path, dirty: bool = False):
    repo = tmp / 'source'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    subprocess.run(['git', '-C', str(repo), 'config', 'user.email', 'test@example.com'], check=True)
    subprocess.run(['git', '-C', str(repo), 'config', 'user.name', 'test'], check=True)
    (repo / 'file.txt').write_text('base', encoding='utf-8')
    subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(repo), 'commit', '-q', '-m', 'base'], check=True)
    sha = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                         check=True, capture_output=True, text=True).stdout.strip()
    if dirty:
        (repo / 'file.txt').write_text('dirty', encoding='utf-8')
    return repo, sha


def make_git_repo_with_source(tmp: Path):
    repo, sha = make_git_repo(tmp)
    make_source_tree(repo)
    subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(repo), 'commit', '-q', '-m', 'source'], check=True)
    sha = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                         check=True, capture_output=True, text=True).stdout.strip()
    return repo, sha


class RecordingRun:
    """Records calls; fails loudly on any command not explicitly configured."""

    def __init__(self):
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        joined = ' '.join(args)
        if 'node --version' in joined:
            return subprocess.CompletedProcess(list(args), 0, stdout='v20.19.5\n', stderr='')
        if 'npm --version' in joined:
            return subprocess.CompletedProcess(list(args), 0, stdout='11.7.0\n', stderr='')
        if 'npm ci' in joined or 'npm run build' in joined:
            return subprocess.CompletedProcess(list(args), 0, stdout='', stderr='')
        raise AssertionError('unexpected command: ' + joined)


class GuardedRun:
    """Runs real commands except deploy-production.sh, which is refused by default."""

    def __init__(self, allow_deploy=False, deploy_stdout='', deploy_side_effect=None):
        self.calls = []
        self.allow_deploy = allow_deploy
        self.deploy_stdout = deploy_stdout
        self.deploy_side_effect = deploy_side_effect

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        joined = ' '.join(args)
        if 'deploy-production.sh' in joined:
            if not self.allow_deploy:
                raise AssertionError('deploy-production.sh invoked unexpectedly')
            if self.deploy_side_effect is not None:
                self.deploy_side_effect()
            return subprocess.CompletedProcess(list(args), 0,
                                               stdout=self.deploy_stdout, stderr='')
        return subprocess.run(list(args), **kwargs)

    def deployed(self):
        return any('deploy-production.sh' in ' '.join(call) for call in self.calls)


def make_acceptance(sha, previous, manifest_sha256, release_id, evidence):
    return {'schema': 'server-release-acceptance@1', 'release_id': release_id,
            'source_sha': sha, 'previous_release': previous,
            'manifest_sha256': manifest_sha256, 'evidence': evidence,
            'accepted_at': '2026-11-14T00:00:00Z'}


def prepare_workspace(tmp, root, sha):
    build_report = {'node': 'v20.19.5', 'npm': '11.7.0',
                    'staff_learning_enabled': True,
                    'learning_source': 'current-release-marker',
                    'customer_base_path': '/', 'serial': True,
                    'locked_dependencies': True, 'total_seconds': 0.0, 'steps': []}
    release_id = 'server-' + sha[:12] + '-1234567890'
    workspace = SR.export_workspace(tmp / 'source', sha, release_id, build_report, root)
    manifest_sha256 = SR.read_build_report(workspace)['manifest_sha256']
    return release_id, workspace, manifest_sha256


class SourceValidationTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def test_verify_source_clean_accepts_exact_sha(self):
        repo, sha = make_git_repo(self.tmp)
        self.assertEqual(SR.verify_source_clean(repo, sha), sha)

    def test_verify_source_clean_rejects_wrong_sha(self):
        repo, _ = make_git_repo(self.tmp)
        with self.assertRaises(ValueError) as caught:
            SR.verify_source_clean(repo, '0' * 40)
        self.assertIn('head_mismatch', str(caught.exception))

    def test_verify_source_clean_rejects_dirty_source(self):
        repo, sha = make_git_repo(self.tmp, dirty=True)
        with self.assertRaises(ValueError) as caught:
            SR.verify_source_clean(repo, sha)
        self.assertIn('dirty_source', str(caught.exception))

    def test_validate_release_id_rejects_traversal_and_bad_format(self):
        for bad in ('server-0123456789ab-../../etc/passwd',
                    'github-0123456789ab-1234',
                    'server-0123456789ab-abc',
                    'server-0123456789ab',
                    ''):
            with self.subTest(value=bad), self.assertRaises(ValueError) as caught:
                SR.validate_release_id(bad)
            self.assertIn('invalid_release_id', str(caught.exception))

    def test_release_id_must_match_source_sha(self):
        with self.assertRaises(ValueError) as caught:
            SR.release_id_for_sha('server-aaaaaaaaaaaa-1', 'b' * 40)
        self.assertIn('release_id_sha_mismatch', str(caught.exception))


class AcceptanceTests(unittest.TestCase):
    def test_acceptance_rejects_bare_true_flag(self):
        with self.assertRaises(ValueError):
            SR.validate_acceptance({'accepted': True}, PREV_RELEASE)

    def test_acceptance_rejects_missing_evidence(self):
        record = {'schema': 'server-release-acceptance@1', 'source_sha': 'a' * 40,
                  'previous_release': PREV_RELEASE, 'manifest_sha256': 'c' * 64,
                  'evidence': []}
        with self.assertRaises(ValueError) as caught:
            SR.validate_acceptance(record, PREV_RELEASE)
        self.assertIn('acceptance_evidence_missing', str(caught.exception))

    def test_acceptance_rejects_unexpected_current(self):
        record = {'schema': 'server-release-acceptance@1', 'source_sha': 'a' * 40,
                  'previous_release': 'github-d50941d67579-43457778128',
                  'manifest_sha256': 'c' * 64,
                  'evidence': [{'kind': 'test', 'path': 'x.json', 'sha256': 'd' * 64}]}
        with self.assertRaises(ValueError) as caught:
            SR.validate_acceptance(record, PREV_RELEASE)
        self.assertIn('unexpected_current_release', str(caught.exception))

    def test_acceptance_rejects_invalid_source_sha(self):
        record = {'schema': 'server-release-acceptance@1', 'source_sha': 'not-a-sha',
                  'previous_release': PREV_RELEASE, 'manifest_sha256': 'c' * 64,
                  'evidence': [{'kind': 'test', 'path': 'x.json', 'sha256': 'd' * 64}]}
        with self.assertRaises(ValueError) as caught:
            SR.validate_acceptance(record, PREV_RELEASE)
        self.assertIn('acceptance_source_sha_invalid', str(caught.exception))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.root = make_root(self.tmp)
        repo, sha = make_git_repo_with_source(self.tmp)
        self.repo = repo
        self.sha = sha
        self.release_id, self.workspace, self.manifest = prepare_workspace(
            self.tmp, self.root, sha)
        self.evidence = self.workspace / 'evidence' / 'api.json'
        self.evidence.write_text('{"passed": 12}\n', encoding='utf-8')
        self.good = [{'kind': 'test', 'path': 'api.json',
                      'sha256': SR.digest_file(self.evidence)}]

    def test_evidence_hash_mismatch_rejected(self):
        record = make_acceptance(self.sha, PREV_RELEASE, self.manifest,
                                 self.release_id,
                                 [{'kind': 'test', 'path': 'api.json',
                                   'sha256': '0' * 64}])
        with self.assertRaises(ValueError) as caught:
            SR.validate_evidence(record, self.workspace)
        self.assertIn('evidence_hash_mismatch', str(caught.exception))

    def test_evidence_path_traversal_rejected(self):
        for path in ('../api.json', 'a/b.json'):
            record = make_acceptance(self.sha, PREV_RELEASE, self.manifest,
                                     self.release_id,
                                     [{'kind': 'test', 'path': path,
                                       'sha256': '0' * 64}])
            with self.subTest(path=path), self.assertRaises(ValueError) as caught:
                SR.validate_evidence(record, self.workspace)
            self.assertIn('evidence_path_unsafe', str(caught.exception))

    def test_evidence_empty_and_missing_files_rejected(self):
        empty = self.workspace / 'evidence' / 'empty.json'
        empty.write_text('', encoding='utf-8')
        for path, reason in (('empty.json', 'evidence_file_empty'),
                             ('missing.json', 'evidence_file_missing')):
            record = make_acceptance(self.sha, PREV_RELEASE, self.manifest,
                                     self.release_id,
                                     [{'kind': 'test', 'path': path,
                                       'sha256': '0' * 64}])
            with self.subTest(path=path), self.assertRaises(ValueError) as caught:
                SR.validate_evidence(record, self.workspace)
            self.assertIn(reason, str(caught.exception))


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.root = make_root(self.tmp)

    def test_export_rejects_duplicate_release_id(self):
        repo, sha = make_git_repo_with_source(self.tmp)
        report = {'node': 'v', 'npm': 'n', 'staff_learning_enabled': False,
                  'learning_source': 'default-false', 'customer_base_path': '/',
                  'serial': True, 'locked_dependencies': True,
                  'total_seconds': 0.0, 'steps': []}
        release_id = 'server-' + sha[:12] + '-1234567890'
        SR.export_workspace(repo, sha, release_id, report, self.root)
        with self.assertRaises(ValueError) as caught:
            SR.export_workspace(repo, sha, release_id, report, self.root)
        self.assertIn('workspace_exists', str(caught.exception))

    def test_export_rejects_symlink_escape(self):
        repo, sha = make_git_repo_with_source(self.tmp)
        (repo / 'hxy-server' / 'evil').symlink_to('/etc/passwd')
        report = {'node': 'v', 'npm': 'n', 'staff_learning_enabled': False,
                  'learning_source': 'default-false', 'customer_base_path': '/',
                  'serial': True, 'locked_dependencies': True,
                  'total_seconds': 0.0, 'steps': []}
        with self.assertRaises(ValueError) as caught:
            SR.export_workspace(repo, sha, 'server-' + sha[:12] + '-1234567890',
                                report, self.root)
        self.assertIn('symlink_input', str(caught.exception))

    def test_bad_artifact_hash_rejected(self):
        repo, sha = make_git_repo_with_source(self.tmp)
        release_id, workspace, manifest = prepare_workspace(
            self.tmp, self.root, sha)
        (workspace / 'diy-web' / 'dist' / 'index.html').write_text(
            'tampered', encoding='utf-8')
        with self.assertRaises(ValueError) as caught:
            SR.verify_workspace(workspace, sha, release_id, manifest)
        self.assertIn('manifest_content_mismatch', str(caught.exception))

    def test_incomplete_attempt_rejected(self):
        repo, sha = make_git_repo_with_source(self.tmp)
        release_id, workspace, manifest = prepare_workspace(
            self.tmp, self.root, sha)
        (workspace / 'hxy-server').rename(workspace / 'hxy-server-removed')
        with self.assertRaises(ValueError) as caught:
            SR.verify_workspace(workspace, sha, release_id, manifest)
        self.assertIn('missing_deploy_root', str(caught.exception))


class PublishTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.root = make_root(self.tmp)
        self.repo, self.sha = make_git_repo_with_source(self.tmp)
        self.release_id, self.workspace, self.manifest = prepare_workspace(
            self.tmp, self.root, self.sha)
        self.evidence = self.workspace / 'evidence' / 'api.json'
        self.evidence.write_text('{"passed": 12}\n', encoding='utf-8')
        self.evidence_item = {'kind': 'test', 'path': 'api.json',
                              'sha256': SR.digest_file(self.evidence)}

    def acceptance(self, **overrides):
        record = make_acceptance(self.sha, PREV_RELEASE, self.manifest,
                                 self.release_id, [self.evidence_item])
        record.update(overrides)
        return record

    def test_rejection_never_dispatches_deploy(self):
        cases = [
            ('wrong_source_sha', {'source_sha': '0' * 40}),
            ('wrong_previous', {'previous_release': 'github-d50941d67579-43457778128'}),
            ('wrong_manifest', {'manifest_sha256': '0' * 64}),
            ('empty_evidence', {'evidence': []}),
        ]
        for name, overrides in cases:
            run = GuardedRun(allow_deploy=False)
            with self.subTest(case=name), self.assertRaises(ValueError):
                SR.publish(self.root, self.release_id, self.acceptance(**overrides),
                           repo=str(self.repo), run=run)
            self.assertFalse(run.deployed(), name)

    def test_changed_current_before_dispatch_rejected(self):
        other = self.root / 'releases' / 'github-d50941d67579-43457778128'
        other.mkdir()
        (self.root / 'current').unlink()
        (self.root / 'current').symlink_to(other, target_is_directory=True)
        run = GuardedRun(allow_deploy=False)
        with self.assertRaises(ValueError) as caught:
            SR.publish(self.root, self.release_id, self.acceptance(),
                       repo=str(self.repo), run=run)
        self.assertIn('unexpected_current_release', str(caught.exception))
        self.assertFalse(run.deployed())

    def test_existing_receipt_reconciled_without_repeat(self):
        release_dir = self.root / 'releases' / self.release_id
        release_dir.mkdir()
        (release_dir / 'MANIFEST.sha256').write_text('', encoding='utf-8')
        (self.root / 'current').unlink()
        (self.root / 'current').symlink_to(release_dir, target_is_directory=True)
        run = GuardedRun(allow_deploy=False)
        result = SR.publish(self.root, self.release_id, self.acceptance(),
                            repo=str(self.repo), run=run)
        self.assertEqual(result['status'], 'already_deployed')
        self.assertFalse(run.deployed())

    def test_inconsistent_existing_release_rejected(self):
        (self.root / 'releases' / self.release_id).mkdir()
        run = GuardedRun(allow_deploy=False)
        with self.assertRaises(ValueError) as caught:
            SR.publish(self.root, self.release_id, self.acceptance(),
                       repo=str(self.repo), run=run)
        self.assertIn('inconsistent_existing_release', str(caught.exception))
        self.assertFalse(run.deployed())

    def test_competing_deploy_between_validation_and_activation_rejected(self):
        stdout = ('deployed release=%s previous=github-d50941d67579-43457778128 '
                  'backup=/tmp/x.dump\n' % self.release_id)
        run = GuardedRun(allow_deploy=True, deploy_stdout=stdout)
        with self.assertRaises(ValueError) as caught:
            SR.publish(self.root, self.release_id, self.acceptance(),
                       repo=str(self.repo), run=run)
        self.assertIn('deploy_previous_changed', str(caught.exception))
        self.assertEqual(sum(1 for c in run.calls
                             if 'deploy-production.sh' in ' '.join(c)), 1)

    def test_publish_success_emits_pending_backup_and_dispatches_once(self):
        stdout = ('deployed release=%s previous=%s backup=/tmp/x.dump\n'
                  % (self.release_id, PREV_RELEASE))

        def activate():
            target = self.root / 'releases' / self.release_id
            target.mkdir()
            (self.root / 'current').unlink()
            (self.root / 'current').symlink_to(target, target_is_directory=True)

        run = GuardedRun(allow_deploy=True, deploy_stdout=stdout,
                         deploy_side_effect=activate)
        result = SR.publish(self.root, self.release_id, self.acceptance(),
                            repo=str(self.repo), run=run)
        self.assertEqual(result['status'], 'published')
        self.assertEqual(sum(1 for c in run.calls
                             if 'deploy-production.sh' in ' '.join(c)), 1)
        record_path = (self.root / 'release-records' /
                       ('pending-github-backup-' + self.release_id + '.json'))
        self.assertTrue(record_path.is_file())
        record = json.loads(record_path.read_text(encoding='utf-8'))
        self.assertEqual(record['source_sha'], self.sha)
        self.assertEqual(record['github_backup'], 'pending')
        self.assertTrue((self.root / 'release-records' /
                         (self.release_id + '.bundle')).is_file())


class BuildSettingsTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.root = make_root(self.tmp)

    def test_read_build_settings_preserves_learning_enabled(self):
        settings = SR.read_build_settings(self.root)
        self.assertTrue(settings['staff_learning_enabled'])
        self.assertEqual(settings['learning_source'], 'current-release-marker')

    def test_read_build_settings_defaults_false_when_marker_absent(self):
        (self.root / 'releases' / PREV_RELEASE / 'admin-react' / 'dist' /
         'staff-learning-build.json').unlink()
        settings = SR.read_build_settings(self.root)
        self.assertFalse(settings['staff_learning_enabled'])
        self.assertEqual(settings['learning_source'], 'default-false')

    def test_build_preserves_flag_serial_order_and_writes_marker(self):
        make_source_tree(self.tmp / 'source')
        run = RecordingRun()
        sha = 'c' * 40
        report = SR.build_source(self.tmp / 'source', sha,
                                 {'staff_learning_enabled': True,
                                  'learning_source': 'current-release-marker',
                                  'customer_base_path': '/'}, run=run)
        order = [' '.join(args) for args, _ in run.calls]
        self.assertEqual(order[0], 'node --version')
        self.assertEqual(order[1], 'npm --version')
        self.assertTrue(order[2].startswith('nice -n 19 npm ci'),
                        'locked install runs first and at low priority')
        diy_build = order.index('nice -n 19 npm run build')
        admin_ci = order.index('nice -n 19 npm ci', diy_build)
        self.assertLess(diy_build, admin_ci, 'customer must build before admin')
        admin_build = [call for call in run.calls
                       if 'npm run build' in ' '.join(call[0])
                       and 'admin-react' in str(call[1].get('cwd'))]
        self.assertEqual(len(admin_build), 1)
        self.assertEqual(admin_build[0][1]['env']['VITE_STAFF_LEARNING_ENABLED'],
                         'true')
        self.assertTrue(report['staff_learning_enabled'])
        marker = self.tmp / 'source' / 'admin-react' / 'dist' / 'staff-learning-build.json'
        self.assertTrue(marker.is_file())
        data = json.loads(marker.read_text(encoding='utf-8'))
        self.assertTrue(data['enabled'])
        self.assertEqual(data['commit'], sha)


class RefTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.repo, self.first = make_git_repo(self.tmp)
        (self.repo / 'second.txt').write_text('second', encoding='utf-8')
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'commit', '-q', '-m', 'second'],
                       check=True)
        self.second = subprocess.run(['git', '-C', str(self.repo), 'rev-parse', 'HEAD'],
                                     check=True, capture_output=True,
                                     text=True).stdout.strip()

    def test_init_advance_cas_fast_forward(self):
        self.assertEqual(SR.init_accepted_ref(str(self.repo), self.first)['status'],
                         'initialized')
        self.assertEqual(SR.show_accepted_ref(str(self.repo)), self.first)
        result = SR.advance_accepted_ref(str(self.repo), self.second, self.first)
        self.assertEqual(result['status'], 'advanced')
        self.assertEqual(SR.show_accepted_ref(str(self.repo)), self.second)

    def test_advance_rejects_wrong_expect(self):
        SR.init_accepted_ref(str(self.repo), self.first)
        with self.assertRaises(ValueError) as caught:
            SR.advance_accepted_ref(str(self.repo), self.second, '0' * 40)
        self.assertIn('ref_compare_and_swap_failed', str(caught.exception))

    def test_advance_rejects_non_fast_forward(self):
        SR.init_accepted_ref(str(self.repo), self.second)
        with self.assertRaises(ValueError) as caught:
            SR.advance_accepted_ref(str(self.repo), self.first, self.second)
        self.assertIn('ref_not_fast_forward', str(caught.exception))


class LegacyGateTests(unittest.TestCase):
    def test_deploy_production_gates_remain_intact(self):
        text = (ROOT / 'deploy' / 'diy' / 'deploy-production.sh').read_text(
            encoding='utf-8')
        self.assertIn('approved_migrations=(', text)
        self.assertIn("'20261114_member_consumption.py'", text)
        self.assertIn('Unapproved Alembic migration change detected', text)
        self.assertIn('flock -n', text)
        self.assertIn('trap rollback ERR', text)


if __name__ == '__main__':
    unittest.main()
