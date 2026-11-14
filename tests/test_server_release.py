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
import shutil
import io
from contextlib import redirect_stdout
from unittest import mock
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
            'accepted_at': SR.utcnow(), 'build_report_sha256': 'b' * 64,
            'required_checks': ['test']}


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
                  'evidence': [], 'build_report_sha256': 'b' * 64,
                  'release_id': 'server-aaaaaaaaaaaa-1', 'accepted_at': SR.utcnow(),
                  'required_checks': ['test']}
        with self.assertRaises(ValueError) as caught:
            SR.validate_acceptance(record, PREV_RELEASE)
        self.assertIn('acceptance_evidence_missing', str(caught.exception))

    def test_acceptance_rejects_unexpected_current(self):
        record = {'schema': 'server-release-acceptance@1', 'source_sha': 'a' * 40,
                  'previous_release': 'github-d50941d67579-43457778128',
                  'manifest_sha256': 'c' * 64,
                  'evidence': [{'kind': 'test', 'path': 'x.json', 'sha256': 'd' * 64}],
                  'build_report_sha256': 'b' * 64, 'accepted_at': SR.utcnow(),
                  'release_id': 'server-aaaaaaaaaaaa-1', 'required_checks': ['test']}
        with self.assertRaises(ValueError) as caught:
            SR.validate_acceptance(record, PREV_RELEASE)
        self.assertIn('unexpected_current_release', str(caught.exception))

    def test_acceptance_rejects_invalid_source_sha(self):
        record = {'schema': 'server-release-acceptance@1', 'source_sha': 'not-a-sha',
                  'previous_release': PREV_RELEASE, 'manifest_sha256': 'c' * 64,
                  'evidence': [{'kind': 'test', 'path': 'x.json', 'sha256': 'd' * 64}],
                  'build_report_sha256': 'b' * 64, 'accepted_at': SR.utcnow(),
                  'release_id': 'server-aaaaaaaaaaaa-1', 'required_checks': ['test']}
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
        SR.init_accepted_ref(str(self.repo), self.sha)
        self.release_id, self.workspace, self.manifest = prepare_workspace(
            self.tmp, self.root, self.sha)
        self.evidence = self.workspace / 'evidence' / 'api.json'
        self.set_evidence()

    def set_evidence(self, **overrides):
        data = {'check': 'test', 'source_sha': self.sha, 'status': 'passed',
                'failed': 0, 'command': 'python3 -m unittest',
                'environment': 'isolated-fixture', 'timestamp': SR.utcnow()}
        data.update(overrides)
        self.evidence.write_text(json.dumps(data))
        self.evidence_item = {'kind': 'test', 'path': 'api.json',
                              'sha256': SR.digest_file(self.evidence)}

    def acceptance(self, **overrides):
        record = make_acceptance(self.sha, PREV_RELEASE, self.manifest,
                                 self.release_id, [self.evidence_item])
        record['build_report_sha256'] = SR.digest_file(self.workspace / 'build-report.json')
        record.update(overrides)
        return record

    def invoke(self, run, acceptance=None):
        return SR.publish(self.root, self.release_id, acceptance or self.acceptance(),
                          repo=str(self.repo), run=run)

    def successful_run(self):
        backup = self.root / 'backups' / 'test.dump'
        backup.parent.mkdir(exist_ok=True)
        backup.write_bytes(b'isolated backup fixture')
        stdout = ('deployed release=%s previous=%s backup=%s\n' %
                  (self.release_id, self.root / 'releases' / PREV_RELEASE, backup))
        def activate():
            target = self.root / 'releases' / self.release_id
            shutil.copytree(self.workspace, target)
            (self.root / 'current').unlink()
            (self.root / 'current').symlink_to(target, target_is_directory=True)
        return GuardedRun(allow_deploy=True, deploy_stdout=stdout, deploy_side_effect=activate)

    def test_rejection_never_dispatches_deploy(self):
        cases = [
            {'source_sha': '0' * 40}, {'previous_release': 'other'},
            {'manifest_sha256': '0' * 64}, {'evidence': []},
            {'build_report_sha256': '0' * 64}, {'required_checks': ['missing']},
            {'release_id': 'server-' + self.sha[:12] + '-999'},
        ]
        for overrides in cases:
            run = GuardedRun()
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.invoke(run, self.acceptance(**overrides))
            self.assertFalse(run.deployed())

    def test_failed_foreign_stale_and_contradictory_evidence_rejected(self):
        cases = [
            {'status': 'failed'}, {'source_sha': 'f' * 40},
            {'timestamp': '2000-01-01T00:00:00Z'},
            {'status': 'failed', 'success': True},
            {'status': 'passed', 'success': False},
            {'status': 'passed', 'failed': 1},
            {'command': ''}, {'environment': ''},
        ]
        for overrides in cases:
            self.set_evidence(**overrides)
            run = GuardedRun()
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.invoke(run)
            self.assertFalse(run.deployed())

    def test_acceptance_must_be_current_and_timezone_aware(self):
        for timestamp in ('2000-01-01T00:00:00Z', '2099-01-01T00:00:00Z', '2026-11-14T12:00:00'):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                self.invoke(GuardedRun(), self.acceptance(accepted_at=timestamp))

    def test_missing_server_accepted_rejected(self):
        subprocess.run(['git', '-C', str(self.repo), 'update-ref', '-d', SR.SERVER_ACCEPTED_REF], check=True)
        run = GuardedRun()
        with self.assertRaises(ValueError):
            self.invoke(run)
        self.assertFalse(run.deployed())

    def test_existing_directory_without_success_receipt_rejected(self):
        target = self.root / 'releases' / self.release_id
        target.mkdir()
        (target / 'MANIFEST.sha256').write_text('')
        run = GuardedRun()
        with self.assertRaises(ValueError):
            self.invoke(run)
        self.assertFalse(run.deployed())

    def test_success_and_duplicate_use_real_previous_path_contract(self):
        acceptance = self.acceptance()
        run = self.successful_run()
        self.assertEqual(self.invoke(run, acceptance)['status'], 'published')
        replay = GuardedRun()
        self.assertEqual(self.invoke(replay, acceptance)['status'], 'already_deployed')
        self.assertFalse(replay.deployed())
        record = SR.load_json(SR._attempt_record_path(self.root, self.release_id))
        self.assertEqual(record['status'], 'succeeded')
        self.assertEqual(record['source_sha'], self.sha)
        self.assertEqual(record['installed_manifest_sha256'], SR.digest_file(self.root / 'current' / 'MANIFEST.sha256'))

    def test_tampered_deployed_content_cannot_reconcile(self):
        acceptance = self.acceptance()
        self.invoke(self.successful_run(), acceptance)
        (self.root / 'current' / 'diy-web' / 'dist' / 'index.html').write_text('tampered')
        with self.assertRaises(ValueError):
            self.invoke(GuardedRun(), acceptance)

    def test_timeout_leaves_uncertain_receipt_and_never_redispatches(self):
        def timeout(args, **kwargs):
            if 'deploy-production.sh' in ' '.join(args):
                raise subprocess.TimeoutExpired(args, 1)
            return subprocess.run(args, **kwargs)
        acceptance = self.acceptance()
        with self.assertRaises(subprocess.TimeoutExpired):
            self.invoke(timeout, acceptance)
        self.assertEqual(SR.load_json(SR._attempt_record_path(self.root, self.release_id))['status'], 'uncertain')
        run = GuardedRun()
        with self.assertRaises(ValueError):
            self.invoke(run, acceptance)
        self.assertFalse(run.deployed())

    def test_backup_failure_does_not_fail_successful_deployment(self):
        with mock.patch.object(SR, 'record_github_backup', side_effect=OSError('backup unavailable')):
            result = self.invoke(self.successful_run())
        self.assertEqual(result['status'], 'published')
        self.assertEqual(result['github_backup'], 'failed')
        self.assertEqual(SR.load_json(SR._attempt_record_path(self.root, self.release_id))['status'], 'succeeded')

    def test_shell_handoff_rejects_competing_current_before_any_mutation(self):
        guard = self.workspace / 'deploy' / 'diy' / 'deploy-production.sh'
        shutil.copy2(ROOT / 'deploy' / 'diy' / 'deploy-production.sh', guard)
        marker = self.tmp / 'capacity-was-run'
        (self.workspace / 'deploy' / 'diy' / 'check-capacity.sh').write_text('#!/bin/bash\ntouch ' + str(marker) + '\nexit 99\n')
        self.manifest = SR.write_manifest(self.workspace)
        report = SR.read_build_report(self.workspace)
        report['manifest_sha256'] = self.manifest
        SR.save_json(self.workspace / 'build-report.json', report)
        other = self.root / 'releases' / 'other'
        other.mkdir()
        def race(args, **kwargs):
            if 'deploy-production.sh' in ' '.join(args):
                (self.root / 'current').unlink()
                (self.root / 'current').symlink_to(other, target_is_directory=True)
            return subprocess.run(args, **kwargs)
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self.invoke(race)
        self.assertIn('unexpected current release', error.exception.stderr)
        self.assertFalse(marker.exists(), 'guard must reject under lock before capacity/backup/activation')
        self.assertEqual((self.root / 'current').resolve(), other)

    def test_unsafe_bundle_path_is_a_backup_failure_not_publish_failure(self):
        bundle = self.root / 'release-records' / (self.release_id + '.bundle')
        protected = self.tmp / 'protected'
        protected.write_text('unchanged')
        bundle.symlink_to(protected)
        result = self.invoke(self.successful_run())
        self.assertEqual(result['status'], 'published')
        self.assertEqual(result['github_backup'], 'failed')
        self.assertEqual(protected.read_text(), 'unchanged')


