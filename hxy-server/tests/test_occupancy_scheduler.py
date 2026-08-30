import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.session import Base
from app.models import PositionOccupancy, Room, SelectionSession, Store
from app.services.occupancy_scheduler import (
    build_occupancy_scheduler,
    run_scheduled_occupancy_cleanup,
)


NOW = datetime(2026, 8, 18, 4, 0, tzinfo=timezone.utc)


class OccupancySchedulerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_scheduler_is_disabled_outside_production_or_when_flag_is_off(self):
        self.assertIsNone(build_occupancy_scheduler(Settings(
            environment="test",
            occupancy_scheduler_enabled=True,
        )))
        self.assertIsNone(build_occupancy_scheduler(Settings(
            environment="production",
            occupancy_scheduler_enabled=False,
        )))

    def test_production_scheduler_registers_minute_and_closing_sweeps_in_store_timezone(self):
        scheduler = build_occupancy_scheduler(Settings(
            environment="production",
            occupancy_scheduler_enabled=True,
            occupancy_scheduler_observe_only=True,
            occupancy_scheduler_interval_seconds=90,
            occupancy_closing_hour=3,
            occupancy_timezone="Asia/Shanghai",
        ))

        self.assertIsNotNone(scheduler)
        jobs = {job.id: job for job in scheduler.get_jobs()}
        self.assertEqual(set(jobs), {"occupancy-minute-sweep", "occupancy-closing-sweep"})
        self.assertIn("interval[0:01:30]", str(jobs["occupancy-minute-sweep"].trigger))
        self.assertIn("hour='3'", str(jobs["occupancy-closing-sweep"].trigger))
        self.assertEqual(str(scheduler.timezone), "Asia/Shanghai")

    def test_observe_only_scheduler_reports_candidate_without_writing_database(self):
        with self.SessionLocal.begin() as db:
            store = Store(
                store_code="scheduler-observe",
                name="调度观察门店",
                address="测试地址",
            )
            db.add(store)
            db.flush()
            room = Room(
                store_id=store.id,
                code="sofa-observe",
                name="观察沙发",
                room_type="sofa",
                room_group="sofa",
                status="occupied",
                operational_status="active",
            )
            session = SelectionSession(
                id="scheduler-observe-session",
                access_token_hash="scheduler-observe-token",
                store_id=store.id,
                status="submitted",
                items=[],
                diy_preferences={},
                pricing_snapshot={},
                submitted_at=NOW - timedelta(minutes=61),
            )
            db.add_all([room, session])
            db.flush()
            occupancy = PositionOccupancy(
                store_id=store.id,
                room_id=room.id,
                selection_session_id=session.id,
                active_room_id=room.id,
                active_session_id=session.id,
                status="waiting_service",
                source="personal_qr",
                version=1,
            )
            db.add(occupancy)
            db.flush()
            occupancy_id = occupancy.id

        runtime_settings = Settings(
            environment="production",
            occupancy_scheduler_enabled=True,
            occupancy_scheduler_observe_only=True,
        )
        with (
            patch("app.services.occupancy_scheduler.SessionLocal", self.SessionLocal),
            patch("app.services.occupancy_scheduler.utcnow", return_value=NOW),
        ):
            result = run_scheduled_occupancy_cleanup(runtime_settings, "test_observe")

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.released_count, 0)
        with self.SessionLocal() as db:
            saved_occupancy = db.get(PositionOccupancy, occupancy_id)
            saved_session = db.get(SelectionSession, "scheduler-observe-session")
            self.assertEqual(saved_occupancy.status, "waiting_service")
            self.assertEqual(saved_session.status, "submitted")

    def test_postgresql_lock_contention_skips_cleanup(self):
        db = MagicMock()
        db.get_bind.return_value.dialect.name = "postgresql"
        db.scalar.return_value = False
        session_context = MagicMock()
        session_context.__enter__.return_value = db
        session_context.__exit__.return_value = False
        runtime_settings = Settings(
            environment="production",
            occupancy_scheduler_enabled=True,
            occupancy_scheduler_observe_only=False,
        )

        with (
            patch("app.services.occupancy_scheduler.SessionLocal", return_value=session_context),
            patch("app.services.occupancy_scheduler.release_due_occupancies") as cleanup,
        ):
            result = run_scheduled_occupancy_cleanup(runtime_settings, "test_lock")

        self.assertEqual(result.candidate_count, 0)
        self.assertEqual(result.released_count, 0)
        cleanup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
