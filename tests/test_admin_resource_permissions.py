import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import Room, ServicePositionQr, Staff, Store
from app.models.operations import Technician


class AdminResourcePermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            store = Store(store_code="resource-scope", name="资源权限店", address="测试")
            db.add(store)
            db.flush()
            existing_room = Room(
                store_id=store.id, code="resource-existing", name="已有二维码位",
                is_service_position=True, is_space_container=False,
            )
            empty_room = Room(
                store_id=store.id, code="resource-empty", name="无二维码位",
                is_service_position=True, is_space_container=False,
            )
            db.add_all([existing_room, empty_room])
            db.flush()
            technician = Technician(store_id=store.id, code="RESOURCE-TECH", name="技师", status="available")
            db.add(technician)
            db.flush()
            manager = Staff(
                username="resource-manager", password_hash=hash_password("pass"),
                name="店长", role="admin", store_id=store.id, status="active",
            )
            clerk = Staff(
                username="resource-clerk", password_hash=hash_password("pass"),
                name="技师", role="technician", technician_id=technician.id, store_id=store.id, status="active",
            )
            db.add_all([manager, clerk])
            db.flush()
            db.add_all([
                Staff(username="legacy-unbound", password_hash=hash_password("pass"), name="旧员工", role="staff", store_id=store.id, status="active"),
                Staff(username="tech-unbound", password_hash=hash_password("pass"), name="未绑定技师", role="technician", store_id=store.id, status="active"),
            ])
            db.flush()
            db.connection().exec_driver_sql("PRAGMA ignore_check_constraints = ON")
            db.connection().exec_driver_sql("INSERT INTO staff (username,password_hash,name,role,store_id,status) VALUES ('unknown-role',:pw,'未知角色','superuser',:sid,'active')", {"pw": hash_password("pass"), "sid": store.id})
            qr = ServicePositionQr(
                public_id="resource-existing-qr", store_id=store.id,
                room_id=existing_room.id, source="personal_qr", status="active",
                created_by_staff_id=manager.id,
            )
            db.add(qr)
            db.commit()
            cls.existing_room_id = existing_room.id
            cls.empty_room_id = empty_room.id
            cls.qr_id = qr.id
            cls.clerk_headers = {
                "Authorization": f"Bearer {create_staff_token(clerk.id, 'staff')}"
            }

        app.dependency_overrides[get_db] = cls._get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.pop(get_db, None)
        cls.engine.dispose()

    @classmethod
    def _get_db(cls):
        with cls.SessionLocal() as db:
            yield db

    def test_staff_can_read_existing_qr_without_mutation(self):
        response = self.client.get(
            f"/api/v1/admin/service-positions/{self.existing_room_id}/qr-link",
            headers=self.clerk_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["qr_id"], self.qr_id)

    def test_staff_cannot_create_qr_through_read_endpoint(self):
        response = self.client.get(
            f"/api/v1/admin/service-positions/{self.empty_room_id}/qr-link",
            headers=self.clerk_headers,
        )
        self.assertEqual(response.status_code, 403, response.text)
        with self.SessionLocal() as db:
            count = db.scalar(select(func.count()).select_from(ServicePositionQr).where(
                ServicePositionQr.room_id == self.empty_room_id,
            ))
        self.assertEqual(count, 0)

    def test_staff_cannot_change_regenerate_or_rebind_qr(self):
        requests = (
            ("patch", f"/api/v1/admin/service-position-qrs/{self.qr_id}", {"status": "disabled"}),
            ("post", f"/api/v1/admin/service-position-qrs/{self.qr_id}/regenerate", {"reason": "test"}),
            ("post", f"/api/v1/admin/service-position-qrs/{self.qr_id}/rebind", {"target_room_id": self.empty_room_id}),
        )
        for method, path, body in requests:
            with self.subTest(path=path):
                response = self.client.request(method, path, headers=self.clerk_headers, json=body)
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(response.json()["detail"]["code"], "MANAGER_REQUIRED")

    def test_missing_credentials_returns_structured_401_response(self):
        response = self.client.patch(
            f"/api/v1/admin/service-position-qrs/{self.qr_id}",
            json={"status": "disabled"},
        )
        self.assertEqual(response.status_code, 401, response.text)
        self.assertIsInstance(response.json()["detail"], dict)
        self.assertEqual(response.json()["detail"]["code"], "AUTHENTICATION_REQUIRED")

    def test_physical_resource_api_is_blocked_for_diy_admin(self):
        response = self.client.get("/api/v1/admin/v2/assignments", headers=self.clerk_headers)
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json()["detail"]["code"], "DIY_PHYSICAL_RESOURCE_FORBIDDEN")

    def test_login_rejects_unbound_legacy_staff(self):
        response = self.client.post("/api/v1/admin/login", json={"username": "legacy-unbound", "password": "pass"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["code"], "ROLE_MIGRATION_REQUIRED")

    def test_login_rejects_unknown_role(self):
        response = self.client.post("/api/v1/admin/login", json={"username": "unknown-role", "password": "pass"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["code"], "INVALID_STAFF_ROLE")

    def test_login_rejects_unbound_technician(self):
        response = self.client.post("/api/v1/admin/login", json={"username": "tech-unbound", "password": "pass"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["code"], "TECHNICIAN_BINDING_REQUIRED")


if __name__ == "__main__":
    unittest.main()
