"""Behavioral checks for the token-free release waiter (no network required)."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseWatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'tools/release/watch_release.py'
        if path.exists():
            spec = importlib.util.spec_from_file_location('watch_release', path)
            cls.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.mod)
        else:
            cls.mod = None

    def setUp(self):
        self.assertIsNotNone(self.mod, 'Shared release waiter must exist')

    def checks(self):
        return [dict(id=i, name=n, status='completed', conclusion='success',
                     app={'slug': 'github-actions'}, head_sha='a'*40)
                for i, n in enumerate(self.mod.REQUIRED + ['AI PR Review'])]

    def test_optional_ai_skip_does_not_block_but_failed_or_missing_gate_does(self):
        checks = self.checks()
        checks[-1]['conclusion'] = 'skipped'
        self.assertEqual(self.mod.gate(checks, 'a'*40), 'ready')
        checks[0]['conclusion'] = 'skipped'
        self.assertEqual(self.mod.gate(checks, 'a'*40), 'checks_failed')
        self.assertEqual(self.mod.gate([], 'a'*40), 'waiting_for_checks')

    def test_latest_check_wins_and_wrong_app_or_sha_is_not_trusted(self):
        checks = self.checks()
        checks += [dict(checks[0], id=100, status='in_progress', conclusion=None)]
        self.assertEqual(self.mod.gate(checks, 'a'*40), 'waiting_for_checks')
        checks = self.checks()
        checks[0]['head_sha'] = 'b'*40
        self.assertEqual(self.mod.gate(checks, 'a'*40), 'waiting_for_checks')
        checks = self.checks()
        checks[0]['app'] = {'slug': 'other'}
        self.assertEqual(self.mod.gate(checks, 'a'*40), 'waiting_for_checks')

    def test_failed_optional_ai_is_not_ignored(self):
        checks = self.checks()
        checks[-1]['conclusion'] = 'failure'
        self.assertEqual(self.mod.gate(checks, 'a'*40), 'checks_failed')

    def test_ci_failure_cannot_be_hidden_by_deploy_success(self):
        ci = dict(status='completed', conclusion='failure')
        deploy = dict(status='completed', conclusion='success')
        self.assertEqual(self.mod.release_state(ci, deploy, 'success'), 'ci_failed')

    def test_release_requires_completed_job_not_only_workflow(self):
        ci = dict(status='completed', conclusion='success')
        deploy = dict(status='completed', conclusion='success')
        for job, expected in [(None, 'deployment_unverified'), ('skipped', 'deployment_skipped'),
                              ('success', 'deployment_succeeded'), ('failure', 'deployment_failed')]:
            self.assertEqual(self.mod.release_state(ci, deploy, job), expected)
        self.assertEqual(self.mod.release_state(None, None, None), 'waiting_for_ci')

    def test_report_atomic_write_and_lock_rejects_duplicate_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'report.json'
            self.mod.save(target, {'status': 'timeout'})
            self.assertEqual(json.loads(target.read_text())['status'], 'timeout')
            with self.mod.lock(Path(folder) / 'worker.lock'):
                with self.assertRaises(self.mod.AlreadyRunning):
                    with self.mod.lock(Path(folder) / 'worker.lock'):
                        pass

    def test_pr_policy_rejects_changed_head_fork_draft_and_closed(self):
        pr = dict(state='open', draft=False, merged=False,
                  head={'sha': 'a'*40, 'repo': {'full_name': 'zzzai/hxydiy'}},
                  base={'ref': 'main'})
        self.assertIsNone(self.mod.pr_problem(pr, 'a'*40))
        self.assertEqual(self.mod.pr_problem(pr, 'b'*40), 'head_changed')
        for changed in [dict(pr, draft=True), dict(pr, state='closed'),
                        dict(pr, head={'sha': 'a'*40, 'repo': {'full_name': 'evil/fork'}})]:
            self.assertEqual(self.mod.pr_problem(changed, 'a'*40), 'pr_ineligible')

    def test_readonly_waiter_never_merges_and_authorized_waiter_pins_sha(self):
        checks = self.checks()
        calls = []

        class API:
            def get(inner, path, body=None):
                calls.append((path, body))
                if path == '/pulls/123' and body is None:
                    return dict(state='open', draft=False, merged=False, mergeable_state='clean',
                                head={'sha': 'a'*40, 'repo': {'full_name': 'zzzai/hxydiy'}},
                                base={'ref': 'main'})
                if path == '/pulls/123/merge':
                    return {'merged': True, 'sha': 'b'*40}
                if path == '/git/ref/heads/main':
                    return {'object': {'sha': 'b'*40}}
                raise AssertionError(path)

            def pages(inner, path, key):
                if path == '/commits/' + 'a'*40 + '/check-runs?filter=latest':
                    return checks
                if path == '/actions/runs?head_sha=' + 'b'*40:
                    return []
                raise AssertionError(path)

        args = SimpleNamespace(pr=123, head='a'*40, merge=False)
        report = {'commit': None}
        self.assertEqual(self.mod.step(API(), args, report), 'waiting_for_merge')
        self.assertFalse(any(body is not None for _, body in calls))
        args.merge = True
        self.assertEqual(self.mod.step(API(), args, report), 'waiting_for_ci')
        self.assertEqual(report['commit'], 'b'*40)
        self.assertIn(('/pulls/123/merge', {'sha': 'a'*40, 'merge_method': 'squash'}), calls)

    def test_new_main_stops_old_commit_before_deployment_queries(self):
        class API:
            def get(inner, path):
                self.assertEqual(path, '/git/ref/heads/main')
                return {'object': {'sha': 'b'*40}}
        self.assertEqual(self.mod.step(API(), SimpleNamespace(pr=None), {'commit': 'a'*40}), 'superseded')


if __name__ == '__main__':
    unittest.main()
