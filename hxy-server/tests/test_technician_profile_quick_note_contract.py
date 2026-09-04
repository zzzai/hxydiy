from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, CustomerProfileRecord, Order, PositionOccupancy, SelectionSession, Staff, Store, User
from app.models.operations import Room, Technician


class TestTechnicianProfileQuickNoteContract:
    def setup_method(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            store = Store(store_code="quick-note-store", name="快记测试店", address="测试地址")
            db.add(store)
            db.flush()
            technician = Technician(store_id=store.id, code="QUICK-NOTE-TECH", name="快记技师", status="available")
            own_user = User(openid="quick-note-own", nickname="本次顾客")
            other_user = User(openid="quick-note-other", nickname="无关顾客")
            db.add_all([technician, own_user, other_user])
            db.flush()
            staff = Staff(
                username="quick-note-tech",
                password_hash=hash_password("tech-pass"),
                name="快记技师",
                role="technician",
                status="active",
                store_id=store.id,
                technician_id=technician.id,
            )
            room = Room(store_id=store.id, code="QUICK-NOTE-SOFA", name="测试沙发", room_type="sofa", status="occupied")
            session = SelectionSession(
                id="quick-note-session",
                store_id=store.id,
                customer_id=own_user.id,
                access_token_hash="quick-note-token",
                status="completed",
                items=[{"name": "草本泡脚"}],
            )
            db.add_all([
                staff,
                room,
                session,
                Order(order_no="QUICK-NOTE-OWN", order_type="service", user_id=own_user.id, store_id=store.id, items=[], status="completed", pay_status="paid"),
                Order(order_no="QUICK-NOTE-OTHER", order_type="service", user_id=other_user.id, store_id=store.id, items=[], status="completed", pay_status="paid"),
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
            db.add_all([
                AuditLog(
                    actor_type="staff",
                    actor_id=str(staff.id),
                    store_id=store.id,
                    action="technician_finish_service",
                    entity_type="position_occupancy",
                    entity_id=str(occupancy.id),
                    detail={"selection_session_id": session.id},
                ),
                CustomerProfileRecord(
                    store_id=store.id,
                    user_id=other_user.id,
                    created_by_staff_id=staff.id,
                    profile={"age_range": "26-35"},
                    signals=["偏好中等力度"],
                    note="无关顾客的内部服务参考",
                ),
            ])
            db.commit()
            self.staff_id = staff.id
            self.technician_id = technician.id
            self.own_user_id = own_user.id
            self.other_user_id = other_user.id
            self.session_id = session.id

        app.dependency_overrides[get_db] = self._override_get_db
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {create_staff_token(self.staff_id, 'technician')}"}

    def teardown_method(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()

    def _override_get_db(self):
        with self.SessionLocal() as db:
            yield db

    def _payload(self):
        return {
            "user_id": self.own_user_id,
            "selection_session_id": self.session_id,
            "source": "customer_statement",
            "profile": {
                "age_range": "26-35",
                "gender": "女",
                "body_type": "标准",
                "occupation": "久坐",
            },
            "signals": ["肩颈紧张", "偏好中等力度"],
            "note": "顾客自述久坐后肩颈容易紧张。",
        }

    def _v2_payload(self, *, confirmed=True):
        return {
            "user_id": self.own_user_id,
            "selection_session_id": self.session_id,
            "schema_version": 2,
            "taxonomy_version": "service_reference_v1",
            "customer_confirmed": confirmed,
            "profile": {
                "schema_version": 2,
                "taxonomy_version": "service_reference_v1",
                "customer_reported": {
                    "focus_areas": ["neck_shoulder", "legs"],
                    "avoid_areas": [],
                    "force_preference": "medium",
                    "temperature_preference": "lower",
                    "quote": "肩颈重点，温度低一点",
                },
                "technician_observed": {"service_feedback": "better_after_adjustment"},
                "next_visit": {"plan": "repeat_current"},
            },
        }

    def test_v2_service_reference_persists_stable_structure_and_confirmation(self):
        payload = self._v2_payload()
        response = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**self.headers, "Idempotency-Key": "quick-note-v2-confirmed-001"},
            json=payload,
        )

        assert response.status_code == 200, response.text
        assert response.json()["schema_version"] == 2
        assert response.json()["taxonomy_version"] == "service_reference_v1"
        assert response.json()["customer_confirmed"] is True
        assert response.json()["source"] == "both"
        with self.SessionLocal() as db:
            record = db.get(CustomerProfileRecord, response.json()["id"])
            assert record.profile["customer_reported"]["avoid_areas"] == []
            assert record.confirmed_at is not None

    def test_v2_unconfirmed_service_reference_uses_observation_source(self):
        payload = self._v2_payload(confirmed=False)
        payload["profile"]["customer_reported"].pop("avoid_areas")
        response = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**self.headers, "Idempotency-Key": "quick-note-v2-unconfirmed-001"},
            json=payload,
        )

        assert response.status_code == 200, response.text
        assert response.json()["source"] == "service_observation"
        assert "avoid_areas" not in response.json()["profile"]["customer_reported"]
        assert response.json()["confirmed_at"] is None

    def test_v2_rejects_unknown_duplicate_long_and_medical_content(self):
        cases = []
        unknown = self._v2_payload()
        unknown["profile"]["customer_reported"]["force_preference"] = "extreme"
        cases.append(unknown)
        duplicate = self._v2_payload()
        duplicate["profile"]["customer_reported"]["focus_areas"] = ["legs", "legs"]
        cases.append(duplicate)
        too_long = self._v2_payload()
        too_long["profile"]["customer_reported"]["quote"] = "顾" * 101
        cases.append(too_long)
        medical = self._v2_payload()
        medical["profile"]["customer_reported"]["quote"] = "顾客说已经确诊颈椎病"
        cases.append(medical)
        extra = self._v2_payload()
        extra["profile"]["customer_reported"]["personality"] = "安静"
        cases.append(extra)

        for index, payload in enumerate(cases):
            response = self.client.post(
                "/api/v1/admin/v2/customer-profile-records",
                headers={**self.headers, "Idempotency-Key": f"quick-note-v2-invalid-{index:03d}"},
                json=payload,
            )
            assert response.status_code == 422, response.text

    def test_technician_cannot_read_unrelated_same_store_profile_history(self):
        response = self.client.get(
            f"/api/v1/admin/v2/users/{self.other_user_id}/customer-profile-records",
            headers=self.headers,
        )

        assert response.status_code == 403, response.text
        assert "无关顾客的内部服务参考" not in response.text

    def test_technician_cannot_bypass_finished_service_with_legacy_profile_route(self):
        response = self.client.post(
            f"/api/v1/admin/v2/customers/{self.other_user_id}/profile-records",
            headers={**self.headers, "Idempotency-Key": "legacy-profile-denied-001"},
            json={"tags": ["久坐"], "service_note": "不应绕过服务关联"},
        )

        assert response.status_code == 403, response.text

    def test_profile_write_requires_idempotency_and_replays_without_duplicate_record(self):
        missing_key = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers=self.headers,
            json=self._payload(),
        )
        assert missing_key.status_code == 400, missing_key.text

        request_headers = {**self.headers, "Idempotency-Key": "quick-note-save-001"}
        first = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers=request_headers,
            json=self._payload(),
        )
        replay = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers=request_headers,
            json=self._payload(),
        )

        assert first.status_code == 200, first.text
        assert replay.status_code == 200, replay.text
        assert replay.json()["id"] == first.json()["id"]
        with self.SessionLocal() as db:
            records = db.scalars(select(CustomerProfileRecord).where(
                CustomerProfileRecord.selection_session_id == self.session_id,
            )).all()
            assert len(records) == 1

        changed = self._payload()
        changed["note"] = "不同的内容"
        conflict = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers=request_headers,
            json=changed,
        )
        assert conflict.status_code == 409, conflict.text

    def test_profile_only_accepts_whitelisted_structured_fields_and_actual_content(self):
        unknown_field = self._payload()
        unknown_field["profile"]["diagnosis"] = "颈椎病"
        invalid = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**self.headers, "Idempotency-Key": "quick-note-invalid-001"},
            json=unknown_field,
        )
        assert invalid.status_code == 422, invalid.text

        empty = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**self.headers, "Idempotency-Key": "quick-note-empty-001"},
            json={
                "user_id": self.own_user_id,
                "selection_session_id": self.session_id,
                "source": "customer_statement",
                "profile": {},
                "signals": [],
                "note": "",
            },
        )
        assert empty.status_code == 422, empty.text

    def test_technician_profile_requires_explicit_record_source(self):
        payload = self._payload()
        payload.pop("source")
        response = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**self.headers, "Idempotency-Key": "quick-note-source-001"},
            json=payload,
        )
        assert response.status_code == 422, response.text
