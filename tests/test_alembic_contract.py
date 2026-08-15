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
                    for constraint in list(copied.foreign_key_constraints):
                        if constraint.name != "fk_projects_current_published_version_id":
                            continue
                        for foreign_key in constraint.elements:
                            foreign_key.parent.foreign_keys.discard(foreign_key)
                            copied.foreign_keys.discard(foreign_key)
                        copied.foreign_key_constraints.discard(constraint)
                        copied.constraints.discard(constraint)
                    copied._columns.remove(current_catalog_column)
                if copied.name == "users":
                    annual_cycle_column = copied.c.annual_membership_cycle_id
                    for index in list(copied.indexes):
                        if annual_cycle_column.name in index.columns:
                            copied.indexes.discard(index)
                    copied._columns.remove(annual_cycle_column)

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
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            self.assertIn("annual_membership_cycle_id", user_columns)
            user_indexes = {index["name"] for index in inspector.get_indexes("users")}
            self.assertIn("ix_users_annual_membership_cycle_id", user_indexes)
            membership_grant_columns = {
                column["name"]
                for column in inspector.get_columns("membership_benefit_grants")
            }
            self.assertIn("membership_cycle_id", membership_grant_columns)
            option_choice_columns = {
                column["name"]
                for column in inspector.get_columns("project_option_choices")
            }
            self.assertIn("pinned_linked_catalog_version_id", option_choice_columns)
            project_foreign_keys = inspector.get_foreign_keys("projects")
            self.assertTrue(any(
                foreign_key["constrained_columns"] == ["id", "current_published_version_id"]
                and foreign_key["referred_table"] == "project_catalog_versions"
                and foreign_key["referred_columns"] == ["project_id", "id"]
                for foreign_key in project_foreign_keys
            ))
            option_choice_foreign_keys = inspector.get_foreign_keys("project_option_choices")
            self.assertTrue(any(
                foreign_key["constrained_columns"] == ["pinned_linked_catalog_version_id"]
                and foreign_key["referred_table"] == "project_catalog_versions"
                for foreign_key in option_choice_foreign_keys
            ))
            expected_unique_columns = {
                "project_catalog_versions": {
                    ("project_id", "version"),
                    ("project_id", "id"),
                },
                "project_option_groups": {("catalog_version_id", "code")},
                "project_option_choices": {("option_group_id", "code")},
                "option_choice_prices": {
                    ("option_choice_id", "price_type", "effective_from"),
                },
                "membership_benefit_grants": {
                    ("user_id", "membership_cycle_id"),
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
            option_price_checks = {
                constraint["name"]: constraint["sqltext"]
                for constraint in inspector.get_check_constraints("option_choice_prices")
            }
            self.assertEqual(
                option_price_checks.get("ck_option_choice_price_non_negative", ""),
                "amount_cents >= 0",
            )
            self.assertEqual(
                option_price_checks.get("ck_option_choice_price_valid_interval", ""),
                "effective_to IS NULL OR effective_to > effective_from",
            )
            price_book_checks = {
                constraint["name"]: constraint["sqltext"]
                for constraint in inspector.get_check_constraints("price_book")
            }
            self.assertEqual(
                price_book_checks.get("ck_price_book_amount_non_negative", ""),
                "amount_cents >= 0",
            )
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
