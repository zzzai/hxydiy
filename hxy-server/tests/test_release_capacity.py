import os
from pathlib import Path
import shlex
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/diy/check-capacity.sh"
BASH = shutil.which("bash")
if os.name == "nt" and Path("C:/Program Files/Git/bin/bash.exe").exists():
    BASH = "C:/Program Files/Git/bin/bash.exe"


@unittest.skipUnless(BASH, "Bash is required for deployment script behavior tests")
class ReleaseCapacityTests(unittest.TestCase):
    def run_gate(self, available, minimum="3145728", failed=False):
        response = "return 1" if failed else (
            "printf '%s\\n' 'Filesystem 1024-blocks Used Available Capacity Mounted' "
            + shlex.quote(f"audit 10000000 5000000 {available} 50% /")
        )
        command = (
            f"df() {{ {response}; }}; export -f df; "
            f"bash {shlex.quote(SCRIPT.as_posix())} {shlex.quote(ROOT.as_posix())} "
            f"{shlex.quote(minimum)}"
        )
        return subprocess.run([BASH, "-c", command], capture_output=True, text=True, timeout=15)

    def test_rejects_insufficient_space(self):
        result = self.run_gate("3145727")
        self.assertEqual(result.returncode, 1)
        self.assertIn("CAPACITY_INSUFFICIENT", result.stderr)

    def test_accepts_space_at_reserve(self):
        result = self.run_gate("3145728")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CAPACITY_OK", result.stdout)

    def test_rejects_unknown_capacity(self):
        result = self.run_gate("invalid")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CAPACITY_UNKNOWN", result.stderr)

    def test_rejects_unreadable_filesystem(self):
        result = self.run_gate("0", failed=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CAPACITY_UNKNOWN", result.stderr)

    def test_rejects_invalid_or_zero_reserve(self):
        for minimum in ("0", "-1", "abc"):
            with self.subTest(minimum=minimum):
                result = self.run_gate("9000000", minimum)
                self.assertEqual(result.returncode, 2)
                self.assertIn("CAPACITY_INVALID", result.stderr)
