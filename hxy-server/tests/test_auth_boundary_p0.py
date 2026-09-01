import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models import Staff, Store, User


class AuthBoundaryP0Tests(unittest.TestCase):
    """顾客与员工令牌必须保持身份域隔离。"""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(
            bind=cls.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        Base.metadata.create_all(cls.engine)

        with cls.SessionLocal() as db:
            store = Store(
                store_code="auth-boundary-store",
                name="鉴权边界测试门店",
                address="测试地址",
                status="open",
            )
            db.add(store)
            db.flush()
            user = User(openid="auth-boundary-user", phone="13800000001")
            staff = Staff(
                username="auth-boundary-admin",
                password_hash=hash_password("test-password"),
                name="鉴权测试管理员",
                role="admin",
                store_id=store.id,
                status="active",
            )
            db.add_all([user, staff])
            db.flush()
            cls.user_id = user.id
            cls.staff_id = staff.id
            db.commit()

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

    def test_customer_token_cannot_access_admin_endpoint_when_ids_overlap(self):
        self.assertEqual(self.user_id, self.staff_id)
        token = create_access_token(str(self.user_id), "auth-boundary-user")

        response = self.client.get(
            "/api/v1/admin/stats",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 401, response.text)

    def test_staff_token_can_still_access_admin_endpoint(self):
        token = create_staff_token(self.staff_id, "admin")

        response = self.client.get(
            "/api/v1/admin/stats",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200, response.text)

    def test_staff_token_cannot_access_customer_endpoint_when_ids_overlap(self):
        self.assertEqual(self.user_id, self.staff_id)
        token = create_staff_token(self.staff_id, "admin")

        response = self.client.get(
            "/api/v1/orders",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 401, response.text)


if __name__ == "__main__":
    unittest.main()
