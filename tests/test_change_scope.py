"""Exercise the same fail-closed change classification used by CI."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ChangeScopeTests(unittest.TestCase):
    def classify(self, paths):
        result = subprocess.check_output([
            'node', '-e', "const {docsOnly}=require('./.github/scripts/change-scope.cjs'); process.stdout.write(JSON.stringify(docsOnly(JSON.parse(process.argv[1]))))", json.dumps(paths)
        ], cwd=ROOT, text=True)
        return json.loads(result)

    def test_documentation_does_not_need_application_builds(self):
        self.assertTrue(self.classify(['docs/CURRENT-STATE.md', 'README.md', 'tests/test_project_memory_contract.py']))

    def test_runtime_and_security_changes_never_skip_builds(self):
        for path in ['diy-web/src/App.tsx', 'hxy-server/app/main.py', 'admin-react/src/App.tsx',
                     '.github/workflows/ci.yml', '.github/scripts/change-scope.cjs', 'deploy/diy/deploy-production.sh',
                     'docs/example.py', 'unknown.txt', 'package.json']:
            with self.subTest(path=path):
                self.assertFalse(self.classify(['docs/CURRENT-STATE.md', path]))

    def test_empty_invalid_and_renamed_runtime_inputs_fail_closed(self):
        for paths in [[], ['../docs/foo.md'], ['docs/../diy-web/foo.md'], [''],
                      ['docs/example.md', 'diy-web/src/renamed.ts']]:
            self.assertFalse(self.classify(paths))
