from datetime import datetime, timezone
import json
import shutil
import subprocess

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, CustomerProfileRecord, Order, PositionOccupancy, SelectionSession, Staff, Store, User
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
            "customer_reported": {"force_preference": "gentle"},
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

    def test_v3_profile_saves_quick_six_and_extended_preferences_in_one_record(self):
        payload = self.v3_payload()
        payload["profile"]["customer_reported"].update({
            "focus_areas": ["neck_shoulder", "legs"],
            "avoid_areas": ["abdomen"],
            "force_preference": "medium",
            "temperature_preference": "lower",
            "communication_consumption": {
                "decision_priorities": ["quality", "fixed_technician"],
                "budget_preference": "balanced",
            },
        })
        payload["profile"]["technician_observed"]["service_feedback"] = "suitable"
        payload["profile"]["next_visit"]["plan"] = "repeat_current"

        response = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            json=payload,
            headers={**self.technician_headers, "Idempotency-Key": "v3-profile-mixed-001"},
        )
        assert response.status_code == 200, response.text
        with self.SessionLocal() as db:
            records = db.query(CustomerProfileRecord).all()
            assert len(records) == 1
            stored = records[0].profile
            assert stored["customer_reported"]["focus_areas"] == ["neck_shoulder", "legs"]
            assert stored["customer_reported"]["communication_consumption"]["budget_preference"] == "balanced"

        payload["profile"]["customer_reported"]["focus_areas"] = ["legs", "legs"]
        duplicate = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            json=payload,
            headers={**self.technician_headers, "Idempotency-Key": "v3-profile-mixed-002"},
        )
        assert duplicate.status_code == 422, duplicate.text

    def test_v3_quick_note_accepts_documented_multi_select_limits_and_rejects_excess(self):
        payload = self.v3_payload()
        payload["profile"]["customer_reported"]["work_lifestyle"]["occupation_contexts"] = ["desk_work", "frequent_driving"]
        payload["profile"]["customer_reported"]["service_related_context"]["contexts"] = ["skin_sensitivity"]
        accepted = self.client.post(
            "/api/v1/admin/v2/customer-profile-records", json=payload,
            headers={**self.technician_headers, "Idempotency-Key": "v3-profile-limits-001"},
        )
        assert accepted.status_code == 200, accepted.text

        payload["profile"]["customer_reported"]["work_lifestyle"]["occupation_contexts"].append("physical_labor")
        rejected = self.client.post(
            "/api/v1/admin/v2/customer-profile-records", json=payload,
            headers={**self.technician_headers, "Idempotency-Key": "v3-profile-limits-002"},
        )
        assert rejected.status_code == 422, rejected.text

    def test_blank_v3_is_rejected_even_when_sections_and_quote_are_present(self):
        for confirmed in (True, False):
            payload = self.v3_payload(customer_confirmed=confirmed, profile={
                "schema_version": 3, "taxonomy_version": "service_reference_v2",
                "customer_reported": {"service_related_context": {"quote": "  "}},
                "technician_observed": {}, "next_visit": {},
            })
            response = self.client.post("/api/v1/admin/v2/customer-profile-records", json=payload, headers=self.technician_headers)
            assert response.status_code == 422, response.text

        observation = self.v3_payload(customer_confirmed=False, profile={
            "schema_version": 3, "taxonomy_version": "service_reference_v2",
            "technician_observed": {"service_feedback": "suitable"},
        })
        response = self.client.post("/api/v1/admin/v2/customer-profile-records", json=observation, headers=self.technician_headers)
        assert response.status_code == 200, response.text
        assert response.json()["source"] == "service_observation"
        assert response.json()["customer_confirmed"] is False
        assert response.json()["confirmed_at"] is None

    def test_v3_requires_service_association(self):
        response = self.client.post("/api/v1/admin/v2/customer-profile-records", json=self.v3_payload(selection_session_id=None), headers=self.technician_headers)
        assert response.status_code == 422, response.text

    def test_manager_cannot_create_v3_or_correct_v3_via_legacy_version(self):
        saved = self.client.post("/api/v1/admin/v2/customer-profile-records", json=self.v3_payload(), headers=self.technician_headers)
        assert saved.status_code == 200, saved.text
        with self.SessionLocal() as db:
            manager = Staff(username="v3-manager", name="店长", password_hash=hash_password("pass"), role="manager", status="active", store_id=1)
            db.add(manager)
            db.commit()
            headers = {"Authorization": f"Bearer {create_staff_token(manager.id, 'manager')}", "Idempotency-Key": "manager-v3-block"}
        for payload in (self.v3_payload(), self.v3_payload(correction_of_id=saved.json()["id"], correction_reason="核对"), {
            "user_id": self.user_id, "profile": {"age_range": "31-40"},
            "correction_of_id": saved.json()["id"], "correction_reason": "绕过版本",
        }):
            response = self.client.post("/api/v1/admin/v2/customer-profile-records", json=payload, headers=headers)
            assert response.status_code == 403, response.text

    def test_v3_saved_record_is_visible_to_next_service_without_private_content(self):
        saved = self.client.post("/api/v1/admin/v2/customer-profile-records", json=self.v3_payload(), headers=self.technician_headers)
        assert saved.status_code == 200, saved.text
        with self.SessionLocal() as db:
            old = db.query(PositionOccupancy).first()
            old.active_room_id = None
            old.active_session_id = None
            db.flush()
            session = SelectionSession(id="next-v3-session", store_id=1, customer_id=self.user_id, access_token_hash="next-v3", status="submitted", items=[])
            db.add(session)
            db.flush()
            occupancy = PositionOccupancy(store_id=1, room_id=old.room_id, active_room_id=old.room_id, selection_session_id=session.id, active_session_id=session.id, status="waiting_service")
            db.add(occupancy)
            db.commit()
            occupancy_id = occupancy.id
        response = self.client.get(f"/api/v1/technician/occupancies/{occupancy_id}/service-reference", headers=self.technician_headers)
        assert response.status_code == 200, response.text
        assert response.json()["record"]["occupation_contexts"] == ["久坐办公"]
        assert "顾客自述正在用药" not in response.text
        assert "personal_context" not in response.text

    @pytest.mark.parametrize(("reported", "expected_areas", "expected_labels"), [
        ({"force_preference": "gentle"}, ([], []), ["未记录", "未记录"]),
        ({"focus_areas": ["neck_shoulder"]}, (["肩颈"], []), ["肩颈", "未记录"]),
        ({"avoid_areas": ["abdomen"]}, ([], ["腹部"]), ["未记录", "腹部"]),
    ])
    def test_next_service_arrays_support_drawer_join_for_minimal_v3(self, reported, expected_areas, expected_labels):
        payload = self.v3_payload(profile={
            "schema_version": 3, "taxonomy_version": "service_reference_v2",
            "customer_reported": reported,
        })
        saved = self.client.post("/api/v1/admin/v2/customer-profile-records", json=payload, headers=self.technician_headers)
        assert saved.status_code == 200, saved.text
        with self.SessionLocal() as db:
            old = db.query(PositionOccupancy).first()
            old.active_room_id = None
            old.active_session_id = None
            db.flush()
            session = SelectionSession(id="minimal-v3-next", store_id=1, customer_id=self.user_id, access_token_hash="minimal-v3-next", status="submitted", items=[])
            db.add(session)
            db.flush()
            occupancy = PositionOccupancy(store_id=1, room_id=old.room_id, active_room_id=old.room_id, selection_session_id=session.id, active_session_id=session.id, status="waiting_service")
            db.add(occupancy)
            db.commit()
            occupancy_id = occupancy.id
        response = self.client.get(f"/api/v1/technician/occupancies/{occupancy_id}/service-reference", headers=self.technician_headers)
        assert response.status_code == 200, response.text
        record = response.json()["record"]
        assert record["focus_areas"] == expected_areas[0]
        assert record["avoid_areas"] == expected_areas[1]
        if "force_preference" in reported:
            assert record["force_preference"] == "轻柔"

        # Consume the real API payload using the drawer's JavaScript array contract.
        # This catches absent/null arrays that would throw in Array.join at render.
        node = shutil.which("node")
        if node is None:
            return  # Backend-only environments still verify both array fields above.
        rendered = subprocess.run([
            node, "-e",
            "const record = JSON.parse(process.argv[1]); process.stdout.write(JSON.stringify([record.focus_areas.join('、') || '未记录', record.avoid_areas.join('、') || '未记录']));",
            json.dumps(record),
        ], capture_output=True, text=True, encoding="utf-8", check=False)
        assert rendered.returncode == 0, rendered.stderr
        assert json.loads(rendered.stdout) == expected_labels

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
        assert set(body["groups"]["personal_context"]["age_band"]) == {"18_24", "25_34", "35_44", "45_54", "55_64", "65_plus"}
        assert set(body["groups"]["communication_consumption"]["budget_preference"]) == {"value", "balanced", "experience", "unexpressed"}

    def test_taxonomy_codes_submit_at_their_published_model_paths(self):
        taxonomy = self.client.get(
            "/api/v1/technician/service-reference-taxonomy",
            headers=self.technician_headers,
        ).json()["groups"]

        payloads = []
        for code in taxonomy["personal_context"]["age_band"]:
            payload = self.v3_payload()
            payload["profile"]["customer_reported"]["personal_context"] = {"age_band": code}
            payloads.append(payload)
        for code in taxonomy["personal_context"]["build"]:
            payload = self.v3_payload()
            payload["profile"]["customer_reported"]["personal_context"] = {"build": code}
            payloads.append(payload)
        for code in taxonomy["personal_context"]["height_band"]:
            payload = self.v3_payload()
            payload["profile"]["customer_reported"]["personal_context"] = {"height_band": code}
            payloads.append(payload)
        for code in taxonomy["occupation_contexts"]:
            payload = self.v3_payload()
            payload["profile"]["customer_reported"]["work_lifestyle"] = {"occupation_contexts": [code]}
            payloads.append(payload)
        for code in taxonomy["work_lifestyle"]["sleep_quality"]:
            payload = self.v3_payload()
            payload["profile"]["customer_reported"]["work_lifestyle"] = {"sleep_quality": code}
            payloads.append(payload)
        for code in taxonomy["service_related_context"]["contexts"]:
            payload = self.v3_payload()
            payload["profile"]["customer_reported"]["service_related_context"] = {"contexts": [code]}
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
