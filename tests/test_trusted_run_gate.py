"""Exercise trusted workflow provenance and failure handling without GitHub access."""
from pathlib import Path
import subprocess
import unittest


class TrustedRunGateBehaviorTests(unittest.TestCase):
    def test_trusted_run_selection_and_fail_closed_behavior(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", "--test", ".github/scripts/trusted-run-gate.test.cjs"],
            cwd=root, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
