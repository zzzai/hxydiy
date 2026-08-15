import hashlib
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models import BrowserInstance, CouponTemplate, CustomerVerificationCode, Order, SelectionSession, ServiceFeedback, User, UserCoupon


class H5AuthApiTests(unittest.TestCase):
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

    def send_code(self, phone="13800138000"):
        response = self.client.post("/api/v1/auth/h5/send-code", json={"phone": phone})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_h5_coupon_claim_requires_phone_login(self):
        response = self.client.post("/api/v1/coupons/claim", json={"template_id": 1})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "请先完成手机号登录")

    def test_send_code_returns_local_debug_code_and_enforces_interval(self):
        first = self.send_code()
        self.assertEqual(len(first["debug_code"]), 6)
        second = self.client.post("/api/v1/auth/h5/send-code", json={"phone": "13800138000"})
        self.assertEqual(second.status_code, 429)

    def test_wrong_code_is_limited_and_correct_code_creates_stable_user(self):
        payload = self.send_code("13900139000")
        for _ in range(5):
            response = self.client.post("/api/v1/auth/h5/login", json={"phone": "13900139000", "code": "000000"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("次数", response.json()["detail"])

        with self.SessionLocal() as db:
            code = db.scalar(select(CustomerVerificationCode).where(CustomerVerificationCode.phone == "13900139000"))
            code.sent_at = code.sent_at.replace(year=2020)
            db.commit()
        fresh = self.send_code("13900139000")

        first = self.client.post("/api/v1/auth/h5/login", json={"phone": "13900139000", "code": fresh["debug_code"]})
        self.assertEqual(first.status_code, 200)
        with self.SessionLocal() as db:
            latest = db.scalar(select(CustomerVerificationCode).where(CustomerVerificationCode.phone == "13900139000").order_by(CustomerVerificationCode.sent_at.desc()))
            latest.sent_at = latest.sent_at.replace(year=2020)
            db.commit()
        second_code = self.send_code("13900139000")
        second = self.client.post("/api/v1/auth/h5/login", json={"phone": "13900139000", "code": second_code["debug_code"]})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["user"]["id"], second.json()["user"]["id"])
        with self.SessionLocal() as db:
            users = list(db.scalars(select(User).where(User.phone == "13900139000")))
            self.assertEqual(len(users), 1)

    def test_login_can_bind_an_anonymous_selection_session(self):
        session_id = "h5-auth-selection"
        with self.SessionLocal() as db:
            db.add(SelectionSession(
                id=session_id,
                access_token_hash=hashlib.sha256(b"h5-auth-selection-token").hexdigest(),
                store_id=1,
                items=[],
                diy_preferences={},
            ))
            db.commit()
        code = self.send_code("13700137000")["debug_code"]
        response = self.client.post("/api/v1/auth/h5/login", json={
            "phone": "13700137000", "code": code, "selection_session_id": session_id,
        }, headers={"X-Selection-Token": "h5-auth-selection-token"})
        self.assertEqual(response.status_code, 200)
        with self.SessionLocal() as db:
            user = db.scalar(select(User).where(User.phone == "13700137000"))
            self.assertEqual(db.get(SelectionSession, session_id).customer_id, user.id)

    def test_phone_login_does_not_bind_selection_without_its_access_token(self):
        session_id = "h5-auth-protected-selection"
        with self.SessionLocal() as db:
            anonymous = User(openid="anon_protected_selection")
            db.add(anonymous)
            db.flush()
            db.add(SelectionSession(
                id=session_id,
                access_token_hash=hashlib.sha256(b"protected-selection-token").hexdigest(),
                store_id=1,
                customer_id=anonymous.id,
                status="confirmed",
                items=[],
                diy_preferences={},
            ))
            db.commit()

        code = self.send_code("13600136000")["debug_code"]
        response = self.client.post("/api/v1/auth/h5/login", json={
            "phone": "13600136000", "code": code, "selection_session_id": session_id,
        }, headers={"X-Selection-Token": "wrong-selection-token"})

        self.assertEqual(response.status_code, 403, response.text)
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            self.assertEqual(session.customer_id, anonymous.id)
            verification = db.scalar(select(CustomerVerificationCode).where(CustomerVerificationCode.phone == "13600136000"))
            self.assertIsNone(verification.used_at)

    def test_phone_login_merges_anonymous_completed_record_and_feedback_for_browser(self):
        anonymous_id = None
        with self.SessionLocal() as db:
            anonymous = User(openid="anon_merge_browser")
            db.add(anonymous)
            db.flush()
            anonymous_id = anonymous.id
            db.add(BrowserInstance(token_hash="merge-browser-token", customer_id=anonymous.id))
            db.add_all([
                SelectionSession(id="anon-merge-one", access_token_hash="x", store_id=1, customer_id=anonymous.id, status="draft", items=[], diy_preferences={}),
                SelectionSession(id="anon-merge-two", access_token_hash="x", store_id=1, customer_id=anonymous.id, status="submitted", items=[], diy_preferences={}),
                SelectionSession(id="anon-merge-completed", access_token_hash=hashlib.sha256(b"anon-merge-completed-token").hexdigest(), store_id=1, customer_id=anonymous.id, status="confirmed", items=[], diy_preferences={}),
            ])
            db.add(ServiceFeedback(
                store_id=1,
                selection_session_id="anon-merge-completed",
                customer_id=anonymous.id,
                rating=5,
                tags=["服务细致"],
                note="体验很好",
            ))
            db.commit()

        code = self.send_code("13500135000")["debug_code"]
        response = self.client.post("/api/v1/auth/h5/login", json={
            "phone": "13500135000", "code": code, "selection_session_id": "anon-merge-completed",
        }, headers={"X-Selection-Token": "anon-merge-completed-token"})
        self.assertEqual(response.status_code, 200, response.text)
        with self.SessionLocal() as db:
            user = db.scalar(select(User).where(User.phone == "13500135000"))
            self.assertIsNotNone(user)
            for session_id in ("anon-merge-one", "anon-merge-two", "anon-merge-completed"):
                self.assertEqual(db.get(SelectionSession, session_id).customer_id, user.id)
            self.assertEqual(db.scalar(select(BrowserInstance).where(BrowserInstance.token_hash == "merge-browser-token")).customer_id, user.id)
            feedback = db.scalar(select(ServiceFeedback).where(ServiceFeedback.selection_session_id == "anon-merge-completed"))
            self.assertEqual(feedback.customer_id, user.id)


    def test_phone_login_merges_anonymous_coupons_and_orders(self):
        session_id = "h5-auth-merge-extras"
        with self.SessionLocal() as db:
            anonymous = User(openid="anon_merge_extras")
            db.add(anonymous)
            db.flush()
            tpl = CouponTemplate(name="合并测试券", code="merge-tpl", coupon_type="amount", amount_cents=500, min_spend_cents=0, status="published", validity_days=7)
            db.add(tpl)
            db.flush()
            db.add(UserCoupon(user_id=anonymous.id, template_id=tpl.id, status="unused"))
            db.add(Order(
                order_no="HXYMERGEEXTRA1", order_type="service", user_id=anonymous.id,
                store_id=1, items=[], total_amount_cents=9900, pay_amount_cents=9900,
                status="completed", pay_status="paid",
            ))
            db.add(SelectionSession(
                id=session_id,
                access_token_hash=hashlib.sha256(b"merge-extras-token").hexdigest(),
                store_id=1,
                customer_id=anonymous.id,
                items=[],
                diy_preferences={},
            ))
            db.commit()

        code = self.send_code("13400134000")["debug_code"]
        response = self.client.post("/api/v1/auth/h5/login", json={
            "phone": "13400134000", "code": code, "selection_session_id": session_id,
        }, headers={"X-Selection-Token": "merge-extras-token"})
        self.assertEqual(response.status_code, 200, response.text)
        with self.SessionLocal() as db:
            user = db.scalar(select(User).where(User.phone == "13400134000"))
            coupon = db.scalar(select(UserCoupon).where(UserCoupon.template_id == tpl.id))
            self.assertEqual(coupon.user_id, user.id)
            order = db.scalar(select(Order).where(Order.order_no == "HXYMERGEEXTRA1"))
            self.assertEqual(order.user_id, user.id)


if __name__ == "__main__":
    unittest.main()
