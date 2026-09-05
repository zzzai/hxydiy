import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHA = '1' * 40


class ReleasePolicyTests(unittest.TestCase):
    def evaluate(self, name, args):
        return json.loads(subprocess.check_output(['node', '-e',
            "const p=require('./.github/scripts/release-policy.cjs'); process.stdout.write(JSON.stringify(p[process.argv[1]](...JSON.parse(process.argv[2]))))",
            name, json.dumps(args)], cwd=ROOT, text=True))

    def test_only_successful_exact_current_main_ci_can_release(self):
        run = dict(head_sha=SHA, head_branch='main', event='push', path='.github/workflows/ci.yml',
                   status='completed', conclusion='success', head_repository={'full_name':'zzzai/hxydiy'})
        self.assertTrue(self.evaluate('eligibleRun', [run, SHA, SHA, 'zzzai/hxydiy']))
        for key, value in [('head_sha','2'*40), ('event','pull_request'), ('path','other.yml'),
                           ('status','in_progress'), ('conclusion','failure'), ('head_repository',{'full_name':'other/repo'})]:
            self.assertFalse(self.evaluate('eligibleRun', [dict(run, **{key:value}), SHA, SHA, 'zzzai/hxydiy']))
        self.assertFalse(self.evaluate('eligibleRun', [run, SHA, '2'*40, 'zzzai/hxydiy']))

    def test_missing_expired_or_wrong_sha_artifacts_cannot_release(self):
        artifacts = [dict(name=f'{name}-dist-{SHA}', expired=False) for name in ['admin','customer']]
        self.assertTrue(self.evaluate('hasBuilds', [artifacts, SHA]))
        for items in [[], artifacts[:1], [dict(item, expired=True) for item in artifacts]]:
            self.assertFalse(self.evaluate('hasBuilds', [items, SHA]))
        self.assertFalse(self.evaluate('hasBuilds', [artifacts, '2'*40]))
