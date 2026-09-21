from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class SchemathesisContractTests(unittest.TestCase):
    def test_pilot_is_pinned_and_limited_to_isolated_catalog_reads(self):
        requirements = (REPO_ROOT / "hxy-server" / "requirements-dev.txt").read_text(encoding="utf-8")
        test_source = (
            REPO_ROOT / "hxy-server" / "tests" / "test_admin_catalog_schemathesis.py"
        ).read_text(encoding="utf-8")

        self.assertIn("schemathesis==4.27.5", requirements)
        self.assertIn('method="GET"', test_source)
        self.assertIn('"/api/v1/admin/v2/projects"', test_source)
        self.assertIn('"/api/v1/admin/v2/products"', test_source)
        self.assertIn("sqlite://", test_source)
        self.assertNotIn('method="POST"', test_source)
        self.assertNotIn("http://", test_source)
        self.assertNotIn("https://", test_source)


if __name__ == "__main__":
    unittest.main()
