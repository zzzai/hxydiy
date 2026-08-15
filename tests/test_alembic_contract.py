import unittest
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from app import models  # noqa: F401
from app.db.session import Base


class AlembicContractTests(unittest.TestCase):
    def test_revision_ids_fit_the_postgresql_version_table(self):
        scripts = ScriptDirectory.from_config(Config("alembic.ini"))
        oversized = {
            revision.revision: len(revision.revision)
            for revision in scripts.walk_revisions()
            if len(revision.revision) > 32
        }

        self.assertEqual(oversized, {})

    def test_upgrade_verifier_runs_outside_the_repository_directory(self):
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "verified.db"
            engine = create_engine(f"sqlite:///{database_path}")
            Base.metadata.create_all(engine)
            engine.dispose()
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            env["DATABASE_URL"] = f"sqlite:///{database_path}"

            result = subprocess.run(
                [sys.executable, str(project_root / "scripts/verify_selection_closure_upgrade.py")],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("selection closure schema verified", result.stdout)


if __name__ == "__main__":
    unittest.main()
