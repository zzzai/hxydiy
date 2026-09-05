import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app
from app.models import CouponTemplate, Store, User, UserCoupon


class CouponClaimTests(unittest.TestCase):
    """领券限领规则：每日限领 / 总限领 / 分享券 24h 幂等。"""

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
        # 原有领券限额测试显式启用策略，默认生产配置保持暂停。
        enabled = patch.object(settings, "coupon_issuance_enabled", True)
        enabled.start()
        self.addCleanup(enabled.stop)
        import secrets
        suffix = secrets.token_hex(4).upper()
        with self.SessionLocal() as db:
            db.add(Store(store_code=f"store-{suffix}", name="测试门店", address="测试地址"))
            db.commit()
            self.user = User(openid=f"claim-user-{suffix}", phone=f"138{suffix[:8]}")
            db.add(self.user)
            db.flush()
            self.daily = CouponTemplate(
                name="每日券", code=f"daily-{suffix}", coupon_type="amount",
                amount_cents=500, min_spend_cents=0, status="published",
                validity_days=7, is_claimable=True, daily_claimable=True, claim_limit=0,
            )
            self.limited = CouponTemplate(
                name="限领券", code=f"limited-{suffix}", coupon_type="amount",
                amount_cents=500, min_spend_cents=0, status="published",
                validity_days=7, is_claimable=True, daily_claimable=False, claim_limit=1,
            )
            db.add_all([self.daily, self.limited])
            db.flush()
            self.user_id = self.user.id
            self.daily_id, self.limited_id = self.daily.id, self.limited.id
            db.commit()

    def _auth(self):
        return {"Authorization": f"Bearer {create_access_token(str(self.user_id), 'openid-x')}"}

    def test_paused_policy_blocks_all_new_issuance_and_preserves_existing_coupon(self):
        from app.api.auth import grant_new_user_coupons
        from app.api.orders import _grant_inviter_reward
        from app.api.selections import _saving_hint

        with self.SessionLocal() as db:
            template = db.get(CouponTemplate, self.daily_id)
            template.auto_grant_new_user = True
            db.add(UserCoupon(user_id=self.user_id, template_id=self.limited_id, status="unused"))
            db.commit()

        with patch.object(settings, "coupon_issuance_enabled", False):
            for headers in ({}, self._auth()):
                response = self.client.get("/api/v1/coupons/templates", headers=headers)
                self.assertEqual(response.json(), {"items": [], "total": 0})
            response = self.client.post("/api/v1/coupons/claim", headers=self._auth(), json={"template_id": self.daily_id})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"]["code"], "COUPON_ISSUANCE_PAUSED")
            response = self.client.post("/api/v1/coupons/claim-share", headers=self._auth())
            self.assertFalse(response.json()["granted"])
            with self.SessionLocal() as db:
                grant_new_user_coupons(db, self.user_id)
                self.assertFalse(_grant_inviter_reward(db, self.user_id))
                pricing = {"payable_total_cents": 1990, "member_total_cents": 1990, "store_total_cents": 1990}
                self.assertIsNone(_saving_hint(db, 1, pricing, None))
                pricing["member_total_cents"] = 990
                self.assertEqual(_saving_hint(db, 1, pricing, None)["kind"], "member")
                db.commit()
                self.assertEqual(db.scalar(select(func.count()).select_from(UserCoupon).where(UserCoupon.user_id == self.user_id)), 1)
            response = self.client.get("/api/v1/coupons", headers=self._auth())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["items"]), 1)

    def test_daily_claimable_coupon_second_claim_same_day_rejected(self):
        first = self.client.post("/api/v1/coupons/claim", headers=self._auth(), json={"template_id": self.daily_id})
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post("/api/v1/coupons/claim", headers=self._auth(), json={"template_id": self.daily_id})
        self.assertEqual(second.status_code, 400)
        self.assertIn("今日", second.json()["detail"])

    def test_total_claim_limit_enforced(self):
        first = self.client.post("/api/v1/coupons/claim", headers=self._auth(), json={"template_id": self.limited_id})
        self.assertEqual(first.status_code, 200)
        second = self.client.post("/api/v1/coupons/claim", headers=self._auth(), json={"template_id": self.limited_id})
        self.assertEqual(second.status_code, 400)
        self.assertIn("上限", second.json()["detail"])

    def test_member_cannot_claim_coupon(self):
        with self.SessionLocal() as db:
            db.get(User, self.user_id).is_member = True
            db.commit()
        response = self.client.post("/api/v1/coupons/claim", headers=self._auth(), json={"template_id": self.daily_id})
        self.assertEqual(response.status_code, 400)
        self.assertIn("无需领取", response.json()["detail"])

    def test_member_coupon_entry_points_return_no_claimable_promotions(self):
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.is_member = True
            template = db.get(CouponTemplate, self.daily_id)
            template.auto_apply = True
            db.commit()

        templates = self.client.get("/api/v1/coupons/templates", headers=self._auth())
        self.assertEqual(templates.status_code, 200, templates.text)
        self.assertEqual(templates.json(), {"items": [], "total": 0})

        activity = self.client.get("/api/v1/coupons/activity", headers=self._auth())
        self.assertEqual(activity.status_code, 200, activity.text)
        self.assertEqual(activity.json(), {"items": [], "total": 0})


if __name__ == "__main__":
    unittest.main()
