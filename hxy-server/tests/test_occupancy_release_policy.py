import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import (
    AuditLog,
    PositionOccupancy,
    Room,
    SelectionChangeRequest,
    SelectionRevision,
    SelectionSession,
    Store,
)
from app.domain.occupancy_release_policy import (
    list_release_candidates,
    release_due_occupancies,
)


NOW = datetime(2026, 8, 18, 4, 0, tzinfo=timezone.utc)


class OccupancyReleasePolicyTests(unittest.TestCase):
    def test_in_service_releases_thirty_minutes_after_expected_end(self):
        now = datetime(2026, 8, 26, 12, 30, tzinfo=timezone.utc)
        with self.SessionLocal() as db:
            occupancy, session = self.add_occupancy(db, "in_service", occupancy_status="in_service", session_status="confirmed")
            occupancy.actual_start_at = now - timedelta(hours=2)
            occupancy.expected_end_at = now - timedelta(minutes=30)
            db.commit()
            candidates = list_release_candidates(db, now, statuses=("in_service", "post_service_present"))
            self.assertEqual([c.occupancy_id for c in candidates], [occupancy.id])

    def test_service_without_expected_end_uses_actual_start_compatibility_deadline(self):
        now = datetime(2026, 8, 26, 12, 30, tzinfo=timezone.utc)
        with self.SessionLocal() as db:
            occupancy, _ = self.add_occupancy(
                db,
                "legacy-service",
                occupancy_status="post_service_present",
                session_status="submitted",
            )
            occupancy.actual_start_at = now - timedelta(minutes=91)
            occupancy.expected_end_at = None
            db.commit()

            candidates = list_release_candidates(
                db,
                now,
                statuses=("in_service", "post_service_present"),
            )

        self.assertEqual([candidate.occupancy_id for candidate in candidates], [occupancy.id])

    def test_service_without_any_time_anchor_is_not_auto_released(self):
        now = datetime(2026, 8, 26, 12, 30, tzinfo=timezone.utc)
        with self.SessionLocal() as db:
            occupancy, _ = self.add_occupancy(
                db,
                "legacy-without-anchor",
                occupancy_status="post_service_present",
                session_status="submitted",
            )
            occupancy.expected_end_at = None
            occupancy.actual_start_at = None
            occupancy.actual_service_end_at = None
            db.commit()

            candidates = list_release_candidates(
                db,
                now,
                statuses=("in_service", "post_service_present"),
            )

        self.assertEqual(candidates, [])

    def test_post_service_without_expected_end_uses_actual_service_end(self):
        now = datetime(2026, 8, 26, 12, 30, tzinfo=timezone.utc)
        with self.SessionLocal() as db:
            occupancy, _ = self.add_occupancy(
                db,
                "legacy-post-service",
                occupancy_status="post_service_present",
                session_status="submitted",
            )
            occupancy.actual_service_end_at = now - timedelta(minutes=31)
            db.commit()

            candidates = list_release_candidates(
                db,
                now,
                statuses=("in_service", "post_service_present"),
            )

        self.assertEqual([candidate.occupancy_id for candidate in candidates], [occupancy.id])
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
        with self.SessionLocal.begin() as db:
            store = Store(store_code="release-policy", name="释放策略门店", address="测试地址")
            db.add(store)
            db.flush()
            self.store_id = store.id

    def tearDown(self):
        self.engine.dispose()

    def add_occupancy(
        self,
        db,
        suffix: str,
        *,
        occupancy_status: str = "waiting_service",
        session_status: str = "submitted",
        submitted_minutes_ago: int = 60,
        room_type: str = "sofa",
    ) -> tuple[PositionOccupancy, SelectionSession]:
        room = Room(
            store_id=self.store_id,
            code=f"{room_type}-{suffix}",
            name=f"测试位{suffix}",
            room_type=room_type,
            room_group=room_type,
            status="occupied",
            operational_status="active",
        )
        session = SelectionSession(
            id=f"session-{suffix}",
            access_token_hash=f"token-{suffix}",
            store_id=self.store_id,
            status=session_status,
            items=[],
            diy_preferences={},
            pricing_snapshot={},
            submitted_at=NOW - timedelta(minutes=submitted_minutes_ago),
        )
        db.add_all([room, session])
        db.flush()
        occupancy = PositionOccupancy(
            store_id=self.store_id,
            room_id=room.id,
            selection_session_id=session.id,
            active_room_id=room.id,
            active_session_id=session.id,
            status=occupancy_status,
            source="personal_qr",
            hold_expires_at=(
                NOW - timedelta(seconds=1)
                if occupancy_status == "held"
                else None
            ),
            version=1,
        )
        db.add(occupancy)
        db.flush()
        return occupancy, session

    def test_waiting_service_releases_at_sixty_minutes_but_not_before(self):
        with self.SessionLocal.begin() as db:
            before, _ = self.add_occupancy(db, "before", submitted_minutes_ago=59)
            due, _ = self.add_occupancy(db, "due", submitted_minutes_ago=60)

        with self.SessionLocal() as db:
            candidate_ids = [item.occupancy_id for item in list_release_candidates(db, NOW)]

        self.assertNotIn(before.id, candidate_ids)
        self.assertIn(due.id, candidate_ids)

    def test_retention_extends_default_deadline(self):
        with self.SessionLocal.begin() as db:
            occupancy, _ = self.add_occupancy(db, "retained", submitted_minutes_ago=80)
            occupancy.retained_until = NOW + timedelta(minutes=10)

        with self.SessionLocal() as db:
            self.assertEqual(list_release_candidates(db, NOW), [])

    def test_only_unconfirmed_sofas_without_service_activity_are_candidates(self):
        with self.SessionLocal.begin() as db:
            eligible, _ = self.add_occupancy(db, "eligible")
            room, _ = self.add_occupancy(db, "room", room_type="room")
            confirmed, _ = self.add_occupancy(db, "confirmed", session_status="confirmed")
            fulfilled, fulfilled_session = self.add_occupancy(db, "fulfilled")
            fulfilled_session.fulfillment_order_id = 999
            started, _ = self.add_occupancy(db, "started")
            started.actual_start_at = NOW - timedelta(minutes=5)
            in_service, _ = self.add_occupancy(db, "in-service", occupancy_status="in_service")
            present, _ = self.add_occupancy(db, "present", occupancy_status="post_service_present")
            cleaning, _ = self.add_occupancy(db, "cleaning", occupancy_status="cleaning")

        with self.SessionLocal() as db:
            candidate_ids = {item.occupancy_id for item in list_release_candidates(db, NOW)}

        self.assertEqual(candidate_ids, {eligible.id})
        self.assertTrue({room.id, confirmed.id, fulfilled.id, started.id, in_service.id, present.id, cleaning.id}.isdisjoint(candidate_ids))

    def test_release_expires_session_rejects_pending_change_and_is_idempotent(self):
        with self.SessionLocal.begin() as db:
            occupancy, session = self.add_occupancy(db, "release")
            revision = SelectionRevision(
                id="revision-release",
                selection_session_id=session.id,
                revision_no=1,
                state="awaiting_staff_confirmation",
                idempotency_key="revision-release",
                snapshot={},
            )
            change = SelectionChangeRequest(
                id="change-release",
                selection_session_id=session.id,
                selection_revision_id=revision.id,
                state="awaiting_staff_confirmation",
            )
            db.add_all([revision, change])

        with self.SessionLocal() as db:
            first = release_due_occupancies(db, NOW, trigger="test")
            second = release_due_occupancies(db, NOW, trigger="test")

        self.assertEqual(first.released_count, 1)
        self.assertEqual(second.released_count, 0)
        with self.SessionLocal() as db:
            saved_occupancy = db.get(PositionOccupancy, occupancy.id)
            saved_session = db.get(SelectionSession, session.id)
            saved_revision = db.get(SelectionRevision, revision.id)
            saved_change = db.get(SelectionChangeRequest, change.id)
            audit = db.scalar(select(AuditLog).where(
                AuditLog.entity_type == "position_occupancy",
                AuditLog.entity_id == str(occupancy.id),
                AuditLog.action == "occupancy_auto_released",
            ))

        self.assertEqual(saved_occupancy.status, "released")
        self.assertIsNone(saved_occupancy.active_room_id)
        self.assertEqual(saved_session.status, "expired")
        self.assertEqual(saved_revision.state, "rejected")
        self.assertEqual(saved_change.state, "rejected")
        self.assertIsNotNone(saved_change.resolved_at)
        self.assertIsNotNone(audit)

    def test_observe_only_reports_due_items_without_writing(self):
        with self.SessionLocal.begin() as db:
            occupancy, session = self.add_occupancy(db, "observe")

        with self.SessionLocal() as db:
            result = release_due_occupancies(db, NOW, observe_only=True, trigger="test")

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.released_count, 0)
        with self.SessionLocal() as db:
            self.assertEqual(db.get(PositionOccupancy, occupancy.id).status, "waiting_service")
            self.assertEqual(db.get(SelectionSession, session.id).status, "submitted")


if __name__ == "__main__":
    unittest.main()
