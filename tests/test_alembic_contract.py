import unittest
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, create_engine, inspect

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

    def test_catalog_option_migration_upgrades_the_previous_schema(self):
        project_root = Path(__file__).resolve().parents[1]
        new_tables = {
            "project_catalog_versions",
            "project_option_groups",
            "project_option_choices",
            "option_choice_prices",
            "membership_benefit_grants",
        }
        previous_metadata = MetaData()
        for table in Base.metadata.tables.values():
            if table.name not in new_tables:
                copied = table.to_metadata(previous_metadata)
                if copied.name == "projects":
                    current_catalog_column = copied.c.current_published_version_id
                    for foreign_key in list(current_catalog_column.foreign_keys):
                        current_catalog_column.foreign_keys.discard(foreign_key)
                        copied.foreign_keys.discard(foreign_key)
                        copied.foreign_key_constraints.discard(foreign_key.constraint)
                        copied.constraints.discard(foreign_key.constraint)
                    copied._columns.remove(current_catalog_column)

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "catalog-options.db"
            database_url = f"sqlite:///{database_path}"
            engine = create_engine(database_url)
            previous_metadata.create_all(engine)
            engine.dispose()
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            env["DATABASE_URL"] = database_url

            stamp = subprocess.run(
                [sys.executable, "-m", "alembic", "stamp", "20260814_settlement_p0"],
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(stamp.returncode, 0, stamp.stderr)
            upgrade = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(upgrade.returncode, 0, upgrade.stderr)

            engine = create_engine(database_url)
            inspector = inspect(engine)
            self.assertTrue(new_tables.issubset(set(inspector.get_table_names())))
            project_columns = {column["name"] for column in inspector.get_columns("projects")}
            self.assertIn("current_published_version_id", project_columns)
            project_foreign_keys = inspector.get_foreign_keys("projects")
            self.assertTrue(any(
                foreign_key["constrained_columns"] == ["current_published_version_id"]
                and foreign_key["referred_table"] == "project_catalog_versions"
                for foreign_key in project_foreign_keys
            ))
            expected_unique_columns = {
                "project_catalog_versions": {("project_id", "version")},
                "project_option_groups": {("catalog_version_id", "code")},
                "project_option_choices": {("option_group_id", "code")},
                "option_choice_prices": {
                    ("option_choice_id", "price_type", "effective_from"),
                },
                "membership_benefit_grants": {
                    ("user_id", "benefit_type", "membership_started_at"),
                    ("used_service_line_id",),
                },
            }
            for table_name, expected_columns in expected_unique_columns.items():
                actual_columns = {
                    tuple(constraint["column_names"])
                    for constraint in inspector.get_unique_constraints(table_name)
                }
                self.assertTrue(expected_columns.issubset(actual_columns), table_name)
            catalog_version_checks = {
                constraint["name"]: constraint["sqltext"]
                for constraint in inspector.get_check_constraints("project_catalog_versions")
            }
            status_check = catalog_version_checks.get("ck_project_catalog_version_status", "")
            self.assertEqual(
                status_check,
                "status IN ('draft', 'published', 'superseded')",
            )
            membership_checks = {
                constraint["name"]: constraint["sqltext"]
                for constraint in inspector.get_check_constraints("membership_benefit_grants")
            }
            membership_status_check = membership_checks.get("ck_membership_benefit_status", "")
            self.assertEqual(
                membership_status_check,
                "status IN ('available', 'used', 'voided')",
            )
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
