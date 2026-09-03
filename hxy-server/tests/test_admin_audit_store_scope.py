import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import admin_v2
from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, Staff, Store


class AdminAuditStoreScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            cls.store_a = Store(store_code="audit-a", name="审计甲店", address="甲")
            cls.store_b = Store(store_code="audit-b", name="审计乙店", address="乙")
            db.add_all([cls.store_a, cls.store_b])
            db.flush()
            cls.staff = Staff(
                username="audit-admin",
                password_hash=hash_password("audit-pass"),
                name="甲店管理员",
                role="admin",
                store_id=cls.store_a.id,
                status="active",
            )
            db.add(cls.staff)
            db.commit()
            cls.staff_id = cls.staff.id
            cls.store_a_id = cls.store_a.id
            cls.store_b_id = cls.store_b.id

        app.dependency_overrides[get_db] = cls._get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)
        cls.engine.dispose()

    @classmethod
    def _get_db(cls):
        with cls.SessionLocal() as db:
            yield db

    def test_audit_helper_persists_explicit_store_scope_from_staff(self):
        with self.SessionLocal() as db:
            staff = db.get(Staff, self.staff_id)
            admin_v2._audit(db, staff, "store_scoped_action", "room", "room-a", {"reason": "test"})
            db.commit()
            row = db.scalar(select(AuditLog).where(AuditLog.action == "store_scoped_action"))
            self.assertIsNotNone(row)
            self.assertEqual(row.store_id, self.store_a_id)
            self.assertEqual(row.actor_id, staff.name)

    def test_store_admin_audit_query_excludes_other_store_without_detail_store_id(self):
        with self.SessionLocal() as db:
            db.add_all([
                AuditLog(
                    actor_type="staff", actor_id="甲店管理员", store_id=self.store_a_id,
                    action="own_action", entity_type="room", entity_id="a",
                    detail={}, created_at=datetime(2026, 8, 25, 1, tzinfo=timezone.utc),
                ),
                AuditLog(
                    actor_type="staff", actor_id="乙店管理员", store_id=self.store_b_id,
                    action="other_action", entity_type="room", entity_id="b",
                    detail={}, created_at=datetime(2026, 8, 25, 2, tzinfo=timezone.utc),
                ),
            ])
            db.commit()

        response = self.client.get(
            "/api/v1/admin/audit-logs",
            params={"start_date": "2026-08-25", "end_date": "2026-08-25"},
            headers={"Authorization": f"Bearer {create_staff_token(self.staff_id, 'admin')}"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        actions = {item["action"] for item in response.json()["items"]}
        self.assertIn("own_action", actions)
        self.assertNotIn("other_action", actions)


if __name__ == "__main__":
    unittest.main()
