import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models import CouponTemplate, Order, PriceBook, Project, Store, User, UserCoupon


class OrderCouponLifecycleTests(unittest.TestCase):
    """优惠券生命周期：过期券不可用；支付成功回调置 used。"""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)

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

    def setUp(self):
        import secrets
        suffix = secrets.token_hex(4).upper()
        with self.SessionLocal() as db:
            db.add(Store(store_code=f"store-{suffix}", name="测试门店", address="测试地址"))
            db.commit()
            self.user = User(openid=f"coupon-user-{suffix}", phone=f"138{suffix[:8]}")
            db.add(self.user)
            db.flush()
            self.tpl = CouponTemplate(
                name="测试券", code=f"tpl-{suffix}", coupon_type="amount",
                amount_cents=1000, min_spend_cents=0, status="published", validity_days=30,
            )
            db.add(self.tpl)
            db.flush()
            self.user_id, self.tpl_id = self.user.id, self.tpl.id
            db.commit()

    def _auth(self):
        return {"Authorization": f"Bearer {create_access_token(str(self.user_id), 'openid-x')}"}

    def _coupon(self, status="unused", expire_at=None):
        with self.SessionLocal() as db:
            coupon = UserCoupon(user_id=self.user_id, template_id=self.tpl_id, status=status, expire_at=expire_at)
            db.add(coupon)
            db.commit()
            return coupon.id

    def _create_order(self, coupon_id, *, store_id=1, items=None):
        return self.client.post("/api/v1/orders", headers=self._auth(), json={
            "order_type": "service", "store_id": store_id, "coupon_id": coupon_id,
            "items": items or [], "booking_date": None, "booking_time": None,
        })

    def test_order_uses_latest_store_price_book_record(self):
        older_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        newer_at = older_at + timedelta(days=1)
        with self.SessionLocal() as db:
            store = Store(store_code=f"price-store-{self.user_id}", name="价格测试门店", address="测试地址")
            db.add(store)
            db.flush()
            project = Project(
                store_id=store.id,
                code=f"price-project-{self.user_id}",
                category="test",
                name="价格测试项目",
                publication_status="published",
            )
            db.add(project)
            db.flush()
            db.add_all([
                PriceBook(
                    project_id=project.id,
                    price_type="store",
                    amount_cents=8800,
                    version="old",
                    published_at=older_at,
                ),
                PriceBook(
                    project_id=project.id,
                    price_type="store",
                    amount_cents=12800,
                    version="new",
                    published_at=newer_at,
                ),
            ])
            db.commit()
            store_id, project_id = store.id, project.id

        response = self._create_order(
            None,
            store_id=store_id,
            items=[{"project_id": project_id, "quantity": 2, "addon_ids": []}],
        )

        self.assertEqual(response.status_code, 200, response.text)
        order = response.json()["data"]
        self.assertEqual(order["items"][0]["unit_price_cents"], 12800)
        self.assertEqual(order["total_amount_cents"], 25600)
        self.assertEqual(order["pay_amount_cents"], 25600)

    def test_expired_coupon_is_rejected(self):
        expired = datetime.now(timezone.utc) - timedelta(days=1)
        coupon_id = self._coupon(expire_at=expired)
        response = self._create_order(coupon_id)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("过期", response.json()["detail"])

    def test_valid_coupon_locks_on_order_creation(self):
        coupon_id = self._coupon(expire_at=datetime.now(timezone.utc) + timedelta(days=5))
        response = self._create_order(coupon_id)
        self.assertEqual(response.status_code, 200, response.text)
        with self.SessionLocal() as db:
            coupon = db.get(UserCoupon, coupon_id)
            self.assertEqual(coupon.status, "locked")

    def test_member_order_does_not_apply_non_member_auto_coupon(self):
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.is_member = True
            store = Store(store_code=f"member-price-store-{self.user_id}", name="会员价格店", address="测试地址")
            db.add(store)
            db.flush()
            project = Project(
                store_id=store.id,
                code=f"member-price-project-{self.user_id}",
                category="test",
                name="会员价格项目",
                publication_status="published",
            )
            db.add(project)
            db.flush()
            db.add_all([
                PriceBook(project_id=project.id, price_type="store", amount_cents=10000),
                PriceBook(project_id=project.id, price_type="member", amount_cents=8000),
            ])
            template = db.get(CouponTemplate, self.tpl_id)
            template.auto_apply = True
            template.amount_cents = 3000
            db.commit()
            store_id, project_id = store.id, project.id

        response = self._create_order(
            None,
            store_id=store_id,
            items=[{"project_id": project_id, "quantity": 1, "addon_ids": []}],
        )
        self.assertEqual(response.status_code, 200, response.text)
        order = response.json()["data"]
        self.assertEqual(order["total_amount_cents"], 8000)
        self.assertEqual(order["pay_amount_cents"], 8000)
        with self.SessionLocal() as db:
            persisted = db.scalar(select(Order).where(Order.id == order["id"]))
            self.assertIsNone(persisted.coupon_id)

    def test_member_order_rejects_explicit_non_member_coupon(self):
        with self.SessionLocal() as db:
            db.get(User, self.user_id).is_member = True
            coupon = UserCoupon(
                user_id=self.user_id, template_id=self.tpl_id,
                status="unused", expire_at=datetime.now(timezone.utc) + timedelta(days=5),
            )
            db.add(coupon)
            db.commit()
            coupon_id = coupon.id
        response = self._create_order(coupon_id)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("会员已享会员价", response.json()["detail"])

    def test_pay_callback_marks_coupon_used(self):
        coupon_id = self._coupon(expire_at=datetime.now(timezone.utc) + timedelta(days=5))
        order_id = self._create_order(coupon_id).json()["data"]["id"]
        with self.SessionLocal() as db:
            order = db.get(Order, order_id)
            order_no = order.order_no

        with mock.patch("app.api.payments.verify_and_decrypt_notify", new=mock.AsyncMock(return_value={
            "trade_state": "SUCCESS",
            "out_trade_no": order_no,
            "transaction_id": "txn-test-1",
        })):
            response = self.client.post("/api/v1/payments/notify", content=b"{}", headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200)
        with self.SessionLocal() as db:
            coupon = db.get(UserCoupon, coupon_id)
            self.assertEqual(coupon.status, "used")
            self.assertEqual(coupon.used_order_id, order_id)

    def test_closed_callback_releases_locked_coupon(self):
        coupon_id = self._coupon(expire_at=datetime.now(timezone.utc) + timedelta(days=5))
        order_id = self._create_order(coupon_id).json()["data"]["id"]
        with self.SessionLocal() as db:
            order_no = db.get(Order, order_id).order_no

        with mock.patch("app.api.payments.verify_and_decrypt_notify", new=mock.AsyncMock(return_value={
            "trade_state": "CLOSED",
            "out_trade_no": order_no,
            "transaction_id": "",
        })):
            response = self.client.post("/api/v1/payments/notify", content=b"{}", headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200)
        with self.SessionLocal() as db:
            self.assertEqual(db.get(Order, order_id).status, "cancelled")
            self.assertEqual(db.get(UserCoupon, coupon_id).status, "unused")

    def test_success_callback_does_not_revive_cancelled_order(self):
        coupon_id = self._coupon(expire_at=datetime.now(timezone.utc) + timedelta(days=5))
        order_id = self._create_order(coupon_id).json()["data"]["id"]
        with self.SessionLocal() as db:
            order = db.get(Order, order_id)
            order_no = order.order_no
            order.status = "cancelled"
            db.commit()

        with mock.patch("app.api.payments.verify_and_decrypt_notify", new=mock.AsyncMock(return_value={
            "trade_state": "SUCCESS",
            "out_trade_no": order_no,
            "transaction_id": "txn-test-2",
        })):
            response = self.client.post("/api/v1/payments/notify", content=b"{}", headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200)
        with self.SessionLocal() as db:
            self.assertEqual(db.get(Order, order_id).status, "cancelled")
            self.assertEqual(db.get(UserCoupon, coupon_id).status, "locked")


if __name__ == "__main__":
    unittest.main()
