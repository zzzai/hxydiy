import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import PositionOccupancy, Room, SelectionChangeRequest, SelectionRevision, SelectionSession, ServiceFeedback, Staff, Store, User


class SelectionAdminApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            store = Store(store_code="selection-admin-store", name="选单门店", address="测试地址")
            staff = Staff(
                username="selection-admin", name="店长", role="admin", status="active",
                password_hash=hash_password("pass"), store_id=None,
            )
            db.add_all([store, staff])
            db.flush()
            staff.store_id = store.id
            room = Room(
                store_id=store.id,
                code="selection-admin-sofa",
                name="测试沙发",
                room_type="sofa",
                room_group="sofa",
                customer_label="测试沙发",
                customer_selectable=True,
                operational_status="active",
            )
            db.add(room)
            db.flush()
            session = SelectionSession(
                id="selection-admin-session", access_token_hash="x", store_id=store.id,
                source="tablet", device_label="门店平板", status="submitted",
                items=[{"project_id": 1, "quantity": 1, "diy_preferences": ["肩颈"]}],
                diy_preferences={},
            )
            db.add(session)
            db.commit()
            cls.store_id = store.id
            cls.staff_id = staff.id
            cls.room_id = room.id

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        cls.headers = {"Authorization": f"Bearer {create_staff_token(cls.staff_id, 'admin')}"}

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def test_staff_can_list_and_confirm_selection(self):
        listed = self.client.get("/api/v1/admin/v2/selection-sessions", headers=self.headers)
        self.assertEqual(listed.status_code, 200)
        self.assertGreaterEqual(listed.json()["total"], 1)
        initial = next(item for item in listed.json()["items"] if item["id"] == "selection-admin-session")
        self.assertEqual(initial["device_label"], "门店平板")

        with self.SessionLocal() as db:
            db.add(SelectionSession(
                id="selection-admin-confirm", access_token_hash="x", store_id=self.store_id,
                source="mini_program", device_label="顾客手机", status="submitted", items=[], diy_preferences={},
            ))
            db.commit()
        confirmed = self.client.post(
            "/api/v1/admin/v2/selection-sessions/selection-admin-confirm/confirm",
            headers=self.headers,
        )
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["status"], "confirmed")

    def test_confirmed_selection_can_be_cancelled(self):
        with self.SessionLocal() as db:
            db.add(SelectionSession(
                id="selection-admin-cancel", access_token_hash="x", store_id=self.store_id,
                source="tablet", device_label="门店平板", status="confirmed", items=[], diy_preferences={},
            ))
            db.commit()
        response = self.client.post(
            "/api/v1/admin/v2/selection-sessions/selection-admin-cancel/cancel",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")

    def test_staff_can_list_pending_service_additions_for_own_store(self):
        with self.SessionLocal() as db:
            session = SelectionSession(
                id="selection-admin-change", access_token_hash="x", store_id=self.store_id,
                source="personal_qr", device_label="顾客手机", status="confirmed", items=[], diy_preferences={},
            )
            revision = SelectionRevision(
                id="selection-admin-change-revision",
                selection_session_id=session.id,
                revision_no=2,
                state="awaiting_staff_confirmation",
                idempotency_key="selection-admin-change-key",
                snapshot={
                    "added_items": [{"name": "肩颈加强", "quantity": 1, "diy_preferences": ["舒缓"]}],
                    "pricing": {"payable_total_cents": 1200},
                },
            )
            change = SelectionChangeRequest(
                id="selection-admin-change-request",
                selection_session_id=session.id,
                selection_revision_id=revision.id,
                state="awaiting_staff_confirmation",
            )
            db.add_all([session, revision, change])
            db.commit()

        response = self.client.get(
            "/api/v1/admin/v2/selection-change-requests",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        request = next(item for item in response.json()["items"] if item["id"] == "selection-admin-change-request")
        self.assertEqual(request["state"], "awaiting_staff_confirmation")
        self.assertEqual(request["selection"]["id"], "selection-admin-change")
        self.assertEqual(request["revision"]["revision_no"], 2)
        self.assertEqual(request["revision"]["added_items"][0]["name"], "肩颈加强")

    def test_staff_cannot_list_pending_additions_from_another_store(self):
        with self.SessionLocal() as db:
            other_store = Store(store_code="selection-admin-other-store", name="其他门店", address="其他地址")
            db.add(other_store)
            db.flush()
            session = SelectionSession(
                id="selection-admin-other-change", access_token_hash="x", store_id=other_store.id,
                source="personal_qr", device_label="顾客手机", status="confirmed", items=[], diy_preferences={},
            )
            revision = SelectionRevision(
                id="selection-admin-other-revision", selection_session_id=session.id, revision_no=2,
                state="awaiting_staff_confirmation", idempotency_key="selection-admin-other-key",
                snapshot={"added_items": [{"name": "其他门店项目"}]},
            )
            db.add_all([session, revision, SelectionChangeRequest(
                id="selection-admin-other-request", selection_session_id=session.id,
                selection_revision_id=revision.id, state="awaiting_staff_confirmation",
            )])
            db.commit()

        response = self.client.get(
            "/api/v1/admin/v2/selection-change-requests",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("selection-admin-other-request", [item["id"] for item in response.json()["items"]])

    def test_selection_list_exposes_bound_customer_identity(self):
        with self.SessionLocal() as db:
            user = User(openid="h5_selection_customer", phone="13600136000", nickname="张女士", is_member=True)
            db.add(user)
            db.flush()
            db.add(SelectionSession(
                id="selection-admin-customer", access_token_hash="x", store_id=self.store_id,
                customer_id=user.id, source="personal_qr", device_label="顾客手机",
                status="submitted", items=[], diy_preferences={},
            ))
            db.commit()

        response = self.client.get(
            "/api/v1/admin/v2/selection-sessions",
            params={"status": "submitted"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        record = next(item for item in response.json()["items"] if item["id"] == "selection-admin-customer")
        self.assertEqual(record["customer"]["phone"], "13600136000")
        self.assertEqual(record["customer"]["nickname"], "张女士")
        self.assertEqual(record["customer"]["is_member"], True)

    def test_selection_list_exposes_pricing_snapshot_for_counter_settlement(self):
        with self.SessionLocal() as db:
            db.add(SelectionSession(
                id="selection-admin-pricing", access_token_hash="x", store_id=self.store_id,
                source="personal_qr", device_label="顾客手机", status="submitted", items=[], diy_preferences={},
                store_total_cents=14800, member_total_cents=9800,
                pricing_snapshot={
                    "applied_price_type": "member",
                    "payable_total_cents": 9800,
                    "promotion_adjustment_cents": -2990,
                },
            ))
            db.commit()

        response = self.client.get("/api/v1/admin/v2/selection-sessions", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        record = next(item for item in response.json()["items"] if item["id"] == "selection-admin-pricing")
        self.assertEqual(record["store_total_cents"], 14800)
        self.assertEqual(record["member_total_cents"], 9800)
        self.assertEqual(record["pricing_snapshot"]["applied_price_type"], "member")
        self.assertEqual(record["pricing_snapshot"]["payable_total_cents"], 9800)

    def test_selection_list_exposes_service_feedback(self):
        with self.SessionLocal() as db:
            session = SelectionSession(
                id="selection-admin-feedback", access_token_hash="x", store_id=self.store_id,
                source="personal_qr", device_label="顾客手机", status="confirmed", items=[], diy_preferences={},
            )
            db.add(session)
            db.flush()
            db.add(ServiceFeedback(
                store_id=self.store_id,
                selection_session_id=session.id,
                rating=5,
                tags=["服务细致", "环境安心"],
                note="体验很好",
            ))
            db.commit()

        response = self.client.get("/api/v1/admin/v2/selection-sessions", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        record = next(item for item in response.json()["items"] if item["id"] == "selection-admin-feedback")
        self.assertEqual(record["feedback"]["rating"], 5)
        self.assertEqual(record["feedback"]["tags"], ["服务细致", "环境安心"])
        self.assertEqual(record["feedback"]["note"], "体验很好")
        self.assertIsNotNone(record["feedback"]["created_at"])

    def test_cancelling_selection_releases_waiting_service_position(self):
        with self.SessionLocal() as db:
            session = SelectionSession(
                id="selection-admin-release", access_token_hash="x", store_id=self.store_id,
                source="personal_qr", device_label="顾客手机", status="submitted", items=[], diy_preferences={},
            )
            db.add(session)
            db.flush()
            occupancy = PositionOccupancy(
                store_id=self.store_id,
                room_id=self.room_id,
                active_room_id=self.room_id,
                selection_session_id=session.id,
                active_session_id=session.id,
                status="waiting_service",
                source="personal_qr",
            )
            db.add(occupancy)
            db.commit()
            occupancy_id = occupancy.id

        response = self.client.post(
            "/api/v1/admin/v2/selection-sessions/selection-admin-release/cancel",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        with self.SessionLocal() as db:
            occupancy = db.get(PositionOccupancy, occupancy_id)
            self.assertEqual(occupancy.status, "released")
            self.assertIsNone(occupancy.active_room_id)
            self.assertEqual(occupancy.release_reason, "选单已取消")


if __name__ == "__main__":
    unittest.main()
