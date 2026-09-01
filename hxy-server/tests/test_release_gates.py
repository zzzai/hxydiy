import unittest

from scripts.release_gates import evaluate_release_gates


class ReleaseGateTests(unittest.TestCase):
    def test_all_required_evidence_allows_release(self):
        report = evaluate_release_gates({
            "tests": True,
            "backup": True,
            "manifest": True,
            "current": True,
            "health": True,
        })
        self.assertTrue(report.ok)
        self.assertEqual(report.missing, ())

    def test_any_missing_evidence_blocks_release(self):
        report = evaluate_release_gates({
            "tests": True,
            "backup": False,
            "manifest": True,
            "current": True,
            "health": False,
        })
        self.assertFalse(report.ok)
        self.assertEqual(report.missing, ("backup", "health"))

    def test_unknown_evidence_is_not_a_substitute_for_required_gate(self):
        report = evaluate_release_gates({"tests": True, "notes": True})
        self.assertFalse(report.ok)
        self.assertEqual(report.missing, ("backup", "manifest", "current", "health"))


if __name__ == "__main__":
    unittest.main()
