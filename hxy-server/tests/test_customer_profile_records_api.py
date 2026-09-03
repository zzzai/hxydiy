import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import PositionOccupancy, SelectionSession, Staff, Store, User


class CustomerProfileRecordsApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            store = Store(store_code="profile-record-store", name="画像测试店", address="测试地址")
            other_store = Store(store_code="profile-record-other", name="另一家店", address="测试地址")
            db.add_all([store, other_store])
            db.flush()
            staff = Staff(username="profile-staff", name="店长", role="manager", status="active", password_hash=hash_password("pass"), store_id=store.id)
            user = User(openid="profile-user", phone="13800138000")
            other_user = User(openid="profile-other-user", phone="13900139000")
            db.add_all([staff, user, other_user])
            db.flush()
            db.add(SelectionSession(id="profile-session", store_id=store.id, customer_id=user.id, access_token_hash="x", source="store_qr", device_label="测试", status="completed", items=[]))
            db.add(PositionOccupancy(store_id=store.id, room_id=1, selection_session_id="profile-session", status="released", actual_service_end_at=datetime.now(timezone.utc)))
            db.commit()
            self.store_id, self.staff_id, self.user_id, self.other_user_id = store.id, staff.id, user.id, other_user.id

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {create_staff_token(self.staff_id, 'manager')}"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_staff_can_save_and_read_quick_customer_profile(self):
        response = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**self.headers, "Idempotency-Key": "manager-profile-save-001"},
            json={
                "user_id": self.user_id,
                "source": "customer_statement",
                "profile": {"age_range": "31-40", "gender": "女", "body_type": "匀称", "occupation": "教师"},
                "signals": ["肩颈紧张", "偏好中等力度"],
                "note": "本次服务后反馈肩颈放松明显",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["profile"]["occupation"], "教师")
        listed = self.client.get(f"/api/v1/admin/v2/users/{self.user_id}/customer-profile-records", headers=self.headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["items"][0]["signals"], ["肩颈紧张", "偏好中等力度"])

    def test_staff_cannot_write_customer_from_another_store(self):
        response = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**self.headers, "Idempotency-Key": "manager-profile-other-001"},
            json={"user_id": self.other_user_id, "source": "customer_statement", "profile": {}, "signals": ["放松需求"], "note": ""},
        )
        self.assertEqual(response.status_code, 404)

    def test_medical_diagnosis_wording_is_rejected(self):
        response = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**self.headers, "Idempotency-Key": "manager-profile-medical-001"},
            json={"user_id": self.user_id, "source": "service_observation", "profile": {}, "signals": ["确诊颈椎病"], "note": ""},
        )
        self.assertEqual(response.status_code, 422)

    def test_correction_creates_new_record_and_preserves_original(self):
        first = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**self.headers, "Idempotency-Key": "manager-profile-correct-001"},
            json={"user_id": self.user_id, "source": "customer_statement", "profile": {"age_range": "31-40"}, "signals": ["偏好中等力度"], "note": "首次记录"},
        )
        self.assertEqual(first.status_code, 200, first.text)
        original_id = first.json()["id"]
        corrected = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**self.headers, "Idempotency-Key": "manager-profile-correct-002"},
            json={"user_id": self.user_id, "source": "both", "correction_of_id": original_id, "correction_reason": "顾客补充说明", "profile": {"age_range": "36-45"}, "signals": ["偏好轻柔力度"], "note": "更正后的记录"},
        )
        self.assertEqual(corrected.status_code, 200, corrected.text)
        self.assertEqual(corrected.json()["correction_of_id"], original_id)
        listed = self.client.get(f"/api/v1/admin/v2/users/{self.user_id}/customer-profile-records", headers=self.headers)
        self.assertEqual(len(listed.json()["items"]), 2)
        self.assertEqual(listed.json()["items"][-1]["id"], original_id)


if __name__ == "__main__":
    unittest.main()
