import unittest
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import hash_password
from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.domain.visit_feedback_tokens import create_visit_feedback_token
from app.main import app
from app.models import AuditLog, EventLog, PositionOccupancy, Room, SelectionSession, ServiceFeedback, ServicePositionQr, Staff, Store, User, VisitFeedback


class OpenVisitFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            store = Store(store_code="visit-feedback-store", name="到店反馈门店", address="测试地址")
            other_store = Store(store_code="visit-feedback-other", name="其他门店", address="其他地址")
            db.add_all([store, other_store])
            db.flush()
            db.add_all([
                Staff(username="visit-feedback-manager", password_hash=hash_password("test-password"), name="反馈店长", role="manager", store_id=store.id),
                Staff(username="visit-feedback-other-manager", password_hash=hash_password("test-password"), name="其他店长", role="manager", store_id=other_store.id),
                Staff(username="visit-feedback-staff", password_hash=hash_password("test-password"), name="普通员工", role="staff", store_id=store.id),
            ])
            room = Room(
                store_id=store.id,
                code="visit-feedback-sofa",
                name="反馈测试服务位",
                room_type="sofa",
                customer_label="1",
                operational_status="active",
                is_service_position=True,
                is_space_container=False,
            )
            entry_room = Room(
                store_id=store.id,
                code="visit-feedback-entry",
                name="现有二维码兼容服务位",
                room_type="sofa",
                customer_label="2",
                operational_status="active",
                is_service_position=True,
                is_space_container=False,
            )
            db.add_all([room, entry_room])
            db.flush()
            qr = ServicePositionQr(
                public_id=str(uuid.uuid4()),
                store_id=store.id,
                room_id=room.id,
                source="personal_qr",
                status="active",
            )
            db.add(qr)
            db.commit()
            cls.store_id = store.id
            cls.other_store_id = other_store.id
            cls.room_id = room.id
            cls.entry_room_id = entry_room.id
            cls.qr_id = qr.id

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

    def setUp(self):
        self.client.cookies.clear()
        self.browser_token = f"visit-feedback-browser-{uuid.uuid4().hex}"
        self.client.cookies.set("hxy_browser_token", self.browser_token)
        with self.SessionLocal() as db:
            self.visit_feedback_token = create_visit_feedback_token(db.get(Room, self.room_id), "personal_qr", self.browser_token)

    def manager_headers(self, username="visit-feedback-manager"):
        response = self.client.post("/api/v1/admin/login", json={"username": username, "password": "test-password"})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['token']}"}

    def submit(self, key: str, **overrides):
        payload = {
            "visit_feedback_token": self.visit_feedback_token,
            "rating": 5,
            "tags": ["手法专业", "环境舒适"],
            "note": "到店体验很好",
        }
        payload.update(overrides)
        return self.client.post(
            "/api/v1/visit-feedback",
            headers={"Idempotency-Key": key},
            json=payload,
        )

    def test_anonymous_feedback_without_selection_is_persisted_for_qr_store(self):
        response = self.client.post(
            "/api/v1/visit-feedback",
            headers={"Idempotency-Key": "visit-feedback-anonymous-1"},
            json={
                "visit_feedback_token": self.visit_feedback_token,
                "rating": 5,
                "tags": ["手法专业", "环境舒适"],
                "note": "  到店体验很好  ",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["feedback_type"], "visit_feedback")
        self.assertEqual(response.json()["note"], "到店体验很好")
        with self.SessionLocal() as db:
            count = db.scalar(select(func.count()).select_from(Base.metadata.tables["visit_feedback"]))
            self.assertGreaterEqual(count, 1)

    def test_existing_entry_session_returns_signed_visit_feedback_token(self):
        response = self.client.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": "visit-feedback-entry",
            "source": "store_qr",
            "device_label": "扫码手机",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["visit_feedback_token"].startswith("vf1."))

    def test_logged_in_feedback_uses_verified_customer_without_session_link(self):
        with self.SessionLocal() as db:
            customer = User(openid=f"visit-login-{uuid.uuid4().hex}", phone="")
            db.add(customer)
            db.commit()
            customer_id = customer.id
            token = create_access_token(str(customer.id), customer.openid, customer.customer_login_version)
        response = self.client.post(
            "/api/v1/visit-feedback",
            headers={"Idempotency-Key": "visit-feedback-login-1", "Authorization": f"Bearer {token}"},
            json={"visit_feedback_token": self.visit_feedback_token, "rating": 3, "tags": ["环境一般"], "note": "可以更好"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        with self.SessionLocal() as db:
            row = db.get(VisitFeedback, response.json()["id"])
            self.assertEqual(row.customer_id, customer_id)
            self.assertEqual(row.store_id, self.store_id)

    def test_invalid_login_does_not_fall_back_to_anonymous(self):
        response = self.client.post(
            "/api/v1/visit-feedback",
            headers={"Idempotency-Key": "visit-feedback-invalid-login", "Authorization": "Bearer invalid"},
            json={"visit_feedback_token": self.visit_feedback_token, "rating": 5, "tags": [], "note": ""},
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_visit_feedback_token_cannot_be_tampered_or_reused_by_another_browser(self):
        tampered = self.submit("visit-feedback-tampered", visit_feedback_token=f"{self.visit_feedback_token}x")
        self.assertEqual(tampered.status_code, 403, tampered.text)
        self.assertEqual(tampered.json()["detail"]["code"], "VISIT_FEEDBACK_TOKEN_INVALID")
        self.client.cookies.set("hxy_browser_token", "another-browser")
        wrong_browser = self.submit("visit-feedback-wrong-browser")
        self.assertEqual(wrong_browser.status_code, 403, wrong_browser.text)
        self.assertEqual(wrong_browser.json()["detail"]["code"], "VISIT_FEEDBACK_TOKEN_INVALID")

    def test_visit_feedback_has_no_public_read_endpoint(self):
        response = self.client.get("/api/v1/visit-feedback")
        self.assertEqual(response.status_code, 405, response.text)

    def test_reusing_same_key_is_idempotent_but_cannot_change_payload(self):
        first = self.submit("visit-feedback-retry-1")
        retry = self.submit("visit-feedback-retry-1")
        conflict = self.submit("visit-feedback-retry-1", rating=1, tags=["等待较久"])
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["id"], first.json()["id"])
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["detail"]["code"], "IDEMPOTENCY_KEY_REUSED")

    def test_rating_tags_note_and_extra_fields_are_strict(self):
        invalid_tag = self.submit("visit-feedback-invalid-tag", rating=1, tags=["手法专业"])
        too_many = self.submit("visit-feedback-too-many", tags=["手法专业", "力度合适", "沟通细致", "环境舒适"])
        too_long = self.submit("visit-feedback-too-long", note="好" * 301)
        extra = self.submit("visit-feedback-extra", customer_id=999)
        self.assertEqual(invalid_tag.status_code, 400, invalid_tag.text)
        self.assertEqual(invalid_tag.json()["detail"]["code"], "FEEDBACK_TAG_INVALID")
        self.assertEqual(too_many.status_code, 422, too_many.text)
        self.assertEqual(too_long.status_code, 422, too_long.text)
        self.assertEqual(extra.status_code, 422, extra.text)

    def test_active_service_at_same_position_is_not_linked_or_attributed(self):
        with self.SessionLocal() as db:
            anonymous = User(openid=f"anon_{uuid.uuid4().hex}")
            db.add(anonymous)
            db.flush()
            session = SelectionSession(
                id=str(uuid.uuid4()), access_token_hash="not-used", store_id=self.store_id,
                customer_id=anonymous.id, status="submitted", items=[], pricing_snapshot={},
            )
            db.add(session)
            db.flush()
            db.add(PositionOccupancy(
                store_id=self.store_id, room_id=self.room_id, selection_session_id=session.id,
                status="in_service", source="bound_qr",
            ))
            db.commit()
        response = self.submit("visit-feedback-active-service")
        self.assertEqual(response.status_code, 200, response.text)
        with self.SessionLocal() as db:
            row = db.get(VisitFeedback, response.json()["id"])
            self.assertIsNone(row.customer_id)
            self.assertFalse(hasattr(row, "selection_session_id"))

    def test_visit_feedback_uses_separate_event_from_selection_funnel(self):
        response = self.submit("visit-feedback-event")
        self.assertEqual(response.status_code, 200, response.text)
        with self.SessionLocal() as db:
            visit_events = db.scalar(select(func.count()).select_from(EventLog).where(EventLog.event == "visit_feedback_submit_success"))
            selection_events = db.scalar(select(func.count()).select_from(EventLog).where(EventLog.event == "feedback_submit_success"))
            self.assertGreaterEqual(visit_events, 1)
            self.assertEqual(selection_events, 0)

    def test_rate_limit_is_shared_in_database(self):
        for index in range(5):
            response = self.submit(f"visit-feedback-rate-{index}", note=f"第{index + 1}条")
            self.assertEqual(response.status_code, 200, response.text)
        blocked = self.submit("visit-feedback-rate-blocked", note="第六条")
        self.assertEqual(blocked.status_code, 429, blocked.text)
        self.assertEqual(blocked.json()["detail"]["code"], "FEEDBACK_RATE_LIMITED")
        self.assertIn("Retry-After", blocked.headers)

    def test_admin_inbox_distinguishes_visit_feedback_and_service_review(self):
        visit = self.submit("visit-feedback-admin-list", rating=1, tags=["等待较久"], note="等候时间较长")
        self.assertEqual(visit.status_code, 200, visit.text)
        with self.SessionLocal() as db:
            session = SelectionSession(
                id=str(uuid.uuid4()), access_token_hash="service-review", store_id=self.store_id,
                status="confirmed", items=[], pricing_snapshot={},
            )
            db.add(session)
            db.flush()
            service_review = ServiceFeedback(
                store_id=self.store_id, selection_session_id=session.id, rating=5,
                tags=["手法专业"], note="服务很好",
            )
            db.add(service_review)
            db.commit()

        response = self.client.get(
            "/api/v1/admin/v2/feedback?page=1&page_size=100",
            headers=self.manager_headers(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        by_type = {item["feedback_type"]: item for item in response.json()["items"]}
        self.assertIsNone(by_type["visit_feedback"]["selection_session_id"])
        self.assertEqual(by_type["service_review"]["selection_session_id"], session.id)

    def test_admin_inbox_paginates_combined_sources_with_stable_order(self):
        initial = self.client.get(
            "/api/v1/admin/v2/feedback?page=1&page_size=1",
            headers=self.manager_headers(),
        )
        self.assertEqual(initial.status_code, 200, initial.text)
        initial_total = initial.json()["total"]
        first_visit = self.submit("visit-feedback-page-first", note="较早到店反馈")
        second_visit = self.submit("visit-feedback-page-second", note="较晚到店反馈")
        self.assertEqual(first_visit.status_code, 200, first_visit.text)
        self.assertEqual(second_visit.status_code, 200, second_visit.text)
        with self.SessionLocal() as db:
            session = SelectionSession(
                id=str(uuid.uuid4()), access_token_hash="service-review-page", store_id=self.store_id,
                status="confirmed", items=[], pricing_snapshot={},
            )
            db.add(session)
            db.flush()
            db.add(ServiceFeedback(
                store_id=self.store_id, selection_session_id=session.id, rating=4,
                tags=["服务贴心"], note="中间服务评价",
            ))
            db.commit()

        combined = []
        expected_total = initial_total + 3
        for page in range(1, (expected_total + 1) // 2 + 1):
            response = self.client.get(
                f"/api/v1/admin/v2/feedback?page={page}&page_size=2",
                headers=self.manager_headers(),
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["total"], expected_total)
            combined.extend(response.json()["items"])
        self.assertEqual(len(combined), expected_total)
        self.assertEqual(len({(item["feedback_type"], item["id"]) for item in combined}), expected_total)
        sort_keys = [(item["created_at"], item["feedback_type"], item["id"]) for item in combined]
        self.assertEqual(sort_keys, sorted(sort_keys, reverse=True))
        other_store = self.client.get(
            "/api/v1/admin/v2/feedback?page=1&page_size=2",
            headers=self.manager_headers("visit-feedback-other-manager"),
        )
        self.assertEqual(other_store.status_code, 200, other_store.text)
        self.assertEqual(other_store.json()["total"], 0)
        self.assertEqual(other_store.json()["items"], [])

    def test_visit_feedback_detail_and_follow_up_are_store_scoped_and_audited(self):
        created = self.submit("visit-feedback-admin-handle", rating=2, tags=["环境问题"], note="需要处理")
        self.assertEqual(created.status_code, 200, created.text)
        feedback_id = created.json()["id"]
        path = f"/api/v1/admin/v2/feedback/visit_feedback/{feedback_id}"
        hidden = self.client.get(path, headers=self.manager_headers("visit-feedback-other-manager"))
        self.assertEqual(hidden.status_code, 404, hidden.text)
        detail = self.client.get(path, headers=self.manager_headers())
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["feedback_type"], "visit_feedback")
        updated = self.client.patch(
            path,
            headers=self.manager_headers(),
            json={"follow_up_status": "resolved", "follow_up_note": "已现场说明"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        with self.SessionLocal() as db:
            row = db.get(VisitFeedback, feedback_id)
            self.assertEqual(row.follow_up_status, "resolved")
            audit = db.scalar(select(AuditLog).where(
                AuditLog.entity_type == "visit_feedback",
                AuditLog.entity_id == str(feedback_id),
            ))
            self.assertIsNotNone(audit)

    def test_store_staff_cannot_read_feedback_inbox(self):
        response = self.client.get(
            "/api/v1/admin/v2/feedback",
            headers=self.manager_headers("visit-feedback-staff"),
        )
        self.assertEqual(response.status_code, 403, response.text)


if __name__ == "__main__":
    unittest.main()
