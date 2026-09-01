from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.api.technician import make_invite_token, token_hash
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, Staff, Store, Technician, TechnicianInvite
from app.models.service import ServiceAssignment


class TestTechnicianAccountLifecycle:
    def setup_method(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            first = Store(store_code="lifecycle-first", name="一号店", address="测试地址")
            second = Store(store_code="lifecycle-second", name="二号店", address="测试地址")
            db.add_all([first, second])
            db.flush()
            manager = Staff(
                username="lifecycle-manager",
                password_hash=hash_password("manager-pass"),
                name="店长",
                role="admin",
                status="active",
                store_id=first.id,
            )
            technician = Technician(
                store_id=first.id, code="LIFE-TECH-1", name="小悦技师", status="available"
            )
            other_technician = Technician(
                store_id=second.id, code="LIFE-TECH-2", name="二号技师", status="available"
            )
            db.add_all([manager, technician, other_technician])
            db.commit()
            self.store_id = first.id
            self.other_store_id = second.id
            self.manager_id = manager.id
            self.technician_id = technician.id
            self.other_technician_id = other_technician.id
        app.dependency_overrides[get_db] = self._override_get_db
        self.client = TestClient(app)
        self.manager_headers = {
            "Authorization": f"Bearer {create_staff_token(self.manager_id, 'admin')}"
        }

    def teardown_method(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()

    def _override_get_db(self):
        with self.SessionLocal() as db:
            yield db

    def _staff(self):
        with self.SessionLocal() as db:
            return db.scalar(select(Staff).where(Staff.technician_id == self.technician_id))

    def test_account_columns_have_safe_defaults_and_invite_purpose_is_required(self):
        with self.SessionLocal() as db:
            staff = Staff(
                username="lifecycle-column-check",
                password_hash=hash_password("password"),
                name="字段检查",
                role="technician",
                status="invited",
                store_id=self.store_id,
                technician_id=self.technician_id,
            )
            db.add(staff)
            db.flush()
            invite = TechnicianInvite(
                store_id=self.store_id,
                technician_id=self.technician_id,
                staff_id=staff.id,
                token_hash="a" * 64,
                purpose="activate",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                created_by_staff_id=self.manager_id,
            )
            db.add(invite)
            db.commit()
            db.refresh(staff)
            assert staff.credentials_version == 1
            assert invite.purpose == "activate"

    def test_manager_can_reset_disable_restore_and_list_lifecycle_state(self):
        invited = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/invite",
            headers=self.manager_headers,
        )
        assert invited.status_code == 200, invited.text
        username = invited.json()["username"]
        activation = self.client.post(
            "/api/v1/technician/activate",
            json={"token": invited.json()["token"], "password": "old-pass-123"},
        )
        assert activation.status_code == 200, activation.text
        old_token = activation.json()["token"]

        reset = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/reset-login",
            headers=self.manager_headers,
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["username"] == username
        old_password_login = self.client.post(
            "/api/v1/admin/login",
            json={"username": username, "password": "old-pass-123"},
        )
        assert old_password_login.status_code == 401
        reset_activation = self.client.post(
            "/api/v1/technician/activate",
            json={"token": reset.json()["token"], "password": "second-pass-123"},
        )
        assert reset_activation.status_code == 200, reset_activation.text
        denied_old_session = self.client.get(
            "/api/v1/technician/me", headers={"Authorization": f"Bearer {old_token}"}
        )
        assert denied_old_session.status_code == 401

        disabled = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/disable",
            headers=self.manager_headers,
        )
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["login_status"] == "disabled"
        disabled_login = self.client.post(
            "/api/v1/admin/login",
            json={"username": username, "password": "second-pass-123"},
        )
        assert disabled_login.status_code == 401
        assert self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/disable",
            headers=self.manager_headers,
        ).json()["login_status"] == "disabled"

        restored = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/restore",
            headers=self.manager_headers,
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["login_status"] == "active"
        listing = self.client.get("/api/v1/admin/v2/technicians", headers=self.manager_headers)
        assert listing.status_code == 200, listing.text
        row = next(item for item in listing.json()["items"] if item["id"] == self.technician_id)
        assert row["username"] == username
        assert row["login_status"] == "active"

        with self.SessionLocal() as db:
            actions = db.scalars(
                select(AuditLog.action).where(
                    AuditLog.entity_type == "technician",
                    AuditLog.entity_id == str(self.technician_id),
                )
            ).all()
            assert actions.count("reset_technician_login") == 1
            assert actions.count("disable_technician_login") == 1
            assert actions.count("restore_technician_login") == 1

    def test_activation_invite_is_single_use_and_reset_purpose_requires_new_password(self):
        issued = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/invite",
            headers=self.manager_headers,
        )
        assert issued.status_code == 200, issued.text
        activated = self.client.post(
            "/api/v1/technician/activate",
            json={"token": issued.json()["token"], "password": "first-pass-123"},
        )
        assert activated.status_code == 200, activated.text
        replay = self.client.post(
            "/api/v1/technician/activate",
            json={"token": issued.json()["token"], "password": "other-pass-123"},
        )
        assert replay.status_code == 400
        reset = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/reset-login",
            headers=self.manager_headers,
        )
        assert reset.status_code == 200, reset.text
        reset_activation = self.client.post(
            "/api/v1/technician/activate",
            json={"token": reset.json()["token"], "password": "second-pass-123"},
        )
        assert reset_activation.status_code == 200, reset_activation.text

    def test_replaying_same_invite_request_key_does_not_issue_a_second_credential(self):
        headers = {**self.manager_headers, "Idempotency-Key": "invite-request-001"}
        issued = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/invite",
            headers=headers,
        )
        assert issued.status_code == 200, issued.text
        replay = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/invite",
            headers=headers,
        )
        assert replay.status_code == 409
        assert replay.json()["detail"]["code"] == "IDEMPOTENCY_REPLAY"
        with self.SessionLocal() as db:
            assert db.scalar(select(Staff).where(Staff.technician_id == self.technician_id)).id
            actions = db.scalars(
                select(AuditLog.action).where(
                    AuditLog.action == "invite_technician",
                    AuditLog.entity_id == str(self.technician_id),
                )
            ).all()
            assert actions == ["invite_technician"]

    def test_replaying_same_reset_request_key_does_not_rotate_again(self):
        issued = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/invite",
            headers=self.manager_headers,
        )
        assert issued.status_code == 200, issued.text
        activated = self.client.post(
            "/api/v1/technician/activate",
            json={"token": issued.json()["token"], "password": "first-pass-123"},
        )
        assert activated.status_code == 200, activated.text
        headers = {**self.manager_headers, "Idempotency-Key": "reset-request-001"}
        reset = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/reset-login",
            headers=headers,
        )
        assert reset.status_code == 200, reset.text
        replay = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/reset-login",
            headers=headers,
        )
        assert replay.status_code == 409
        assert replay.json()["detail"]["code"] == "IDEMPOTENCY_REPLAY"
        with self.SessionLocal() as db:
            actions = db.scalars(
                select(AuditLog.action).where(
                    AuditLog.action == "reset_technician_login",
                    AuditLog.entity_id == str(self.technician_id),
                )
            ).all()
            assert actions == ["reset_technician_login"]

    def test_replaying_same_disable_request_key_is_state_idempotent_and_audited_once(self):
        issued = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/invite",
            headers=self.manager_headers,
        )
        assert issued.status_code == 200, issued.text
        headers = {**self.manager_headers, "Idempotency-Key": "disable-request-001"}
        first = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/disable",
            headers=headers,
        )
        assert first.status_code == 200, first.text
        replay = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/disable",
            headers=headers,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["login_status"] == "disabled"
        with self.SessionLocal() as db:
            actions = db.scalars(
                select(AuditLog.action).where(
                    AuditLog.action == "disable_technician_login",
                    AuditLog.entity_id == str(self.technician_id),
                )
            ).all()
            assert actions == ["disable_technician_login"]

    def test_cross_store_lifecycle_target_is_hidden_from_manager(self):
        response = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.other_technician_id}/invite",
            headers=self.manager_headers,
        )
        assert response.status_code == 404
        response = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.other_technician_id}/reset-login",
            headers=self.manager_headers,
        )
        assert response.status_code == 404

    def test_legacy_delete_cannot_physically_remove_technician(self):
        response = self.client.delete(
            f"/api/v1/admin/v2/technicians/{self.technician_id}",
            headers=self.manager_headers,
        )
        assert response.status_code == 410
        assert response.json()["detail"]["code"] == "TECHNICIAN_PHYSICAL_DELETE_FORBIDDEN"
        with self.SessionLocal() as db:
            assert db.get(Technician, self.technician_id) is not None

    def test_resign_rejects_active_assignment_and_rehire_issues_fresh_activation(self):
        with self.SessionLocal() as db:
            staff = Staff(
                username="lifecycle-resign",
                password_hash=hash_password("tech-pass-123"),
                name="小悦技师",
                role="technician",
                status="active",
                store_id=self.store_id,
                technician_id=self.technician_id,
            )
            db.add(staff)
            db.flush()
            assignment = ServiceAssignment(
                store_id=self.store_id,
                service_order_id=1,
                technician_id=self.technician_id,
                room_id=1,
                status="assigned",
            )
            db.add(assignment)
            db.commit()
        blocked = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/resign",
            headers=self.manager_headers,
            json={"reason": "交接前"},
        )
        assert blocked.status_code == 409
        with self.SessionLocal() as db:
            db.query(ServiceAssignment).delete()
            db.commit()
        resigned = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/resign",
            headers=self.manager_headers,
            json={"reason": "离职办理"},
        )
        assert resigned.status_code == 200
        assert resigned.json()["status"] == "resigned"
        rehire = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/rehire",
            headers=self.manager_headers,
        )
        assert rehire.status_code == 200, rehire.text
        assert rehire.json()["status"] == "invited"
        assert rehire.json()["token"]
        with self.SessionLocal() as db:
            technician = db.get(Technician, self.technician_id)
            assert technician.status == "available"
            assert db.scalar(select(Staff).where(Staff.technician_id == self.technician_id)).status == "invited"
