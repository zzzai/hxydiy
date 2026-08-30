import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.api.admin_v2 import MembershipUpdateIn, set_user_membership
from app.db.session import Base, get_db
from app.main import app
from app.models import MembershipBenefitGrant, Order, Staff, Store, User


class AdminMembershipTests(unittest.TestCase):
    """店长在管理端设置/取消用户会员身份。"""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            store = Store(store_code="membership-store", name="会员门店", address="测试地址")
            staff = Staff(
                username="membership-admin", name="店长", role="admin", status="active",
                password_hash=hash_password("pass"), store_id=None,
            )
            db.add_all([store, staff])
            db.flush()
            staff.store_id = store.id
            customer = User(openid="membership-customer", phone="13800138000")
            db.add(customer)
            db.flush()
            # 用户列表按门店订单关联；顾客须有本店订单才能在列表中被店长操作。
            db.add(Order(
                order_no="HXYMEMBERSHIP001", order_type="service", user_id=customer.id,
                store_id=store.id, items=[], total_amount_cents=9900,
                pay_amount_cents=9900, status="completed", pay_status="paid",
            ))
            db.commit()
            cls.store_id = store.id
            cls.staff_id = staff.id
            cls.customer_id = customer.id

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        cls.headers = {"Authorization": f"Bearer {create_staff_token(cls.staff_id, 'admin')}"}

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def test_set_member_true_and_false(self):
        response = self.client.patch(
            f"/api/v1/admin/v2/users/{self.customer_id}/membership",
            headers=self.headers, json=self._annual_payload("base-customer-cycle"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["is_member"])
        with self.SessionLocal() as db:
            user = db.get(User, self.customer_id)
            self.assertTrue(user.is_member)
            self.assertEqual(user.member_type, "annual")

        response = self.client.patch(
            f"/api/v1/admin/v2/users/{self.customer_id}/membership",
            headers=self.headers, json={"is_member": False},
        )
        self.assertEqual(response.status_code, 200)
        with self.SessionLocal() as db:
            user = db.get(User, self.customer_id)
            self.assertFalse(user.is_member)
            self.assertIsNone(user.member_type)

    def test_setting_same_annual_membership_twice_issues_one_gift(self):
        with self.SessionLocal() as db:
            customer = User(openid="annual-repeat-customer", phone="13500135000")
            db.add(customer)
            db.flush()
            db.add(Order(
                order_no="HXYANNUALREPEAT001", order_type="service", user_id=customer.id,
                store_id=self.store_id, items=[], total_amount_cents=9900,
                pay_amount_cents=9900, status="completed", pay_status="paid",
            ))
            db.commit()
            customer_id = customer.id

        first = self.client.patch(
            f"/api/v1/admin/v2/users/{customer_id}/membership",
            json=self._annual_payload("annual-repeat-cycle"),
            headers=self.headers,
        )
        second = self.client.patch(
            f"/api/v1/admin/v2/users/{customer_id}/membership",
            json=self._annual_payload("annual-repeat-cycle"),
            headers=self.headers,
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        with self.SessionLocal() as db:
            count = db.scalar(select(func.count()).select_from(MembershipBenefitGrant).where(
                MembershipBenefitGrant.user_id == customer_id,
                MembershipBenefitGrant.benefit_type == "annual_project_gift",
            ))
            grant = db.scalar(select(MembershipBenefitGrant).where(
                MembershipBenefitGrant.user_id == customer_id,
            ))
            user = db.get(User, customer_id)

        self.assertEqual(count, 1)
        self.assertEqual(grant.status, "available")
        self.assertIsNotNone(grant.membership_started_at)
        self.assertTrue(user.is_member)
        self.assertEqual(user.member_type, "annual")

    def test_locked_membership_query_refreshes_preloaded_user_before_issuing_grant(self):
        with self.SessionLocal() as db:
            customer = User(openid="annual-stale-customer", phone="13400134000")
            db.add(customer)
            db.flush()
            db.add(Order(
                order_no="HXYANNUALSTALE001", order_type="service", user_id=customer.id,
                store_id=self.store_id, items=[], total_amount_cents=9900,
                pay_amount_cents=9900, status="completed", pay_status="paid",
            ))
            db.commit()
            customer_id = customer.id

        db1 = self.SessionLocal()
        try:
            preloaded = db1.get(User, customer_id)
            self.assertIsNone(preloaded.member_type)
            with self.SessionLocal() as db2:
                user = db2.get(User, customer_id)
                user.is_member = True
                user.member_type = "annual"
                user.member_expire_at = datetime(2027, 8, 1, tzinfo=timezone.utc)
                user.annual_membership_cycle_id = "stale-cycle"
                db2.add(MembershipBenefitGrant(
                    user_id=customer_id,
                    benefit_type="annual_project_gift",
                    membership_cycle_id="stale-cycle",
                    membership_started_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                    status="available",
                ))
                db2.commit()

            set_user_membership(
                customer_id,
                MembershipUpdateIn(**self._annual_payload("stale-cycle")),
                db=db1,
                authorization=self.headers["Authorization"],
            )
        finally:
            db1.close()

        with self.SessionLocal() as db:
            count = db.scalar(select(func.count()).select_from(MembershipBenefitGrant).where(
                MembershipBenefitGrant.user_id == customer_id,
                MembershipBenefitGrant.benefit_type == "annual_project_gift",
            ))

        self.assertEqual(count, 1)

    def test_unknown_membership_type_is_rejected(self):
        response = self.client.patch(
            f"/api/v1/admin/v2/users/{self.customer_id}/membership",
            headers=self.headers,
            json={"member_type": "vip"},
        )

        self.assertEqual(response.status_code, 422)

    def test_membership_requires_admin_token(self):
        response = self.client.patch(
            f"/api/v1/admin/v2/users/{self.customer_id}/membership",
            json=self._annual_payload("unauthenticated-cycle"),
        )
        self.assertEqual(response.status_code, 401)

    def test_pure_diy_customer_without_order_can_be_set_member(self):
        # DIY 选单顾客没有订单，也应能出现在用户列表并被店长设置会员。
        from app.models import SelectionSession
        with self.SessionLocal() as db:
            customer = User(openid="diy-only-customer", phone="13700137000")
            db.add(customer)
            db.flush()
            db.add(SelectionSession(
                id="diy-only-session", access_token_hash="x", store_id=self.store_id,
                customer_id=customer.id, status="submitted", items=[], diy_preferences={},
            ))
            db.commit()
            customer_id = customer.id

        response = self.client.patch(
            f"/api/v1/admin/v2/users/{customer_id}/membership",
            headers=self.headers, json=self._annual_payload("diy-only-cycle"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        with self.SessionLocal() as db:
            self.assertTrue(db.get(User, customer_id).is_member)

    def test_user_list_searches_by_phone_and_filters_members(self):
        with self.SessionLocal() as db:
            customer = User(openid="phone-search-customer", phone="17601019659", is_member=True, member_type="annual")
            db.add(customer)
            db.flush()
            db.add(Order(
                order_no="HXYPHONESEARCH001", order_type="service", user_id=customer.id,
                store_id=self.store_id, items=[], total_amount_cents=9900,
                pay_amount_cents=9900, status="completed", pay_status="paid",
            ))
            db.commit()

        response = self.client.get(
            "/api/v1/admin/v2/users",
            headers=self.headers,
            params={"search": "17601019659", "is_member": "true"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["items"][0]["phone_tail"], "9659")

    def test_member_without_order_is_visible_and_phone_is_masked(self):
        with self.SessionLocal() as db:
            customer = User(
                openid="member-without-order",
                phone="15936692222",
                is_member=True,
                member_type="annual",
                membership_store_id=self.store_id,
            )
            db.add(customer)
            db.commit()

        response = self.client.get(
            "/api/v1/admin/v2/users",
            headers=self.headers,
            params={"search": "15936692222", "is_member": "true"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["items"][0]["phone_masked"], "159****2222")

    def test_member_from_another_store_is_not_visible_without_local_activity(self):
        with self.SessionLocal() as db:
            other_store = Store(
                store_code="membership-other-store",
                name="其他会员门店",
                address="其他地址",
            )
            db.add(other_store)
            db.flush()
            customer = User(
                openid="other-store-member",
                phone="15800158000",
                is_member=True,
                member_type="annual",
                membership_store_id=other_store.id,
            )
            db.add(customer)
            db.commit()

        response = self.client.get(
            "/api/v1/admin/v2/users",
            headers=self.headers,
            params={"search": "15800158000"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 0)

    def test_setting_member_refreshes_open_selection_pricing(self):
        from app.models import PriceBook, Project, SelectionSession
        with self.SessionLocal() as db:
            customer = User(openid="refresh-customer", phone="13600136000")
            foot = Project(
                store_id=self.store_id, code="hxy-refresh-foot", category="bath",
                name="泡脚", publication_status="published",
            )
            db.add_all([customer, foot])
            db.flush()
            db.add_all([
                PriceBook(project_id=foot.id, price_type="store", amount_cents=3990),
                PriceBook(project_id=foot.id, price_type="member", amount_cents=2990),
            ])
            db.flush()
            db.add(SelectionSession(
                id="refresh-session", access_token_hash="x", store_id=self.store_id,
                customer_id=customer.id, status="draft",
                items=[{"project_id": foot.id, "quantity": 1, "chargeable": True, "item_type": "service"}],
                diy_preferences={},
            ))
            db.commit()
            customer_id = customer.id
            session_id = "refresh-session"

        # 未设会员前按门店价
        with self.SessionLocal() as db:
            self.assertEqual(db.get(SelectionSession, session_id).member_total_cents, 0)

        response = self.client.patch(
            f"/api/v1/admin/v2/users/{customer_id}/membership",
            headers=self.headers, json=self._annual_payload("refresh-cycle"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            self.assertGreater(session.member_total_cents, 0)

    def test_annual_cycle_is_strict_idempotent_and_uses_expiry(self):
        with self.SessionLocal() as db:
            customer = User(openid="annual-cycle-customer", phone="13300135000")
            db.add(customer)
            db.flush()
            db.add(Order(
                order_no="HXYANNUALCYCLE001", order_type="service", user_id=customer.id,
                store_id=self.store_id, items=[], total_amount_cents=9900,
                pay_amount_cents=9900, status="completed", pay_status="paid",
            ))
            db.commit()
            customer_id = customer.id

        malformed = self.client.patch(
            f"/api/v1/admin/v2/users/{customer_id}/membership",
            headers=self.headers,
            json={"member_type": "annual", "cycle_id": "cycle-a", "member_started_at": "2026-08-01T00:00:00", "member_expire_at": "2027-08-01T00:00:00+00:00"},
        )
        self.assertEqual(malformed.status_code, 422, malformed.text)
        conflicting = self.client.patch(
            f"/api/v1/admin/v2/users/{customer_id}/membership",
            headers=self.headers,
            json={"member_type": "annual", "is_member": False, "cycle_id": "cycle-a", "member_started_at": "2026-08-01T00:00:00+00:00", "member_expire_at": "2027-08-01T00:00:00+00:00"},
        )
        self.assertEqual(conflicting.status_code, 422, conflicting.text)

        cycle_a = {
            "member_type": "annual",
            "cycle_id": "cycle-a",
            "member_started_at": "2026-08-01T00:00:00+00:00",
            "member_expire_at": "2027-08-01T00:00:00+00:00",
        }
        first = self.client.patch(
            f"/api/v1/admin/v2/users/{customer_id}/membership",
            headers=self.headers,
            json=cycle_a,
        )
        retry = self.client.patch(
            f"/api/v1/admin/v2/users/{customer_id}/membership",
            headers=self.headers,
            json=cycle_a,
        )
        changed_start_for_same_cycle = self.client.patch(
            f"/api/v1/admin/v2/users/{customer_id}/membership",
            headers=self.headers,
            json={
                **cycle_a,
                "member_started_at": "2026-08-02T00:00:00+00:00",
            },
        )
        cancel = self.client.patch(
            f"/api/v1/admin/v2/users/{customer_id}/membership",
            headers=self.headers,
            json={"is_member": False},
        )
        reopen = self.client.patch(
            f"/api/v1/admin/v2/users/{customer_id}/membership",
            headers=self.headers,
            json=cycle_a,
        )
        cycle_b = self.client.patch(
            f"/api/v1/admin/v2/users/{customer_id}/membership",
            headers=self.headers,
            json={
                "member_type": "annual",
                "cycle_id": "cycle-b",
                "member_started_at": "2027-08-01T00:00:00+00:00",
                "member_expire_at": "2028-08-01T00:00:00+00:00",
            },
        )
        for response in (first, retry, cancel, reopen, cycle_b):
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(changed_start_for_same_cycle.status_code, 409, changed_start_for_same_cycle.text)

        with self.SessionLocal() as db:
            grants = list(db.scalars(select(MembershipBenefitGrant).where(
                MembershipBenefitGrant.user_id == customer_id,
            ).order_by(MembershipBenefitGrant.membership_started_at)))
            user = db.get(User, customer_id)

        self.assertEqual(len(grants), 2)
        self.assertEqual([grant.membership_cycle_id for grant in grants], ["cycle-a", "cycle-b"])
        self.assertEqual(user.annual_membership_cycle_id, "cycle-b")
        self.assertEqual(user.member_expire_at.replace(tzinfo=timezone.utc), datetime(2028, 8, 1, tzinfo=timezone.utc))

    @staticmethod
    def _annual_payload(cycle_id: str) -> dict:
        return {
            "member_type": "annual",
            "cycle_id": cycle_id,
            "member_started_at": "2026-08-01T00:00:00+00:00",
            "member_expire_at": "2027-08-01T00:00:00+00:00",
        }


if __name__ == "__main__":
    unittest.main()
