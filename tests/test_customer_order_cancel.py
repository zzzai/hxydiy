import unittest
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models import CouponTemplate, Order, OrderEvent, User, UserCoupon


class CustomerOrderCancelTests(unittest.TestCase):
    """顾客侧取消订单：仅未支付订单可自助取消，释放锁定券。"""

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
            self.owner = User(openid=f"cancel-owner-{suffix}", phone=f"138{suffix[:8]}")
            self.other = User(openid=f"cancel-other-{suffix}", phone=f"139{suffix[:8]}")
            db.add_all([self.owner, self.other])
            db.flush()
            self.tpl = CouponTemplate(name="新人券", code=f"cancel-tpl-{suffix}", coupon_type="amount", amount_cents=1000, min_spend_cents=0, status="published", validity_days=30)
            db.add(self.tpl)
            db.flush()
            self.pending = Order(
                order_no=f"HXY{suffix}AAAAAA", order_type="service", user_id=self.owner.id,
                store_id=1, items=[], total_amount_cents=9900, pay_amount_cents=8900,
                discount_cents=1000, status="pending_payment", pay_status="unpaid",
            )
            self.paid = Order(
                order_no=f"HXY{suffix}BBBBBB", order_type="service", user_id=self.owner.id,
                store_id=1, items=[], total_amount_cents=9900, pay_amount_cents=9900,
                status="paid", pay_status="paid",
            )
            db.add_all([self.pending, self.paid])
            db.flush()
            self.pending_id, self.paid_id = self.pending.id, self.paid.id
            self.owner_id, self.other_id = self.owner.id, self.other.id
            db.commit()

    def _auth(self, user_id: int) -> dict:
        return {"Authorization": f"Bearer {create_access_token(str(user_id), 'openid-x')}"}

    def _post(self, order_id: int, user_id: int):
        return self.client.post(f"/api/v1/orders/{order_id}/cancel", headers=self._auth(user_id))

    def test_cancel_requires_login(self):
        response = self.client.post(f"/api/v1/orders/{self.pending_id}/cancel")
        self.assertEqual(response.status_code, 401)

    def test_cannot_cancel_others_order(self):
        response = self._post(self.pending_id, self.other_id)
        self.assertEqual(response.status_code, 404)

    def test_cancel_pending_payment_order_releases_locked_coupon(self):
        with self.SessionLocal() as db:
            coupon = UserCoupon(user_id=self.owner_id, template_id=self.tpl.id, status="locked")
            db.add(coupon)
            db.flush()
            order = db.get(Order, self.pending_id)
            order.coupon_id = coupon.id
            coupon_id = coupon.id
            db.commit()

        response = self._post(self.pending_id, self.owner_id)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "cancelled")
        with self.SessionLocal() as db:
            order = db.get(Order, self.pending_id)
            self.assertEqual(order.status, "cancelled")
            coupon = db.get(UserCoupon, coupon_id)
            self.assertEqual(coupon.status, "unused")
            event = db.scalar(select(OrderEvent).where(
                OrderEvent.order_id == self.pending_id,
                OrderEvent.to_status == "cancelled",
            ))
            self.assertIsNotNone(event)

    def test_paid_order_cannot_be_self_cancelled(self):
        response = self._post(self.paid_id, self.owner_id)
        self.assertEqual(response.status_code, 409)

    def test_cancel_twice_is_rejected(self):
        self.assertEqual(self._post(self.pending_id, self.owner_id).status_code, 200)
        response = self._post(self.pending_id, self.owner_id)
        self.assertEqual(response.status_code, 409)

    def test_cancelled_order_cannot_start_payment(self):
        self.assertEqual(self._post(self.pending_id, self.owner_id).status_code, 200)
        with mock.patch(
            "app.api.payments.create_jsapi_payment",
            new=mock.AsyncMock(return_value={"prepay_id": "must-not-be-returned"}),
        ):
            response = self.client.post(
                f"/api/v1/payments/{self.pending_id}/pay",
                headers=self._auth(self.owner_id),
            )

        self.assertEqual(response.status_code, 409, response.text)


if __name__ == "__main__":
    unittest.main()
