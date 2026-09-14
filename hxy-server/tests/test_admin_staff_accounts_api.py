import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, verify_password
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, Staff, Store


class AdminStaffAccountContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        cls.SessionLocal = sessionmaker(bind=cls.engine, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            store = Store(store_code="staff-contract", name="员工测试店", address="测试")
            other_store = Store(store_code="staff-contract-other", name="另一员工测试店", address="测试")
            db.add_all([store, other_store])
            db.flush()
            headquarters = Staff(
                username="staff-contract-hq", password_hash="unused", name="总部管理员",
                role="admin", store_id=None, status="active",
            )
            manager = Staff(
                username="staff-contract-manager", password_hash="unused", name="测试店长",
                role="manager", store_id=store.id, status="active",
            )
            employee = Staff(
                username="staff-contract-employee", password_hash="unused", name="测试员工",
                role="staff", store_id=store.id, status="active",
            )
            disabled = Staff(
                username="staff-contract-disabled", password_hash="unused", name="停用员工",
                role="staff", store_id=store.id, status="disabled",
            )
            technician = Staff(
                username="staff-contract-technician", password_hash="unused", name="技师账号",
                role="technician", store_id=store.id, status="active",
            )
            db.add_all([headquarters, manager, employee, disabled, technician])
            db.commit()
            cls.store_id = store.id
            cls.other_store_id = other_store.id
            cls.headquarters_id = headquarters.id
            cls.manager_id = manager.id
            cls.employee_id = employee.id
            cls.technician_id = technician.id

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

    def headers_for(self, staff_id: int) -> dict[str, str]:
        with self.SessionLocal() as db:
            staff = db.get(Staff, staff_id)
            token = create_staff_token(staff.id, staff.role, staff.credentials_version)
        return {"Authorization": f"Bearer {token}"}

    def test_headquarters_creates_store_staff_with_audited_login_credentials(self):
        response = self.client.post(
            "/api/v1/admin/v2/staff",
            headers=self.headers_for(self.headquarters_id),
            json={
                "username": "front-desk-01",
                "password": "safe-password-01",
                "name": "前台员工",
                "role": "staff",
                "store_id": self.store_id,
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["username"], "front-desk-01")
        self.assertEqual(body["role"], "staff")
        self.assertEqual(body["store_id"], self.store_id)
        self.assertNotIn("password", body)
        self.assertNotIn("password_hash", body)
        with self.SessionLocal() as db:
            account = db.scalar(select(Staff).where(Staff.username == "front-desk-01"))
            self.assertIsNotNone(account)
            self.assertTrue(verify_password("safe-password-01", account.password_hash))
            audit = db.scalar(select(AuditLog).where(AuditLog.action == "create_staff_account"))
            self.assertEqual(audit.store_id, self.store_id)
            self.assertEqual(audit.detail, {"role": "staff", "store_id": self.store_id})
        login = self.client.post("/api/v1/admin/login", json={"username": "front-desk-01", "password": "safe-password-01"})
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["staff"]["role"], "staff")

    def test_headquarters_lists_only_managed_store_accounts(self):
        response = self.client.get(
            "/api/v1/admin/v2/staff?page=1&page_size=20",
            headers=self.headers_for(self.headquarters_id),
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        usernames = {account["username"] for account in body["items"]}
        self.assertIn("staff-contract-manager", usernames)
        self.assertIn("staff-contract-employee", usernames)
        self.assertIn("staff-contract-disabled", usernames)
        self.assertNotIn("staff-contract-hq", usernames)
        self.assertNotIn("staff-contract-technician", usernames)
        self.assertEqual(body["total"], len(body["items"]))
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["page_size"], 20)
        self.assertTrue(all("password" not in account and "password_hash" not in account for account in body["items"]))

    def test_reassigning_staff_revokes_the_old_login_session(self):
        old_session = self.headers_for(self.employee_id)
        response = self.client.patch(
            f"/api/v1/admin/v2/staff/{self.employee_id}",
            headers=self.headers_for(self.headquarters_id),
            json={"store_id": self.other_store_id},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["store_id"], self.other_store_id)
        old_session_result = self.client.get("/api/v1/admin/v2/staff", headers=old_session)
        self.assertEqual(old_session_result.status_code, 401, old_session_result.text)
        self.assertEqual(old_session_result.json()["detail"]["code"], "STAFF_SESSION_REVOKED")
        with self.SessionLocal() as db:
            audit = db.scalar(
                select(AuditLog)
                .where(AuditLog.action == "update_staff_account")
                .order_by(AuditLog.id.desc())
            )
            self.assertEqual(audit.store_id, self.other_store_id)
            self.assertEqual(audit.detail, {
                "fields": ["store_id"],
                "store_id": self.other_store_id,
                "session_revoked": True,
            })

    def test_general_staff_api_rejects_headquarters_and_technician_accounts(self):
        for staff_id in (self.headquarters_id, self.technician_id):
            response = self.client.patch(
                f"/api/v1/admin/v2/staff/{staff_id}",
                headers=self.headers_for(self.headquarters_id),
                json={"name": "不应修改"},
            )
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(response.json()["detail"]["code"], "STAFF_ACCOUNT_MANAGED_ELSEWHERE")

    def test_store_manager_cannot_manage_staff_accounts(self):
        response = self.client.post(
            "/api/v1/admin/v2/staff",
            headers=self.headers_for(self.manager_id),
            json={
                "username": "manager-forbidden-staff",
                "password": "safe-password-02",
                "name": "越权员工",
                "role": "staff",
                "store_id": self.store_id,
            },
        )

        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "HEADQUARTERS_ADMIN_REQUIRED")
        update = self.client.patch(
            f"/api/v1/admin/v2/staff/{self.employee_id}",
            headers=self.headers_for(self.manager_id),
            json={"status": "disabled"},
        )
        self.assertEqual(update.status_code, 403, update.text)
        self.assertEqual(update.json()["detail"]["code"], "HEADQUARTERS_ADMIN_REQUIRED")


if __name__ == "__main__":
    unittest.main()
