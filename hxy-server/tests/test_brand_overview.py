import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import Order, ServiceFeedback, Staff, Store, User


class BrandOverviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        now = datetime.now(timezone.utc)
        with cls.SessionLocal() as db:
            store = Store(store_code="brand-store-a", name="品牌门店 A", address="A", status="open")
            preparing = Store(store_code="brand-store-b", name="品牌门店 B", address="B", status="preparing")
            admin = Staff(username="brand-admin", password_hash=hash_password("pass1234"), name="总部", role="admin", store_id=None)
            manager = Staff(username="brand-manager", password_hash=hash_password("pass1234"), name="店长", role="manager", store_id=None)
            user = User(openid="brand-customer", phone="13800000001")
            db.add_all([store, preparing, admin, manager, user])
            db.flush()
            db.add_all([
                Order(store_id=store.id, user_id=user.id, order_no="BRAND-1", order_type="service", status="paid", pay_status="paid", pay_amount_cents=9900, created_at=now),
                Order(store_id=store.id, user_id=user.id, order_no="BRAND-2", order_type="service", status="cancelled", pay_status="paid", pay_amount_cents=5000, created_at=now),
                ServiceFeedback(store_id=store.id, selection_session_id="brand-session", customer_id=user.id, rating=2, tags=[], created_at=now),
                ServiceFeedback(store_id=store.id, selection_session_id="brand-session-2", customer_id=user.id, rating=5, tags=[], created_at=now),
            ])
            db.commit()
            cls.store_id = store.id
            cls.admin_headers = {"Authorization": f"Bearer {create_staff_token(admin.id, admin.role)}"}
            cls.manager_headers = {"Authorization": f"Bearer {create_staff_token(manager.id, manager.role)}"}

        def override_get_db():
            with cls.SessionLocal() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def test_hq_overview_aggregates_all_stores(self):
        response = self.client.get("/api/v1/admin/v2/brand/overview", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["scope"], "brand")
        self.assertEqual(body["summary"]["store_count"], 2)
        self.assertEqual(body["summary"]["open_store_count"], 1)
        self.assertEqual(body["summary"]["paid_order_count"], 1)
        self.assertEqual(body["summary"]["paid_amount_cents"], 9900)
        self.assertEqual(body["summary"]["review_count"], 2)
        self.assertEqual(body["summary"]["average_rating"], 3.5)
        self.assertEqual(body["summary"]["low_rating_count"], 1)
        self.assertEqual(len(body["stores"]), 2)

    def test_hq_overview_rejects_store_scoped_manager(self):
        response = self.client.get("/api/v1/admin/v2/brand/overview", headers=self.manager_headers)
        self.assertEqual(response.status_code, 403, response.text)

    def test_hq_overview_validates_date_range(self):
        response = self.client.get(
            "/api/v1/admin/v2/brand/overview",
            params={"start_date": "2026-10-22", "end_date": "2026-10-01"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 400, response.text)