class BackupIsolationTests(unittest.TestCase):
    def test_partial_clone_backup_does_not_fetch_missing_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            origin, sha = make_git_repo(root)
            subprocess.run(['git', '-C', str(origin), 'config', 'uploadpack.allowFilter', 'true'], check=True)
            clone = root / 'partial'
            subprocess.run(['git', 'clone', '-q', '--filter=blob:none', '--no-checkout',
                            origin.as_uri(), str(clone)], check=True)
            def missing():
                result = subprocess.check_output(['git', '-C', str(clone), 'rev-list',
                    '--objects', '--missing=print', 'HEAD'], text=True)
                return [line for line in result.splitlines() if line.startswith('?')]
            before = missing()
            self.assertTrue(before, 'fixture must contain a missing promised blob')
            release_root = make_root(root)
            result = SR.record_github_backup(release_root, 'server-' + sha[:12] + '-123', sha, str(clone))
            self.assertEqual(result['github_backup'], 'failed')
            self.assertEqual(missing(), before, 'backup must not fetch from any remote')
            refs = subprocess.check_output(['git', '-C', str(clone), 'for-each-ref',
                '--format=%(refname)', 'refs/server-release-bundle-tmp-'], text=True)
            self.assertEqual(refs, '')

    def test_backup_timeout_is_recorded_without_escaping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            with mock.patch.object(SR, 'ensure_bundle', side_effect=subprocess.TimeoutExpired('git bundle', 120)):
                record = SR.record_github_backup(root, 'server-' + 'a' * 12 + '-123', 'a' * 40, '/unused')
            self.assertEqual(record['github_backup'], 'failed')
            self.assertIn('TimeoutExpired', record['error'])


