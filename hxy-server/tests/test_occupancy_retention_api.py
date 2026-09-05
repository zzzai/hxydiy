import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import PositionOccupancy, Room, SelectionSession, Staff, Store


class OccupancyRetentionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(
            bind=cls.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal.begin() as db:
            store = Store(store_code="retention-api", name="续留接口门店", address="测试地址")
            db.add(store)
            db.flush()
            admin = Staff(
                username="retention-admin",
                password_hash=hash_password("pass"),
                name="店长",
                role="admin",
                store_id=store.id,
                status="active",
            )
            staff = Staff(
                username="retention-staff",
                password_hash=hash_password("pass"),
                name="前台",
                role="manager",
                store_id=store.id,
                status="active",
            )
            db.add_all([admin, staff])
            db.flush()
            cls.store_id = store.id
            cls.admin_headers = {
                "Authorization": f"Bearer {create_staff_token(admin.id, admin.role)}"
            }
            cls.staff_headers = {
                "Authorization": f"Bearer {create_staff_token(staff.id, staff.role)}"
            }

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def add_waiting(self, suffix: str, *, minutes_ago: int = 90) -> PositionOccupancy:
        now = datetime.now(timezone.utc)
        with self.SessionLocal.begin() as db:
            room = Room(
                store_id=self.store_id,
                code=f"sofa-retain-{suffix}",
                name=f"续留沙发{suffix}",
                room_type="sofa",
                room_group="sofa",
                status="available",
                operational_status="active",
            )
            session = SelectionSession(
                id=f"retain-session-{suffix}",
                access_token_hash=f"retain-token-{suffix}",
                store_id=self.store_id,
                status="submitted",
                items=[],
                diy_preferences={},
                pricing_snapshot={},
                submitted_at=now - timedelta(minutes=minutes_ago),
            )
            db.add_all([room, session])
            db.flush()
            occupancy = PositionOccupancy(
                store_id=self.store_id,
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
        with self.SessionLocal() as db:
            return db.get(PositionOccupancy, occupancy_id)

    def test_staff_retention_starts_thirty_minutes_from_current_time_when_overdue(self):
        occupancy = self.add_waiting("staff-retain", minutes_ago=180)
        requested_at = datetime.now(timezone.utc)

        response = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy.id}/retain",
            headers=self.staff_headers,
            json={"version": occupancy.version, "minutes": 30, "reason": "顾客仍在等候"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        retained_until = datetime.fromisoformat(
            response.json()["retained_until"].replace("Z", "+00:00")
        )
        self.assertGreaterEqual(retained_until, requested_at + timedelta(minutes=30))
        self.assertLess(retained_until, requested_at + timedelta(minutes=31))

    def test_retention_rejects_version_conflict_and_non_waiting_state(self):
        occupancy = self.add_waiting("conflict")
        conflict = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy.id}/retain",
            headers=self.staff_headers,
            json={"version": occupancy.version + 1, "minutes": 30, "reason": "仍在等候"},
        )
        self.assertEqual(conflict.status_code, 409, conflict.text)

        with self.SessionLocal.begin() as db:
            saved = db.get(PositionOccupancy, occupancy.id)
            saved.status = "in_service"
        invalid_state = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy.id}/retain",
            headers=self.staff_headers,
            json={"version": occupancy.version, "minutes": 30, "reason": "仍在等候"},
        )
        self.assertEqual(invalid_state.status_code, 409, invalid_state.text)

    def test_retention_only_accepts_exactly_thirty_minutes(self):
        occupancy = self.add_waiting("invalid-minutes")
        response = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy.id}/retain",
            headers=self.staff_headers,
            json={"version": occupancy.version, "minutes": 60, "reason": "仍在等候"},
        )
        self.assertEqual(response.status_code, 422, response.text)

    def test_preview_is_store_scoped_and_bulk_release_requires_admin(self):
        occupancy = self.add_waiting("bulk")
        preview = self.client.get(
            "/api/v1/admin/occupancies/release-candidates",
            headers=self.staff_headers,
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        item = next(
            candidate for candidate in preview.json()["items"]
            if candidate["occupancy_id"] == occupancy.id
        )

        denied = self.client.post(
            "/api/v1/admin/occupancies/bulk-release",
            headers=self.staff_headers,
            json={
                "items": [{"occupancy_id": occupancy.id, "version": item["version"]}],
                "reason": "闭店清理遗留占用",
            },
        )
        self.assertEqual(denied.status_code, 403, denied.text)

        released = self.client.post(
            "/api/v1/admin/occupancies/bulk-release",
            headers=self.admin_headers,
            json={
                "items": [{"occupancy_id": occupancy.id, "version": item["version"]}],
                "reason": "闭店清理遗留占用",
            },
        )
        self.assertEqual(released.status_code, 200, released.text)
        self.assertEqual(released.json()["released"], [occupancy.id])
        self.assertEqual(released.json()["skipped"], [])

    def test_bulk_release_skips_changed_version_without_releasing(self):
        occupancy = self.add_waiting("changed")
        response = self.client.post(
            "/api/v1/admin/occupancies/bulk-release",
            headers=self.admin_headers,
            json={
                "items": [{"occupancy_id": occupancy.id, "version": occupancy.version + 1}],
                "reason": "闭店清理遗留占用",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["released"], [])
        self.assertEqual(response.json()["skipped"], [
            {"occupancy_id": occupancy.id, "reason": "version_changed"}
        ])
        with self.SessionLocal() as db:
            self.assertEqual(db.get(PositionOccupancy, occupancy.id).status, "waiting_service")


if __name__ == "__main__":
    unittest.main()
