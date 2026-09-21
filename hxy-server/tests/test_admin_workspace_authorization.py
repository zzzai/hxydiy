import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import hash_password
from app.db.session import Base, get_db
from app.domain.staff_workspaces import create_scoped_token
from app.main import app
from app.models import Staff, StaffScopeAssignment, Store


class AdminWorkspaceAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        cls.SessionLocal = sessionmaker(bind=cls.engine, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            first = Store(store_code="workspace-first", name="第一门店", address="测试")
            second = Store(store_code="workspace-second", name="第二门店", address="测试")
            db.add_all([first, second])
            db.flush()
            single = Staff(
                username="workspace-single", password_hash=hash_password("workspace-password"),
                name="单门店店长", role="manager", store_id=first.id, status="active",
            )
            multiple = Staff(
                username="workspace-multiple", password_hash=hash_password("workspace-password"),
                name="多门店店长", role="manager", store_id=first.id, status="active",
            )
            no_scope = Staff(
                username="workspace-none", password_hash=hash_password("workspace-password"),
                name="无授权员工", role="staff", store_id=first.id, status="active",
            )
            other = Staff(
                username="workspace-other", password_hash=hash_password("workspace-password"),
                name="其他员工", role="staff", store_id=second.id, status="active",
            )
            brand_admin = Staff(
                username="workspace-brand-admin", password_hash=hash_password("workspace-password"),
                name="品牌管理员", role="admin", store_id=None, status="active",
            )
            hq_operator = Staff(
                username="workspace-hq-operator", password_hash=hash_password("workspace-password"),
                name="总部运营", role="staff", store_id=None, status="active",
            )
            db.add_all([single, multiple, no_scope, other, brand_admin, hq_operator])
            db.flush()
            grants = [
                StaffScopeAssignment(staff_id=single.id, role="store_manager", scope_type="store", scope_id=first.id),
                StaffScopeAssignment(staff_id=multiple.id, role="store_manager", scope_type="store", scope_id=first.id),
                StaffScopeAssignment(staff_id=multiple.id, role="store_manager", scope_type="store", scope_id=second.id),
                StaffScopeAssignment(staff_id=other.id, role="store_staff", scope_type="store", scope_id=second.id),
                StaffScopeAssignment(staff_id=brand_admin.id, role="brand_admin", scope_type="brand", scope_id=None),
                StaffScopeAssignment(staff_id=hq_operator.id, role="hq_operator", scope_type="brand", scope_id=None),
            ]
            db.add_all(grants)
            db.commit()
            cls.single_id = single.id
            cls.multiple_id = multiple.id
            cls.other_assignment_id = grants[3].id
            cls.no_scope_id = no_scope.id
            cls.first_store_id = first.id
            cls.brand_admin_id = brand_admin.id
            cls.hq_operator_id = hq_operator.id

        def override_get_db():
            with cls.SessionLocal() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def login(self, username: str):
        return self.client.post(
            "/api/v1/admin/login",
            json={"username": username, "password": "workspace-password"},
        )

    def scoped_headers(self, staff_id: int) -> dict[str, str]:
        with self.SessionLocal() as db:
            staff = db.get(Staff, staff_id)
            assignment = db.query(StaffScopeAssignment).filter_by(staff_id=staff_id, status="active").first()
            token = create_scoped_token(staff, assignment)
        return {"Authorization": f"Bearer {token}"}

    def test_brand_admin_manages_grants_with_audit_context(self):
        created = self.client.post(
            f"/api/v1/admin/v2/staff/accounts/{self.no_scope_id}/assignments",
            headers=self.scoped_headers(self.brand_admin_id),
            json={"role": "store_staff", "scope_type": "store", "scope_id": self.first_store_id},
        )
        self.assertEqual(created.status_code, 201, created.text)
        duplicate = self.client.post(
            f"/api/v1/admin/v2/staff/accounts/{self.no_scope_id}/assignments",
            headers=self.scoped_headers(self.brand_admin_id),
            json={"role": "store_staff", "scope_type": "store", "scope_id": self.first_store_id},
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        with self.SessionLocal() as db:
            from app.models import AuditLog
            audit = db.query(AuditLog).filter_by(action="create_staff_scope_assignment").order_by(AuditLog.id.desc()).first()
            self.assertEqual(audit.assignment_id, db.query(StaffScopeAssignment).filter_by(staff_id=self.brand_admin_id).one().id)
            self.assertEqual(audit.actor_role, "brand_admin")
            self.assertEqual(audit.detail["target_staff_id"], self.no_scope_id)
            created_assignment = db.get(StaffScopeAssignment, created.json()["id"])
            created_assignment.status = "disabled"
            db.commit()

    def test_hq_operator_cannot_manage_brand_admin_grants(self):
        response = self.client.post(
            f"/api/v1/admin/v2/staff/accounts/{self.no_scope_id}/assignments",
            headers=self.scoped_headers(self.hq_operator_id),
            json={"role": "brand_admin", "scope_type": "brand", "scope_id": None},
        )
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "ASSIGNMENT_MANAGEMENT_FORBIDDEN")

    def test_last_brand_admin_cannot_be_disabled(self):
        with self.SessionLocal() as db:
            assignment = db.query(StaffScopeAssignment).filter_by(staff_id=self.brand_admin_id).one()
        response = self.client.patch(
            f"/api/v1/admin/v2/staff/accounts/{self.brand_admin_id}/assignments/{assignment.id}",
            headers=self.scoped_headers(self.brand_admin_id),
            json={"status": "disabled"},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "LAST_BRAND_ADMIN_REQUIRED")

    def test_single_workspace_login_returns_scoped_token(self):
        response = self.login("workspace-single")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["workspaces"]), 1)
        self.assertEqual(body["staff"]["role"], "store_manager")
        protected = self.client.get(
            "/api/v1/admin/today-appointments",
            headers={"Authorization": f"Bearer {body['token']}"},
        )
        self.assertEqual(protected.status_code, 200, protected.text)

    def test_openapi_describes_workspace_requests_responses_and_bearer_auth(self):
        document = self.client.get("/api/v1/openapi.json").json()
        login = document["paths"]["/api/v1/admin/login"]["post"]
        select_workspace = document["paths"]["/api/v1/admin/workspaces/select"]["post"]
        self.assertIn("StaffLoginRequest", login["requestBody"]["content"]["application/json"]["schema"]["$ref"])
        self.assertIn("StaffLoginResponse", login["responses"]["200"]["content"]["application/json"]["schema"]["$ref"])
        self.assertIn("ApiErrorResponse", login["responses"]["401"]["content"]["application/json"]["schema"]["$ref"])
        self.assertEqual(select_workspace["security"], [{"StaffBearer": []}])
        self.assertFalse(any(item.get("name", "").lower() == "authorization" for item in select_workspace.get("parameters", [])))

    def test_multiple_workspaces_require_explicit_selection(self):
        response = self.login("workspace-multiple")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["workspaces"]), 2)
        rejected = self.client.get(
            "/api/v1/admin/today-appointments",
            headers={"Authorization": f"Bearer {body['token']}"},
        )
        self.assertEqual(rejected.status_code, 401, rejected.text)
        selected = self.client.post(
            "/api/v1/admin/workspaces/select",
            headers={"Authorization": f"Bearer {body['selector_token']}"},
            json={"assignment_id": body["workspaces"][1]["assignment_id"]},
        )
        self.assertEqual(selected.status_code, 200, selected.text)
        self.assertEqual(selected.json()["workspace"]["scope_name"], "第二门店")

    def test_selector_cannot_select_another_staff_assignment(self):
        body = self.login("workspace-multiple").json()
        response = self.client.post(
            "/api/v1/admin/workspaces/select",
            headers={"Authorization": f"Bearer {body['selector_token']}"},
            json={"assignment_id": self.other_assignment_id},
        )
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "WORKSPACE_ACCESS_DENIED")

    def test_account_without_active_assignment_cannot_login(self):
        response = self.login("workspace-none")
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "STAFF_WORKSPACE_REQUIRED")

    def test_disabling_assignment_revokes_scoped_token(self):
        with self.SessionLocal() as db:
            assignment = db.query(StaffScopeAssignment).filter_by(staff_id=self.single_id).one()
            staff = db.get(Staff, self.single_id)
            token = create_scoped_token(staff, assignment)
            assignment.status = "disabled"
            db.commit()
        response = self.client.get(
            "/api/v1/admin/today-appointments",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(response.json()["detail"]["code"], "STAFF_ASSIGNMENT_REVOKED")
        with self.SessionLocal() as db:
            assignment = db.query(StaffScopeAssignment).filter_by(staff_id=self.single_id).one()
            assignment.status = "active"
            db.commit()
