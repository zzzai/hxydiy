from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, Order, PositionOccupancy, SelectionSession, Staff, Store, User
from app.models.operations import Room, Technician


class TestTechnicianProfileV3Contract:
    def setup_method(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            store = Store(store_code="v3-profile-store", name="v3 画像测试店", address="测试地址")
            technician = Technician(store_id=1, code="V3-TECH", name="v3 技师", status="available")
            customer = User(openid="v3-profile-customer", nickname="顾客")
            db.add_all([store, technician, customer])
            db.flush()
            technician.store_id = store.id
            staff = Staff(
                username="v3-profile-tech",
                password_hash=hash_password("tech-pass"),
                name="v3 技师",
                role="technician",
                status="active",
                store_id=store.id,
                technician_id=technician.id,
            )
            room = Room(store_id=store.id, code="V3-SOFA", name="测试沙发", room_type="sofa", status="occupied")
            session = SelectionSession(
                id="v3-profile-session",
                store_id=store.id,
                customer_id=customer.id,
                access_token_hash="v3-profile-token",
                status="completed",
                items=[{"name": "草本泡脚"}],
            )
            db.add_all([
                staff,
                room,
                session,
                Order(order_no="V3-PROFILE-ORDER", order_type="service", user_id=customer.id, store_id=store.id, items=[], status="completed", pay_status="paid"),
            ])
            db.flush()
            occupancy = PositionOccupancy(
                store_id=store.id,
                room_id=room.id,
                selection_session_id=session.id,
                active_room_id=room.id,
                active_session_id=session.id,
                status="post_service_present",
                actual_service_end_at=datetime.now(timezone.utc),
            )
            db.add(occupancy)
            db.flush()
            db.add(AuditLog(
                actor_type="staff",
                actor_id=str(staff.id),
                store_id=store.id,
                action="technician_finish_service",
                entity_type="position_occupancy",
                entity_id=str(occupancy.id),
                detail={"selection_session_id": session.id},
            ))
            db.commit()
            self.staff_id = staff.id
            self.user_id = customer.id
            self.session_id = session.id

        app.dependency_overrides[get_db] = self._override_get_db
        self.client = TestClient(app)
        self.technician_headers = {
            "Authorization": f"Bearer {create_staff_token(self.staff_id, 'technician')}",
            "Idempotency-Key": "v3-profile-contract-001",
        }

    def teardown_method(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()

    def _override_get_db(self):
        with self.SessionLocal() as db:
            yield db

    def v3_payload(self, **overrides):
        profile = {
            "schema_version": 3,
            "taxonomy_version": "service_reference_v2",
            "customer_reported": {
                "personal_context": {"age_band": "25_34", "build": "balanced"},
                "work_lifestyle": {"occupation_contexts": ["desk_work"], "sleep_quality": "average"},
                "service_related_context": {"contexts": ["medication_mentioned"], "quote": "顾客自述正在用药"},
            },
            "technician_observed": {"session_response": {"relaxation": "gradual"}},
            "next_visit": {},
        }
        payload = {
            "user_id": self.user_id,
            "selection_session_id": self.session_id,
            "schema_version": 3,
            "taxonomy_version": "service_reference_v2",
            "customer_confirmed": True,
            "profile": profile,
            "signals": [],
            "note": "",
        }
        payload.update(overrides)
        return payload

    def test_v3_profile_accepts_confirmed_customer_context_and_rejects_unknown_codes(self):
        payload = self.v3_payload()
        response = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            json=payload,
            headers=self.technician_headers,
        )
        assert response.status_code == 200, response.text

        payload["profile"]["customer_reported"]["personal_context"]["age_band"] = "guess"
        response = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            json=payload,
            headers={**self.technician_headers, "Idempotency-Key": "v3-profile-contract-002"},
        )
        assert response.status_code == 422, response.text

    def test_v3_profile_rejects_duplicate_codes_and_allows_minimal_optional_sections(self):
        minimal = self.v3_payload(profile={
            "schema_version": 3,
            "taxonomy_version": "service_reference_v2",
            "customer_reported": {},
            "technician_observed": {},
            "next_visit": {},
        })
        response = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            json=minimal,
            headers=self.technician_headers,
        )
        assert response.status_code == 200, response.text

        duplicate = self.v3_payload()
        duplicate["profile"]["customer_reported"]["work_lifestyle"]["occupation_contexts"] = ["desk_work", "desk_work"]
        response = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            json=duplicate,
            headers={**self.technician_headers, "Idempotency-Key": "v3-profile-contract-003"},
        )
        assert response.status_code == 422, response.text

    def test_taxonomy_endpoint_exposes_v3_stable_codes(self):
        response = self.client.get(
            "/api/v1/technician/service-reference-taxonomy",
            headers=self.technician_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["schema_version"] == 3
        assert body["taxonomy_version"] == "service_reference_v2"
        assert "desk_work" in body["groups"]["occupation_contexts"]
        assert body["groups"]["personal_context"]["height_band"]["average"] == "适中"

    def test_taxonomy_codes_submit_at_their_published_model_paths(self):
        taxonomy = self.client.get(
            "/api/v1/technician/service-reference-taxonomy",
            headers=self.technician_headers,
        ).json()["groups"]

        payloads = []
        for code in taxonomy["personal_context"]["height_band"]:
            payload = self.v3_payload()
            payload["profile"]["customer_reported"]["personal_context"] = {"height_band": code}
            payloads.append(payload)
        for code in taxonomy["occupation_contexts"]:
            payload = self.v3_payload()
            payload["profile"]["customer_reported"]["work_lifestyle"] = {"occupation_contexts": [code]}
            payloads.append(payload)
        for code in taxonomy["session_response"]["relaxation"]:
            payload = self.v3_payload()
            payload["profile"]["technician_observed"] = {"session_response": {"relaxation": code}}
            payloads.append(payload)

        for index, payload in enumerate(payloads):
            response = self.client.post(
                "/api/v1/admin/v2/customer-profile-records",
                json=payload,
                headers={**self.technician_headers, "Idempotency-Key": f"v3-taxonomy-path-{index:03d}"},
            )
            assert response.status_code == 200, response.text
