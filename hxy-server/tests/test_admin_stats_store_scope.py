import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import EventLog, Order, Staff, Store, User


class AdminStatsStoreScopeTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        now = datetime.now(timezone.utc)
        with self.SessionLocal() as db:
            first = Store(store_code="stats-a", name="统计 A 店", address="A")
            second = Store(store_code="stats-b", name="统计 B 店", address="B")
            db.add_all([first, second])
            db.flush()
            staff = Staff(
                username="stats-a-admin",
                password_hash=hash_password("test-pass"),
                name="A 店长",
                role="admin",
                store_id=first.id,
            )
            first_user = User(openid="stats-a-user", phone="13900000001", created_at=now)
            second_user = User(openid="stats-b-user", phone="13900000002", created_at=now)
            db.add_all([staff, first_user, second_user])
            db.flush()
            db.add_all([
                Order(
                    order_no="STATS-A-ORDER",
                    order_type="service",
                    user_id=first_user.id,
                    store_id=first.id,
                    items=[],
                    total_amount_cents=1000,
                    pay_amount_cents=1000,
                    status="completed",
                    pay_status="paid",
                    created_at=now,
                ),
                Order(
                    order_no="STATS-B-ORDER",
                    order_type="service",
                    user_id=second_user.id,
                    store_id=second.id,
                    items=[],
                    total_amount_cents=1000,
                    pay_amount_cents=1000,
                    status="completed",
                    pay_status="paid",
                    created_at=now,
                ),
                EventLog(event="page_view", page="home", data={}, store_id=first.id, created_at=now),
                EventLog(event="page_view", page="home", data={}, store_id=second.id, created_at=now),
            ])
            db.commit()
            self.headers = {"Authorization": f"Bearer {create_staff_token(staff.id, 'admin')}"}

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_stats_only_include_current_store_traffic_and_new_users(self):
        response = self.client.get("/api/v1/admin/stats", headers=self.headers)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["page_views"], 1)
        self.assertEqual(response.json()["new_users"], 1)


if __name__ == "__main__":
    unittest.main()
