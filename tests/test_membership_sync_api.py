import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app
from app.models import PriceBook, Project, SelectionSession, Store, User


class MembershipSyncApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            store = Store(store_code="membership-store", name="会员同步测试门店", address="测试地址")
            db.add(store)
            db.flush()
            foot_bath = Project(store_id=store.id, code="hxy-qiqing-30", category="bath", name="草本泡脚", publication_status="published")
            local = Project(store_id=store.id, code="hxy-jubu-30", category="local-strength", name="局部调理", publication_status="published")
            db.add_all([foot_bath, local])
            db.flush()
            for project, prices in (
                (foot_bath, {"store": 3990, "group": 2990, "member": 2990}),
                (local, {"store": 6900, "group": 5900, "member": 4900}),
            ):
                db.add_all([
                    PriceBook(project_id=project.id, price_type=price_type, amount_cents=amount)
                    for price_type, amount in prices.items()
                ])
            db.commit()
            cls.store_id = store.id
            cls.foot_bath_id = foot_bath.id
            cls.local_id = local.id

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

    def test_external_membership_sync_is_secret_protected_and_is_used_by_phone_login(self):
        with patch.object(settings, "third_party_membership_sync_key", "sync-test-key"):
            blocked = self.client.post("/api/v1/integrations/memberships/sync", json={
                "phone": "13600136000", "is_member": True,
            })
            self.assertEqual(blocked.status_code, 401)

            synced = self.client.post(
                "/api/v1/integrations/memberships/sync",
                headers={"X-Membership-Sync-Key": "sync-test-key"},
                json={"phone": "13600136000", "is_member": True, "member_type": "annual"},
            )
            self.assertEqual(synced.status_code, 200, synced.text)
            self.assertTrue(synced.json()["is_member"])

            code = self.client.post("/api/v1/auth/h5/send-code", json={"phone": "13600136000"}).json()["debug_code"]
            login = self.client.post("/api/v1/auth/h5/login", json={"phone": "13600136000", "code": code})
            self.assertEqual(login.status_code, 200, login.text)
            self.assertTrue(login.json()["user"]["is_member"])
            self.assertEqual(login.json()["user"]["member_type"], "annual")

    def test_phone_login_reprices_the_bound_draft_selection_using_synced_membership(self):
        created = self.client.post("/api/v1/selection-sessions", json={"store_id": self.store_id})
        self.assertEqual(created.status_code, 200)
        session_id = created.json()["session"]["id"]
        selection_token = created.json()["access_token"]
        saved = self.client.patch(
            f"/api/v1/selection-sessions/{session_id}",
            headers={"X-Selection-Token": selection_token},
            json={"items": [
                {"project_id": self.foot_bath_id},
                {"project_id": self.local_id, "diy_preferences": ["肩颈"]},
                {"project_id": self.local_id, "diy_preferences": ["腰臀"]},
            ]},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["pricing_snapshot"]["applied_price_type"], "store")

        with patch.object(settings, "third_party_membership_sync_key", "sync-test-key"):
            self.client.post(
                "/api/v1/integrations/memberships/sync",
                headers={"X-Membership-Sync-Key": "sync-test-key"},
                json={"phone": "13700137000", "is_member": True, "member_type": "annual"},
            )
        code = self.client.post("/api/v1/auth/h5/send-code", json={"phone": "13700137000"}).json()["debug_code"]
        login = self.client.post("/api/v1/auth/h5/login", json={
            "phone": "13700137000", "code": code, "selection_session_id": session_id,
        }, headers={"X-Selection-Token": selection_token})
        self.assertEqual(login.status_code, 200, login.text)

        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            self.assertEqual(session.pricing_snapshot["applied_price_type"], "member")
            self.assertEqual(session.pricing_snapshot["payable_total_cents"], 9800)
            user = db.scalar(select(User).where(User.phone == "13700137000"))
            self.assertTrue(user.is_member)


if __name__ == "__main__":
    unittest.main()
