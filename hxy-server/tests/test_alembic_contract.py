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
    def test_service_reference_revision_adds_version_confirmation_and_indexes(self):
        project_root = Path(__file__).resolve().parents[1]
        migration_path = project_root / "alembic" / "versions" / "20260904_service_reference_v2.py"

        self.assertTrue(migration_path.exists())
        migration = migration_path.read_text(encoding="utf-8")
        self.assertIn('down_revision = "20260830_media_assets"', migration)
        for column in ("schema_version", "taxonomy_version", "customer_confirmed", "confirmed_at"):
            self.assertIn(f'"{column}"', migration)
        self.assertIn("ix_customer_profile_store_user_confirmed_created", migration)
        self.assertIn("ix_customer_profile_store_technician_created", migration)

    def test_membership_store_backfill_uses_cross_database_boolean_predicate(self):
        project_root = Path(__file__).resolve().parents[1]
        migration = (
            project_root
            / "alembic"
            / "versions"
            / "20260825_membership_store_scope.py"
        ).read_text(encoding="utf-8")

        self.assertEqual(migration.count("users.is_member IS TRUE"), 2)
        self.assertNotIn("users.is_member = 1", migration)

    def test_revision_ids_fit_the_postgresql_version_table(self):
        project_root = Path(__file__).resolve().parents[1]
        config = Config(str(project_root / "alembic.ini"))
        config.set_main_option("script_location", str(project_root / "alembic"))
        scripts = ScriptDirectory.from_config(config)
        oversized = {
            revision.revision: len(revision.revision)
            for revision in scripts.walk_revisions()
            if len(revision.revision) > 32
        }

        self.assertEqual(oversized, {})

    def test_migration_graph_has_one_intentional_head(self):
        project_root = Path(__file__).resolve().parents[1]
        config = Config(str(project_root / "alembic.ini"))
        config.set_main_option("script_location", str(project_root / "alembic"))
        scripts = ScriptDirectory.from_config(config)

        self.assertEqual(len(scripts.get_heads()), 1, scripts.get_heads())

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

    def test_production_sms_revision_upgrades_to_current_head(self):
        project_root = Path(__file__).resolve().parents[1]
        previous_metadata = MetaData()
        excluded_tables = {"service_position_qrs", "customer_profile_records", "media_assets", "customer_trusted_devices", "membership_codes"}
        for table in Base.metadata.tables.values():
            if table.name in excluded_tables:
                continue
            copied = table.to_metadata(previous_metadata)
            if copied.name == "users":
                copied._columns.remove(copied.c.customer_login_version)
                membership_store_column = copied.c.membership_store_id
                for index in list(copied.indexes):
                    if membership_store_column.name in index.columns:
                        copied.indexes.discard(index)
                for constraint in list(copied.foreign_key_constraints):
                    if any(
                        foreign_key.parent is membership_store_column
                        for foreign_key in constraint.elements
                    ):
                        for foreign_key in constraint.elements:
                            foreign_key.parent.foreign_keys.discard(foreign_key)
                            copied.foreign_keys.discard(foreign_key)
                        copied.foreign_key_constraints.discard(constraint)
                        copied.constraints.discard(constraint)
                copied._columns.remove(membership_store_column)
            if copied.name == "selection_sessions":
                for column_name in ("membership_verified_at", "membership_verified_by_staff_id"):
                    column = copied.c[column_name]
                    for constraint in list(copied.foreign_key_constraints):
                        if any(foreign_key.parent is column for foreign_key in constraint.elements):
                            for foreign_key in constraint.elements:
                                foreign_key.parent.foreign_keys.discard(foreign_key)
                                copied.foreign_keys.discard(foreign_key)
                            copied.foreign_key_constraints.discard(constraint); copied.constraints.discard(constraint)
                    copied._columns.remove(column)
            if copied.name == "rooms":
                for column_name in (
                    "parent_room_id",
                    "is_space_container",
                    "is_service_position",
                ):
                    column = copied.c[column_name]
                    for index in list(copied.indexes):
                        if column.name in index.columns:
                            copied.indexes.discard(index)
                    for constraint in list(copied.foreign_key_constraints):
                        if any(
                            foreign_key.parent is column
                            for foreign_key in constraint.elements
                        ):
                            for foreign_key in constraint.elements:
                                foreign_key.parent.foreign_keys.discard(foreign_key)
                                copied.foreign_keys.discard(foreign_key)
                            copied.foreign_key_constraints.discard(constraint)
                            copied.constraints.discard(constraint)
                    copied._columns.remove(column)
            if copied.name == "service_feedback":
                for column_name in (
                    "follow_up_status",
                    "follow_up_staff_id",
                    "follow_up_note",
                    "followed_up_at",
                ):
                    column = copied.c[column_name]
                    for index in list(copied.indexes):
                        if column.name in index.columns:
                            copied.indexes.discard(index)
                    for constraint in list(copied.foreign_key_constraints):
                        if any(
                            foreign_key.parent is column
                            for foreign_key in constraint.elements
                        ):
                            for foreign_key in constraint.elements:
                                foreign_key.parent.foreign_keys.discard(foreign_key)
                                copied.foreign_keys.discard(foreign_key)
                            copied.foreign_key_constraints.discard(constraint)
                            copied.constraints.discard(constraint)
                    copied._columns.remove(column)

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "production-sms-revision.db"
            database_url = f"sqlite:///{database_path}"
            engine = create_engine(database_url)
            previous_metadata.create_all(engine)
            engine.dispose()
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            env["DATABASE_URL"] = database_url

            stamp = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "alembic",
                    "stamp",
                    "20260819_sms_send_receipts",
                ],
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
            self.assertTrue(
                {
                    "parent_room_id",
                    "is_space_container",
                    "is_service_position",
                }.issubset(
                    {
                        column["name"]
                        for column in inspector.get_columns("rooms")
                    }
                )
            )
            self.assertIn(
                "service_position_qrs",
                inspector.get_table_names(),
            )
            self.assertTrue(
                {
                    "follow_up_status",
                    "follow_up_staff_id",
                    "follow_up_note",
                    "followed_up_at",
                }.issubset(
                    {
                        column["name"]
                        for column in inspector.get_columns("service_feedback")
                    }
                )
            )
            engine.dispose()

    def test_catalog_option_migration_upgrades_the_previous_schema(self):
        project_root = Path(__file__).resolve().parents[1]
        new_tables = {
            "project_catalog_versions",
            "project_option_groups",
            "project_option_choices",
            "option_choice_prices",
            "membership_benefit_grants",
            "service_position_qrs",
            "customer_profile_records",
            "media_assets",
            "customer_trusted_devices",
            "membership_codes",
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
                    for column_name in (
                        "annual_membership_cycle_id",
                        "membership_store_id",
                        "customer_login_version",
                    ):
                        column = copied.c[column_name]
                        for index in list(copied.indexes):
                            if column.name in index.columns:
                                copied.indexes.discard(index)
                        for constraint in list(copied.foreign_key_constraints):
                            if any(
                                foreign_key.parent is column
                                for foreign_key in constraint.elements
                            ):
                                for foreign_key in constraint.elements:
                                    foreign_key.parent.foreign_keys.discard(foreign_key)
                                    copied.foreign_keys.discard(foreign_key)
                                copied.foreign_key_constraints.discard(constraint)
                                copied.constraints.discard(constraint)
                        copied._columns.remove(column)
                if copied.name == "position_occupancies":
                    retained_until_column = copied.c.retained_until
                    for index in list(copied.indexes):
                        if retained_until_column.name in index.columns:
                            copied.indexes.discard(index)
                    copied._columns.remove(retained_until_column)
                if copied.name == "selection_sessions":
                    for column_name in ("membership_verified_at", "membership_verified_by_staff_id"):
                        column = copied.c[column_name]
                        for constraint in list(copied.foreign_key_constraints):
                            if any(foreign_key.parent is column for foreign_key in constraint.elements):
                                for foreign_key in constraint.elements:
                                    foreign_key.parent.foreign_keys.discard(foreign_key)
                                    copied.foreign_keys.discard(foreign_key)
                                copied.foreign_key_constraints.discard(constraint); copied.constraints.discard(constraint)
                        copied._columns.remove(column)
                if copied.name == "rooms":
                    for column_name in ("parent_room_id", "is_space_container", "is_service_position"):
                        hierarchy_column = copied.c[column_name]
                        for index in list(copied.indexes):
                            if hierarchy_column.name in index.columns:
                                copied.indexes.discard(index)
                        for constraint in list(copied.foreign_key_constraints):
                            if any(foreign_key.parent is hierarchy_column for foreign_key in constraint.elements):
                                for foreign_key in constraint.elements:
                                    foreign_key.parent.foreign_keys.discard(foreign_key)
                                    copied.foreign_keys.discard(foreign_key)
                                copied.foreign_key_constraints.discard(constraint)
                                copied.constraints.discard(constraint)
                        copied._columns.remove(hierarchy_column)
                if copied.name == "customer_verification_codes":
                    for column_name in ("sms_biz_id", "sms_request_id"):
                        if column_name not in copied.c:
                            continue
                        sms_receipt_column = copied.c[column_name]
                        for index in list(copied.indexes):
                            if sms_receipt_column.name in index.columns:
                                copied.indexes.discard(index)
                        copied._columns.remove(sms_receipt_column)
                if copied.name == "service_feedback":
                    for column_name in (
                        "follow_up_status",
                        "follow_up_staff_id",
                        "follow_up_note",
                        "followed_up_at",
                    ):
                        if column_name not in copied.c:
                            continue
                        follow_up_column = copied.c[column_name]
                        for index in list(copied.indexes):
                            if follow_up_column.name in index.columns:
                                copied.indexes.discard(index)
                        for constraint in list(copied.foreign_key_constraints):
                            if any(
                                foreign_key.parent is follow_up_column
                                for foreign_key in constraint.elements
                            ):
                                for foreign_key in constraint.elements:
                                    foreign_key.parent.foreign_keys.discard(foreign_key)
                                    copied.foreign_keys.discard(foreign_key)
                                copied.foreign_key_constraints.discard(constraint)
                                copied.constraints.discard(constraint)
                        copied._columns.remove(follow_up_column)

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
            qr_columns = {column["name"] for column in inspector.get_columns("service_position_qrs")}
            self.assertTrue({"public_id", "store_id", "room_id", "status", "replaced_by_id"}.issubset(qr_columns))
            qr_indexes = {index["name"] for index in inspector.get_indexes("service_position_qrs")}
            self.assertIn("ix_service_position_qrs_public_id", qr_indexes)
            self.assertIn("uq_service_position_qrs_active_room", qr_indexes)
            project_columns = {column["name"] for column in inspector.get_columns("projects")}
            self.assertIn("current_published_version_id", project_columns)
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            self.assertIn("annual_membership_cycle_id", user_columns)
            user_indexes = {index["name"] for index in inspector.get_indexes("users")}
            self.assertIn("ix_users_annual_membership_cycle_id", user_indexes)
            occupancy_columns = {
                column["name"]
                for column in inspector.get_columns("position_occupancies")
            }
            self.assertIn("retained_until", occupancy_columns)
            occupancy_indexes = {
                index["name"]
                for index in inspector.get_indexes("position_occupancies")
            }
            self.assertIn("ix_position_occupancies_retained_until", occupancy_indexes)
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
