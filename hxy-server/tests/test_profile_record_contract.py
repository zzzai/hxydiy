from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, CustomerProfileRecord, Order, Staff, Store, User
from app.models.operations import Technician


class TestProfileRecordContract:
    def test_model_exposes_service_reference_version_and_confirmation_fields(self):
        table = CustomerProfileRecord.__table__

        assert table.c.schema_version.default.arg == 1
        assert table.c.taxonomy_version.nullable is True
        assert table.c.customer_confirmed.default.arg is False
        assert table.c.confirmed_at.nullable is True

    def setup_method(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            own_store = Store(store_code="profile-v2-own", name="画像本店", address="本店地址")
            other_store = Store(store_code="profile-v2-other", name="画像他店", address="他店地址")
            db.add_all([own_store, other_store])
            db.flush()
            technician = Technician(
                store_id=own_store.id,
                code="PROFILE-V2-TECH",
                name="画像技师",
                status="available",
            )
            own_user = User(openid="profile-v2-own-user", nickname="本店顾客")
            other_user = User(openid="profile-v2-other-user", nickname="他店顾客")
            db.add_all([technician, own_user, other_user])
            db.flush()
            technician_staff = Staff(
                username="profile-v2-technician",
                password_hash=hash_password("tech-pass"),
                name="画像技师",
                role="technician",
                status="active",
                store_id=own_store.id,
                technician_id=technician.id,
            )
            manager_staff = Staff(
                username="profile-v2-manager",
                password_hash=hash_password("manager-pass"),
                name="画像店长",
                role="manager",
                status="active",
                store_id=own_store.id,
            )
            db.add_all([technician_staff, manager_staff])
            db.flush()
            db.add_all([
                Order(
                    order_no="PROFILE-V2-OWN-ORDER",
                    order_type="service",
                    user_id=own_user.id,
                    store_id=own_store.id,
                    items=[],
                    status="completed",
                    pay_status="paid",
                ),
                Order(
                    order_no="PROFILE-V2-OTHER-ORDER",
                    order_type="service",
                    user_id=other_user.id,
                    store_id=other_store.id,
                    items=[],
                    status="completed",
                    pay_status="paid",
                ),
            ])
            db.commit()
            self.technician_staff_id = technician_staff.id
            self.manager_staff_id = manager_staff.id
            self.technician_id = technician.id
            self.own_user_id = own_user.id
            self.other_user_id = other_user.id

        app.dependency_overrides[get_db] = self._override_get_db
        self.client = TestClient(app)
        self.technician_headers = {
            "Authorization": f"Bearer {create_staff_token(self.technician_staff_id, 'technician')}"
        }
        self.manager_headers = {
            "Authorization": f"Bearer {create_staff_token(self.manager_staff_id, 'manager')}"
        }

    def _override_get_db(self):
        with self.SessionLocal() as db:
            yield db

    def teardown_method(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()

    def test_legacy_profile_route_is_manager_only(self):
        denied = self.client.post(
            f"/api/v1/admin/v2/customers/{self.own_user_id}/profile-records",
            headers=self.technician_headers,
            json={"tags": ["久坐", "偏好轻柔力度"], "service_note": "顾客自述肩颈容易疲劳"},
        )
        assert denied.status_code == 403, denied.text

        created = self.client.post(
            f"/api/v1/admin/v2/customers/{self.own_user_id}/profile-records",
            headers={**self.manager_headers, "Idempotency-Key": "legacy-manager-profile-001"},
            json={"tags": ["久坐", "偏好轻柔力度"], "service_note": "顾客自述肩颈容易疲劳"},
        )
        assert created.status_code == 200, created.text
        assert created.json()["technician_id"] is None
        with self.SessionLocal() as db:
            record = db.scalar(select(CustomerProfileRecord))
            assert record is not None
            assert record.created_by_staff_id == self.manager_staff_id
            assert record.technician_id is None

    def test_cross_store_health_claims_and_length_limits_are_rejected(self):
        cross_store = self.client.post(
            f"/api/v1/admin/v2/customers/{self.other_user_id}/profile-records",
            headers={**self.manager_headers, "Idempotency-Key": "legacy-cross-store-001"},
            json={"tags": ["久坐"], "service_note": "顾客自述容易疲劳"},
        )
        diagnosis = self.client.post(
            f"/api/v1/admin/v2/customers/{self.own_user_id}/profile-records",
            headers={**self.manager_headers, "Idempotency-Key": "legacy-health-claim-001"},
            json={"tags": ["确诊颈椎病"], "service_note": ""},
        )
        curative_claim = self.client.post(
            f"/api/v1/admin/v2/customers/{self.own_user_id}/profile-records",
            headers={**self.manager_headers, "Idempotency-Key": "legacy-curative-claim-001"},
            json={"tags": [], "service_note": "本项目可以治愈失眠"},
        )
        long_tag = self.client.post(
            f"/api/v1/admin/v2/customers/{self.own_user_id}/profile-records",
            headers={**self.manager_headers, "Idempotency-Key": "legacy-long-tag-001"},
            json={"tags": ["久" * 33], "service_note": ""},
        )
        long_note = self.client.post(
            f"/api/v1/admin/v2/customers/{self.own_user_id}/profile-records",
            headers={**self.manager_headers, "Idempotency-Key": "legacy-long-note-001"},
            json={"tags": [], "service_note": "顾" * 1001},
        )

        assert cross_store.status_code == 404
        assert diagnosis.status_code == 422
        assert curative_claim.status_code == 422
        assert long_tag.status_code == 422
        assert long_note.status_code == 422

    def test_manager_can_create_record_and_action_is_audited(self):
        response = self.client.post(
            f"/api/v1/admin/v2/customers/{self.own_user_id}/profile-records",
            headers={**self.manager_headers, "Idempotency-Key": "legacy-manager-audit-001"},
            json={"tags": ["偏好中等力度"], "service_note": "店长根据顾客当面陈述代录"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["technician_id"] is None
        with self.SessionLocal() as db:
            audit = db.scalar(select(AuditLog).where(
                AuditLog.action == "manager_create_customer_profile_record",
                AuditLog.entity_type == "customer_profile_record",
                AuditLog.entity_id == str(response.json()["id"]),
                AuditLog.store_id == response.json()["store_id"],
            ))
            assert audit is not None
            assert audit.actor_id == self.manager_staff_id.__str__()

    def test_manager_cannot_create_confirmed_v2_reference_without_completed_service(self):
        response = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**self.manager_headers, "Idempotency-Key": "manager-v2-no-service-001"},
            json={
                "user_id": self.own_user_id,
                "schema_version": 2,
                "taxonomy_version": "service_reference_v1",
                "customer_confirmed": True,
                "profile": {
                    "schema_version": 2,
                    "taxonomy_version": "service_reference_v1",
                    "customer_reported": {"focus_areas": ["neck_shoulder"]},
                },
            },
        )

        assert response.status_code == 422, response.text
