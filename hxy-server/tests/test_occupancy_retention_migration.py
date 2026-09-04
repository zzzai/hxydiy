import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import MetaData, create_engine, inspect

from app import models  # noqa: F401
from app.db.session import Base
from app.domain.occupancy import occupancy_view
from app.models import PositionOccupancy


class OccupancyRetentionMigrationTests(unittest.TestCase):
    def test_upgrade_adds_nullable_retention_timestamp_and_index(self):
        project_root = Path(__file__).resolve().parents[1]
        previous_metadata = MetaData()
        for table in Base.metadata.tables.values():
            if table.name in {"service_position_qrs", "media_assets"}:
                continue
            copied = table.to_metadata(previous_metadata)
            if copied.name == "position_occupancies" and "retained_until" in copied.c:
                retained_until = copied.c.retained_until
                for index in list(copied.indexes):
                    if retained_until.name in index.columns:
                        copied.indexes.discard(index)
                copied._columns.remove(retained_until)
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
            database_path = Path(directory) / "occupancy-retention.db"
            database_url = f"sqlite:///{database_path}"
            engine = create_engine(database_url)
            previous_metadata.create_all(engine)
            engine.dispose()
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            environment["DATABASE_URL"] = database_url

            stamp = subprocess.run(
                [sys.executable, "-m", "alembic", "stamp", "20260815_member_grants"],
                cwd=project_root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(stamp.returncode, 0, stamp.stderr)
            upgrade = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=project_root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(upgrade.returncode, 0, upgrade.stderr)

            engine = create_engine(database_url)
            inspector = inspect(engine)
            columns = {
                column["name"]: column
                for column in inspector.get_columns("position_occupancies")
            }
            indexes = {
                index["name"]
                for index in inspector.get_indexes("position_occupancies")
            }
            engine.dispose()

        self.assertIn("retained_until", columns)
        self.assertTrue(columns["retained_until"]["nullable"])
        self.assertIn("ix_position_occupancies_retained_until", indexes)

    def test_occupancy_view_includes_retained_until(self):
        retained_until = datetime(2026, 8, 18, 2, 30, tzinfo=timezone.utc)
        occupancy = PositionOccupancy(
            id=1,
            store_id=1,
            room_id=1,
            selection_session_id="retention-session",
            active_room_id=1,
            active_session_id="retention-session",
            status="waiting_service",
            source="personal_qr",
            retained_until=retained_until,
            version=1,
        )

        self.assertEqual(occupancy_view(occupancy)["retained_until"], retained_until)


if __name__ == "__main__":
    unittest.main()
