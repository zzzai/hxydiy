import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.check_release_consistency import check_release_consistency


class ReleaseConsistencyTests(unittest.TestCase):
    def test_reports_catalog_migration_capability_missing_from_release(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            production = root / "production" / "current"
            files = {
                workspace / "hxy-server/app/api/selections.py": "/revisions",
                workspace / "hxy-server/app/api/admin_v2.py": "selection-change-requests",
                workspace / "diy-web/src/api.ts": "/revisions",
                workspace / "admin-react/src/api.ts": "selection-change-requests",
                production / "hxy-server/app/api/selections.py": "/revisions",
                production / "hxy-server/app/api/admin_v2.py": "selection-change-requests",
                production / "diy-web/dist/index.js": "/revisions",
                production / "admin-react/dist/index.js": "selection-change-requests",
            }
            for path, content in files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            report = check_release_consistency(workspace, root / "production")

            self.assertFalse(report.ok)
            self.assertIn("workspace_backend", report.missing)
            self.assertIn("production_api", report.missing)

    def test_reports_p0_capabilities_missing_from_production(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            production = root / "production"
            for relative in (
                "hxy-server/app/api/selections.py",
                "hxy-server/app/api/admin_v2.py",
                "diy-web/src/api.ts",
                "admin-react/src/api.ts",
            ):
                path = workspace / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("P0_MARKER", encoding="utf-8")

            production = production / "current"
            production_api = production / "hxy-server"
            production_web = production / "diy-web" / "dist"
            production_api.mkdir(parents=True)
            production_web.mkdir(parents=True)
            (production_api / "app" / "api").mkdir(parents=True)
            (production_api / "app" / "api" / "selections.py").write_text("", encoding="utf-8")
            (production_api / "app" / "api" / "admin_v2.py").write_text("", encoding="utf-8")
            (production_web / "index.js").write_text("", encoding="utf-8")

            report = check_release_consistency(workspace, production)

            self.assertFalse(report.ok)
            self.assertIn("production_api", report.missing)
            self.assertIn("production_customer_web", report.missing)
            self.assertIn("production_admin_web", report.missing)

    def test_accepts_matching_backend_and_frontend_markers(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            production = root / "production"
            files = {
                "hxy-server/app/api/selections.py": 'route /revisions',
                "hxy-server/app/api/admin_v2.py": 'route /selection-change-requests',
                "hxy-server/scripts/migrate_catalog_options.py": 'def migrate_store_catalog --apply',
                "diy-web/src/api.ts": '/selection-sessions/x/revisions',
                "admin-react/src/api.ts": '/admin/v2/selection-change-requests',
            }
            for relative, content in files.items():
                path = workspace / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            production = production / "current"
            for relative in (
                "app/api/selections.py",
                "app/api/admin_v2.py",
            ):
                path = production / "hxy-server" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("/revisions /selection-change-requests", encoding="utf-8")
            migration = production / "hxy-server" / "scripts" / "migrate_catalog_options.py"
            migration.parent.mkdir(parents=True, exist_ok=True)
            migration.write_text("def migrate_store_catalog --apply", encoding="utf-8")
            web = production / "diy-web" / "dist" / "index.js"
            web.parent.mkdir(parents=True, exist_ok=True)
            web.write_text("/revisions", encoding="utf-8")
            admin = production / "admin-react" / "dist" / "index.js"
            admin.parent.mkdir(parents=True, exist_ok=True)
            admin.write_text("selection-change-requests", encoding="utf-8")

            report = check_release_consistency(workspace, production)

            self.assertTrue(report.ok, report.missing)


if __name__ == "__main__":
    unittest.main()
