import hashlib
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models import MembershipCode, PositionOccupancy, SelectionSession, Staff, Store, User
from app.models.operations import Room, Technician


class TestMembershipVerification:
    def setup_method(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            store = Store(store_code="member-code-store", name="会员码测试店", address="测试地址")
            other = Store(store_code="member-code-other", name="另一门店", address="测试地址")
            db.add_all([store, other]); db.flush()
            member = User(openid="member_code_user", phone="13800138999", nickname="小悦", is_member=True, member_type="annual", member_expire_at=datetime.now(timezone.utc) + timedelta(days=60), customer_login_version=2, membership_store_id=store.id)
            technician = Technician(store_id=store.id, code="MEMBER-TECH", name="核验技师", status="available")
            db.add_all([member, technician]); db.flush()
            tech_staff = Staff(username="member-tech", password_hash=hash_password("pass"), name="核验技师", role="technician", status="active", store_id=store.id, technician_id=technician.id)
            manager = Staff(username="member-manager", password_hash=hash_password("pass"), name="值班店长", role="manager", status="active", store_id=store.id)
            other_manager = Staff(username="member-other", password_hash=hash_password("pass"), name="异店店长", role="manager", status="active", store_id=other.id)
            room = Room(store_id=store.id, code="SOFA-M", name="会员沙发", room_type="sofa", status="available")
            db.add_all([tech_staff, manager, other_manager, room]); db.flush()
            selection = SelectionSession(id="member-selection", access_token_hash=hashlib.sha256(b"member-selection-token").hexdigest(), store_id=store.id, status="draft", items=[], diy_preferences={})
            db.add(selection); db.flush()
            db.add(PositionOccupancy(store_id=store.id, room_id=room.id, selection_session_id=selection.id, status="held", source="diy"))
            db.commit()
            self.member_id, self.store_id, self.selection_id = member.id, store.id, selection.id
            self.tech_id, self.manager_id, self.other_manager_id = tech_staff.id, manager.id, other_manager.id
        app.dependency_overrides[get_db] = self.override_db
        self.client = TestClient(app)

    def teardown_method(self):
        self.client.close(); app.dependency_overrides.clear(); self.engine.dispose()

    def override_db(self):
        with self.SessionLocal() as db: yield db

    def customer_headers(self):
        return {"Authorization": f"Bearer {create_access_token(str(self.member_id), 'member_code_user', 2)}"}

    def test_trusted_device_issues_only_one_30_second_code(self):
        trusted = self.client.post("/api/v1/auth/h5/trusted-device/enroll", headers=self.customer_headers())
        assert trusted.status_code == 200, trusted.text
        first = self.client.post("/api/v1/auth/h5/member-code", headers=self.customer_headers())
        second = self.client.post("/api/v1/auth/h5/member-code", headers=self.customer_headers())
        assert first.status_code == second.status_code == 200
        with self.SessionLocal() as db:
            rows = list(db.scalars(select(MembershipCode).where(MembershipCode.user_id == self.member_id).order_by(MembershipCode.created_at)))
            assert [row.status for row in rows] == ["revoked", "issued"]
        assert first.json()["code_token"] != second.json()["code_token"]

    def test_untrusted_browser_cannot_issue_code(self):
        response = self.client.post("/api/v1/auth/h5/member-code", headers=self.customer_headers())
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "DEVICE_NOT_TRUSTED"

    def test_scan_reserves_code_before_binding(self):
        self.client.post("/api/v1/auth/h5/trusted-device/enroll", headers=self.customer_headers())
        issued = self.client.post("/api/v1/auth/h5/member-code", headers=self.customer_headers()).json()
        headers = {"Authorization": f"Bearer {create_staff_token(self.tech_id, 'technician')}"}
        scanned = self.client.post("/api/v1/technician/membership-verification/scan", headers=headers, json={"code_token": issued["code_token"]})
        assert scanned.status_code == 200, scanned.text
        assert scanned.json()["member"]["phone_masked"] == "138****8999"
        with self.SessionLocal() as db:
            assert db.scalar(select(MembershipCode).where(MembershipCode.user_id == self.member_id)).status == "scanned_pending"

    def test_technician_consumes_once_and_cross_store_is_rejected(self):
        self.client.post("/api/v1/auth/h5/trusted-device/enroll", headers=self.customer_headers())
        issued = self.client.post("/api/v1/auth/h5/member-code", headers=self.customer_headers()).json()
        other_headers = {"Authorization": f"Bearer {create_staff_token(self.other_manager_id, 'manager')}"}
        denied = self.client.post("/api/v1/technician/membership-verification/consume", headers=other_headers, json={"code_token": issued["code_token"], "selection_session_id": self.selection_id, "idempotency_key": "verify-cross-store"})
        assert denied.status_code == 403
        tech_headers = {"Authorization": f"Bearer {create_staff_token(self.tech_id, 'technician')}"}
        consumed = self.client.post("/api/v1/technician/membership-verification/consume", headers=tech_headers, json={"code_token": issued["code_token"], "selection_session_id": self.selection_id, "idempotency_key": "verify-member-once"})
        assert consumed.status_code == 200, consumed.text
        assert consumed.json()["member"]["phone_masked"] == "138****8999"
        same_retry = self.client.post("/api/v1/technician/membership-verification/consume", headers=tech_headers, json={"code_token": issued["code_token"], "selection_session_id": self.selection_id, "idempotency_key": "verify-member-once"})
        assert same_retry.status_code == 200
        replay = self.client.post("/api/v1/technician/membership-verification/consume", headers=tech_headers, json={"code_token": issued["code_token"], "selection_session_id": self.selection_id, "idempotency_key": "verify-member-replay"})
        assert replay.status_code == 409
        with self.SessionLocal() as db:
            selection = db.get(SelectionSession, self.selection_id)
            assert selection.customer_id == self.member_id
            assert selection.membership_verified_at is not None

    def test_store_manager_can_verify_without_technician_permissions(self):
        self.client.post("/api/v1/auth/h5/trusted-device/enroll", headers=self.customer_headers())
        issued = self.client.post("/api/v1/auth/h5/member-code", headers=self.customer_headers()).json()
        headers = {"Authorization": f"Bearer {create_staff_token(self.manager_id, 'manager')}"}
        consumed = self.client.post("/api/v1/technician/membership-verification/consume", headers=headers, json={"code_token": issued["code_token"], "selection_session_id": self.selection_id, "idempotency_key": "verify-by-manager"})
        assert consumed.status_code == 200, consumed.text
        service_action = self.client.post("/api/v1/technician/occupancies/1/confirm", headers=headers, json={"idempotency_key": "manager-cannot-confirm"})
        assert service_action.status_code == 403

    def test_manager_revoke_device_also_revokes_unconsumed_codes(self):
        self.client.post("/api/v1/auth/h5/trusted-device/enroll", headers=self.customer_headers())
        self.client.post("/api/v1/auth/h5/member-code", headers=self.customer_headers())
        headers = {"Authorization": f"Bearer {create_staff_token(self.manager_id, 'manager')}"}
        response = self.client.post(f"/api/v1/admin/v2/users/{self.member_id}/trusted-device/revoke", headers=headers, json={"reason": "顾客申请换机"})
        assert response.status_code == 200, response.text
        with self.SessionLocal() as db:
            assert db.scalar(select(MembershipCode).where(MembershipCode.user_id == self.member_id)).status == "revoked"
            assert db.get(User, self.member_id).customer_login_version == 3
