import hashlib
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models import SelectionSession, User


class CustomerProfileApiTests(unittest.TestCase):
    """个人中心：按 JWT 列出"我的选单"。"""

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

    def _auth(self, user_id: int) -> dict:
        return {"Authorization": f"Bearer {create_access_token(str(user_id), 'openid-x')}"}

    def test_mine_requires_login(self):
        response = self.client.get("/api/v1/selection-sessions/mine")
        self.assertEqual(response.status_code, 401)

    def test_mine_returns_only_own_sessions_latest_first(self):
        with self.SessionLocal() as db:
            alice = User(openid="alice-profile", phone="13800138000")
            bob = User(openid="bob-profile", phone="13900139000")
            db.add_all([alice, bob])
            db.flush()
            db.add_all([
                SelectionSession(id="alice-new", access_token_hash="x", store_id=1, customer_id=alice.id, status="submitted", items=[], diy_preferences={}),
                SelectionSession(id="alice-old", access_token_hash="x", store_id=1, customer_id=alice.id, status="draft", items=[], diy_preferences={}),
                SelectionSession(id="bob-one", access_token_hash="x", store_id=1, customer_id=bob.id, status="submitted", items=[], diy_preferences={}),
            ])
            db.commit()
            alice_id, bob_id = alice.id, bob.id

        response = self.client.get("/api/v1/selection-sessions/mine", headers=self._auth(alice_id))
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual([item["id"] for item in items], ["alice-new", "alice-old"])
        self.assertEqual(items[0]["status"], "submitted")
        self.assertIn("created_at", items[0])

    def test_mine_filters_by_status(self):
        with self.SessionLocal() as db:
            user = User(openid="carol-profile", phone="13700137000")
            db.add(user)
            db.flush()
            db.add_all([
                SelectionSession(id="carol-draft", access_token_hash="x", store_id=1, customer_id=user.id, status="draft", items=[], diy_preferences={}),
                SelectionSession(id="carol-confirmed", access_token_hash="x", store_id=1, customer_id=user.id, status="confirmed", items=[], diy_preferences={}),
            ])
            db.commit()
            user_id = user.id

        response = self.client.get("/api/v1/selection-sessions/mine?status=confirmed", headers=self._auth(user_id))
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["items"]]
        self.assertEqual(ids, ["carol-confirmed"])


if __name__ == "__main__":
    unittest.main()