class EntryRegressionTests(unittest.TestCase):
    def test_prepare_cli_dispatches_to_builder(self):
        with mock.patch.object(SR, 'prepare', return_value={}) as prepare:
            with redirect_stdout(io.StringIO()):
                result = SR.main(['prepare', '--source', '/tmp/source', '--sha', 'a' * 40,
                                  '--release-root', '/tmp/release-root'])
        self.assertEqual(result, 0)
        prepare.assert_called_once()

    def test_default_inspect_does_not_create_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            (root / 'release-records').rmdir()
            env = dict(os.environ, HXY_DIY_RELEASE_ROOT=str(root))
            result = subprocess.run(['python3', str(ROOT / 'deploy/diy/server_release.py')], env=env,
                                    text=True, capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout)['current'], PREV_RELEASE)
            self.assertFalse((root / 'release-records').exists())

    def test_resource_preflight_rejects_unsafe_build_headroom(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                SR.preflight_resources(Path(tmp), free_disk_kb=10**8, available_memory_mb=700)

    def test_git_archive_excludes_ignored_files_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, sha = make_git_repo(Path(tmp))
            (repo / '.gitignore').write_text('private.dump\n')
            subprocess.run(['git', '-C', str(repo), 'add', '.gitignore'], check=True)
            subprocess.run(['git', '-C', str(repo), 'commit', '-q', '-m', 'ignore private input'], check=True)
            sha = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
            (repo / 'private.dump').write_text('private fixture')
            build_dir = Path(tmp) / 'build'; build_dir.mkdir()
            exported = SR.materialize_archive(repo, sha, build_dir)
            self.assertFalse((exported / 'private.dump').exists())
            (exported / 'file.txt').write_text('isolated build changes')
            self.assertEqual((repo / 'file.txt').read_text(), 'base')
            SR.verify_source_clean(repo, sha)

    def test_archive_rejects_tracked_symlink_before_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, sha = make_git_repo(Path(tmp))
            (repo / 'escape').symlink_to('/etc/passwd')
            subprocess.run(['git', '-C', str(repo), 'add', 'escape'], check=True)
            subprocess.run(['git', '-C', str(repo), 'commit', '-q', '-m', 'symlink fixture'], check=True)
            sha = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
            build_dir = Path(tmp) / 'build'; build_dir.mkdir()
            with self.assertRaises(ValueError):
                SR.materialize_archive(repo, sha, build_dir)
            self.assertFalse((build_dir / 'src').exists())

    def test_prepare_rejects_invalid_id_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            repo, sha = make_git_repo_with_source(Path(tmp))
            with mock.patch.object(SR, 'build_source') as build:
                with self.assertRaises(ValueError):
                    SR.prepare(root, repo, sha, '../../escape')
            build.assert_not_called()


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

    def test_read_build_settings_refuses_to_guess_when_marker_absent(self):
        (self.root / 'releases' / PREV_RELEASE / 'admin-react' / 'dist' /
         'staff-learning-build.json').unlink()
        with self.assertRaises(ValueError):
            SR.read_build_settings(self.root)

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
