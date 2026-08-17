import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[2]
CREATE = REPO_ROOT / "deploy/diy/create-release.sh"
ACTIVATE = REPO_ROOT / "deploy/diy/activate-release.sh"


class ReleaseScriptTests(unittest.TestCase):
    def test_container_entrypoint_uses_unix_line_endings(self):
        entrypoint = (REPO_ROOT / "hxy-server/entrypoint.sh").read_bytes()

        self.assertTrue(entrypoint.startswith(b"#!/bin/sh\n"))
        self.assertNotIn(b"\r\n", entrypoint)

    def test_existing_database_migrations_require_explicit_opt_in(self):
        entrypoint = (REPO_ROOT / "hxy-server/entrypoint.sh").read_text(encoding="utf-8")
        compose = (REPO_ROOT / "deploy/diy/docker-compose.hxy.yml").read_text(encoding="utf-8")

        self.assertIn('if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then', entrypoint)
        self.assertIn('RUN_MIGRATIONS: "false"', compose)

    def test_creates_complete_release_and_switches_current(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            release_root = root / "production"
            shutil.copytree(REPO_ROOT / "hxy-server", workspace / "hxy-server", ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
            shutil.copytree(REPO_ROOT / "deploy", workspace / "deploy")
            (workspace / "diy-web/dist").mkdir(parents=True)
            (workspace / "admin-react/dist").mkdir(parents=True)
            (workspace / "diy-web/dist/index.html").write_text("customer", encoding="utf-8")
            (workspace / "admin-react/dist/index.html").write_text("staff", encoding="utf-8")
            environment = {**os.environ, "HXY_DIY_RELEASE_ROOT": str(release_root)}

            created = subprocess.run(
                [str(CREATE), "p0-test"], cwd=workspace / "deploy/diy", env=environment,
                capture_output=True, text=True, check=True,
            )
            activated = subprocess.run(
                [str(ACTIVATE), "p0-test"], cwd=workspace / "deploy/diy", env=environment,
                capture_output=True, text=True, check=True,
            )

            release = release_root / "releases/p0-test"
            self.assertEqual(Path(created.stdout.strip()), release)
            self.assertEqual(Path(activated.stdout.strip()), release)
            self.assertEqual((release_root / "current").resolve(), release)
            self.assertTrue((release / "MANIFEST.sha256").is_file())

    def test_refuses_to_activate_an_incomplete_release(self):
        with TemporaryDirectory() as directory:
            release_root = Path(directory)
            (release_root / "releases/broken").mkdir(parents=True)
            environment = {**os.environ, "HXY_DIY_RELEASE_ROOT": str(release_root)}

            result = subprocess.run(
                [str(ACTIVATE), "broken"], env=environment, capture_output=True, text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((release_root / "current").exists())


if __name__ == "__main__":
    unittest.main()
