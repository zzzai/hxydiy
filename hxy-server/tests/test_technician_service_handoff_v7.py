from copy import deepcopy

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.models import CustomerProfileRecord, SelectionSession, PositionOccupancy
from app.schemas.service_handoff import ServiceHandoffRecord, safe_handoff_lines
from test_technician_profile_quick_note_contract import TestTechnicianProfileQuickNoteContract as Fixture


def valid_profile():
    return {
        "schema_version": 7,
        "taxonomy_version": "service_handoff_v1",
        "communication": "quiet",
        "body_focus": [{"region": "neck_shoulder", "next_action": "lighter"}],
        "session_changes": ["temperature_lower"],
        "basic_info": {"age_band": "age_40_44", "gender": "female"},
        "private_note": "下次先问右肩感受",
    }


def test_v7_schema_accepts_only_stable_basic_info_and_paired_body_actions():
    record = ServiceHandoffRecord.model_validate(valid_profile())
    assert record.basic_info.age_band == "age_40_44"
    assert safe_handoff_lines(record.storage_payload()) == [
        "顾客想安静休息",
        "肩颈：下次轻一些",
        "本次已调低温度",
    ]

    for field, value in (("age_band", "40-45"), ("gender", "unknown")):
        invalid = valid_profile()
        invalid["basic_info"][field] = value
        with pytest.raises(ValidationError):
            ServiceHandoffRecord.model_validate(invalid)

    missing_action = valid_profile()
    missing_action["body_focus"] = [{"region": "knee"}]
    with pytest.raises(ValidationError):
        ServiceHandoffRecord.model_validate(missing_action)


def test_v7_schema_limits_body_entries_and_keeps_private_text_out_of_safe_lines():
    invalid = valid_profile()
    invalid["body_focus"] = [
        {"region": "neck_shoulder", "next_action": "lighter"},
        {"region": "waist_back", "next_action": "focus"},
        {"region": "leg", "next_action": "confirm"},
        {"region": "knee", "next_action": "avoid"},
    ]
    with pytest.raises(ValidationError):
        ServiceHandoffRecord.model_validate(invalid)

    assert "下次先问右肩感受" not in str(safe_handoff_lines(valid_profile()))


def test_v7_no_new_cannot_mix_with_content_or_confirmation():
    empty = {
        "schema_version": 7,
        "taxonomy_version": "service_handoff_v1",
        "recording_outcome": "no_additional_notes",
    }
    assert ServiceHandoffRecord.model_validate(empty).recording_outcome == "no_additional_notes"
    mixed = {**empty, "communication": "chat"}
    with pytest.raises(ValidationError):
        ServiceHandoffRecord.model_validate(mixed)


class TestServiceHandoffV7:
    setup_method = Fixture.setup_method
    teardown_method = Fixture.teardown_method
    _override_get_db = Fixture._override_get_db

    def payload(self):
        return {
            "user_id": self.own_user_id,
            "selection_session_id": self.session_id,
            "schema_version": 7,
            "taxonomy_version": "service_handoff_v1",
            "customer_confirmed": True,
            "profile": valid_profile(),
            "signals": [],
            "note": "",
        }

    def post(self, payload, key="handoff-v7-001"):
        return self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            json=payload,
            headers={**self.headers, "Idempotency-Key": key},
        )

    def test_options_default_to_v7_and_keep_v6_history_editor_compatible(self):
        current = self.client.get("/api/v1/technician/service-record-options", headers=self.headers)
        assert current.status_code == 200
        assert current.json()["taxonomy_version"] == "service_handoff_v1"
        assert current.json()["groups"]["gender"] == [
            {"value": "male", "label": "男"},
            {"value": "female", "label": "女"},
        ]

        legacy = self.client.get("/api/v1/technician/service-record-options?schema_version=6", headers=self.headers)
        assert legacy.status_code == 200, legacy.text
        assert legacy.json()["taxonomy_version"] == "service_record_v1"
        assert "water_request" in legacy.json()["groups"]

    def test_v7_write_is_idempotent_and_private_note_is_redacted_from_safe_views(self):
        payload = self.payload()
        first = self.post(payload)
        assert first.status_code == 200, first.text
        assert self.post(payload).json()["id"] == first.json()["id"]

        changed = deepcopy(payload)
        changed["profile"]["communication"] = "chat"
        assert self.post(changed).status_code == 409

        from app.api.admin_v2 import _management_profile_record_view
        from app.api.technician import _history_profile_summary

        with self.SessionLocal() as db:
            record = db.get(CustomerProfileRecord, first.json()["id"])
            management_view = _management_profile_record_view(record, db)
            assert "private_note" not in str(management_view)
            assert "肩颈" not in str(management_view)
            assert management_view["profile"]["body_reconfirm_required"] is True
            assert _history_profile_summary(record)["service_lines"] == [
                "顾客想安静休息",
                "肩颈：下次轻一些",
                "本次已调低温度",
            ]

    def test_v7_supports_one_owned_correction_and_preserves_original(self):
        payload = self.payload()
        first = self.post(payload)
        payload["correction_of_id"] = first.json()["id"]
        payload["correction_reason"] = "补充顾客确认后的调整"
        payload["profile"]["body_focus"][0]["next_action"] = "confirm"
        revised = self.post(payload, "handoff-v7-002")
        assert revised.status_code == 200, revised.text
        assert self.post(payload, "handoff-v7-003").status_code == 409
        with self.SessionLocal() as db:
            original = db.get(CustomerProfileRecord, first.json()["id"])
            assert original.profile["body_focus"][0]["next_action"] == "lighter"

    def test_v7_requires_completed_owned_service(self):
        payload = self.payload()
        with self.SessionLocal() as db:
            occupancy = db.scalar(select(PositionOccupancy).where(PositionOccupancy.selection_session_id == self.session_id))
            occupancy.actual_service_end_at = None
            db.commit()
        assert self.post(payload).status_code == 409

        wrong_customer = self.payload()
        wrong_customer["user_id"] = self.other_user_id
        assert self.post(wrong_customer, "handoff-v7-other").status_code == 404
