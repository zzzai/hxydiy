import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models import CouponTemplate, Order, Store, User, UserCoupon


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

    def _create_order(self, coupon_id):
        return self.client.post("/api/v1/orders", headers=self._auth(), json={
            "order_type": "service", "store_id": 1, "coupon_id": coupon_id,
            "items": [], "booking_date": None, "booking_time": None,
        })

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
