import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import CouponTemplate, EventLog, Project, Staff, Store


class StoreIsolationRegressionTests(unittest.TestCase):
    """跨店读取/更新必须按认证员工门店隔离。"""

    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        now = datetime.now(timezone.utc)
        with self.SessionLocal() as db:
            store_a = Store(store_code="reg-a", name="回归 A 店", address="A")
            store_b = Store(store_code="reg-b", name="回归 B 店", address="B")
            db.add_all([store_a, store_b])
            db.flush()
            staff_a = Staff(username="reg-a-admin", password_hash=hash_password("pass"), name="A 店长", role="admin", store_id=store_a.id)
            db.add(staff_a)
            db.flush()
            project_a = Project(store_id=store_a.id, code="REG-A-P", category="bath", name="A 项目", publication_status="published")
            project_b = Project(store_id=store_b.id, code="REG-B-P", category="bath", name="B 项目", publication_status="published")
            db.add_all([project_a, project_b])
            db.flush()
            db.add_all([
                EventLog(event="project_view", page="diy", data={"project_id": project_a.id}, store_id=store_a.id, created_at=now),
                EventLog(event="project_view", page="diy", data={"project_id": project_b.id}, store_id=store_b.id, created_at=now),
                EventLog(event="diy_entry_view", page="diy", data={}, store_id=store_a.id, created_at=now),
                EventLog(event="diy_entry_view", page="diy", data={}, store_id=store_b.id, created_at=now),
            ])
            coupon_a = CouponTemplate(store_id=store_a.id, code="REG-A-C", name="A 券", status="draft")
            coupon_b = CouponTemplate(store_id=store_b.id, code="REG-B-C", name="B 券", status="draft")
            db.add_all([coupon_a, coupon_b])
            db.commit()
            self.staff_id = staff_a.id
            self.store_a_id = store_a.id
            self.coupon_a_id = coupon_a.id
            self.coupon_b_id = coupon_b.id

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {create_staff_token(self.staff_id, 'admin')}"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_analytics_only_reports_current_store_events_and_projects(self):
        response = self.client.get("/api/v1/admin/analytics", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["funnel"]["diy_entry_view"], 1)
        self.assertEqual([item["name"] for item in payload["hot_projects"]], ["A 项目"])

    def test_operations_summary_ignores_event_data_store_id_spoofing(self):
        with self.SessionLocal() as db:
            db.add(EventLog(event="project_view", page="diy", data={"store_id": 1}, store_id=2, created_at=datetime.now(timezone.utc)))
            db.commit()
        response = self.client.get("/api/v1/admin/operations-summary", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["funnel"]["project_view"], 1)

    def test_coupon_list_and_update_hide_other_store_template(self):
        listed = self.client.get("/api/v1/admin/coupons", headers=self.headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual([item["id"] for item in listed.json()["items"]], [self.coupon_a_id])

        cross_update = self.client.post(
            f"/api/v1/admin/coupons/{self.coupon_b_id}",
            headers=self.headers,
            json={"name": "越权修改"},
        )
        self.assertEqual(cross_update.status_code, 404)

    def test_coupon_creation_always_belongs_to_authenticated_store(self):
        created = self.client.post(
            "/api/v1/admin/coupons",
            headers=self.headers,
            json={"code": "REG-NEW", "name": "新券"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        with self.SessionLocal() as db:
            row = db.get(CouponTemplate, created.json()["data"]["id"])
            self.assertEqual(row.store_id, self.store_a_id)


if __name__ == "__main__":
    unittest.main()
