import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import PositionOccupancy, PriceBook, Project, Room, SelectionChangeRequest, SelectionRevision, SelectionSession, ServiceFeedback, ServiceLine, Staff, Store, User


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

    def test_front_desk_confirmation_freezes_tuesday_member_price_in_revision(self):
        session_id = "selection-admin-tuesday-confirm"
        revision_id = "selection-admin-tuesday-revision"
        with self.SessionLocal() as db:
            project = Project(
                store_id=self.store_id,
                code="selection-admin-tuesday-project",
                category="care",
                name="周二确认项目",
                publication_status="published",
            )
            user = User(
                openid="selection_admin_tuesday_member",
                nickname="周二会员",
                is_member=True,
                member_type="annual",
                member_expire_at=datetime(2027, 8, 18, tzinfo=timezone.utc),
            )
            db.add_all([project, user])
            db.flush()
            db.add_all([
                PriceBook(project_id=project.id, price_type="store", amount_cents=10000),
                PriceBook(project_id=project.id, price_type="group", amount_cents=9000),
                PriceBook(project_id=project.id, price_type="member", amount_cents=8000),
            ])
            item = {"project_id": project.id, "quantity": 1, "name": project.name}
            session = SelectionSession(
                id=session_id,
                access_token_hash="x",
                store_id=self.store_id,
                customer_id=user.id,
                source="personal_qr",
                device_label="顾客手机",
                status="submitted",
                items=[item],
                diy_preferences={},
                pricing_snapshot={"payable_total_cents": 8000},
            )
            revision = SelectionRevision(
                id=revision_id,
                selection_session_id=session_id,
                revision_no=1,
                state="submitted",
                idempotency_key="selection-admin-tuesday-key",
                snapshot={
                    "items": [item],
                    "pricing": {"payable_total_cents": 8000},
                    "source_marker": "preserve-me",
                },
            )
            db.add_all([session, revision])
            db.commit()

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                frozen = datetime(2026, 8, 18, 2, 0, tzinfo=timezone.utc)
                return frozen if tz is None else frozen.astimezone(tz)

        with patch("app.api.admin_v2.datetime", FrozenDateTime):
            response = self.client.post(
                f"/api/v1/admin/v2/selection-sessions/{session_id}/confirm",
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["pricing_snapshot"]["payable_total_cents"], 6800)
        self.assertEqual(body["pricing_snapshot"]["lines"][0]["price_basis"], "tuesday_68")
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            revision = db.get(SelectionRevision, revision_id)
            line = db.query(ServiceLine).filter_by(selection_session_id=session_id).one()
            self.assertEqual(session.pricing_snapshot["payable_total_cents"], 6800)
            self.assertEqual(revision.snapshot["pricing"]["payable_total_cents"], 6800)
            self.assertEqual(revision.snapshot["items"], session.items)
            self.assertEqual(revision.snapshot["source_marker"], "preserve-me")
            self.assertEqual(line.snapshot, session.items[0])
            self.assertEqual(revision.confirmed_at, session.confirmed_at)

    def test_front_desk_confirmation_rejects_project_without_price_book(self):
        session_id = "selection-admin-missing-price"
        revision_id = "selection-admin-missing-price-revision"
        with self.SessionLocal() as db:
            project = Project(
                store_id=self.store_id,
                code="selection-admin-missing-price-project",
                category="care",
                name="缺少价格项目",
                publication_status="published",
            )
            db.add(project)
            db.flush()
            item = {"project_id": project.id, "quantity": 1, "name": project.name}
            db.add_all([
                SelectionSession(
                    id=session_id,
                    access_token_hash="x",
                    store_id=self.store_id,
                    source="personal_qr",
                    status="submitted",
                    items=[item],
                    diy_preferences={},
                ),
                SelectionRevision(
                    id=revision_id,
                    selection_session_id=session_id,
                    revision_no=1,
                    state="submitted",
                    idempotency_key="selection-admin-missing-price-key",
                    snapshot={"items": [item], "pricing": {"payable_total_cents": 0}},
                ),
            ])
            db.commit()

        response = self.client.post(
            f"/api/v1/admin/v2/selection-sessions/{session_id}/confirm",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 409, response.text)
        with self.SessionLocal() as db:
            self.assertEqual(db.get(SelectionSession, session_id).status, "submitted")
            self.assertEqual(db.get(SelectionRevision, revision_id).state, "submitted")
            self.assertEqual(
                db.query(ServiceLine).filter_by(selection_session_id=session_id).count(),
                0,
            )

    def test_front_desk_confirmation_accepts_explicit_zero_price_book(self):
        session_id = "selection-admin-explicit-zero-price"
        revision_id = "selection-admin-explicit-zero-revision"
        with self.SessionLocal() as db:
            project = Project(
                store_id=self.store_id,
                code="selection-admin-explicit-zero-project",
                category="care",
                name="显式零元项目",
                publication_status="published",
            )
            db.add(project)
            db.flush()
            db.add(PriceBook(project_id=project.id, price_type="store", amount_cents=0))
            item = {"project_id": project.id, "quantity": 1, "name": project.name}
            db.add_all([
                SelectionSession(
                    id=session_id,
                    access_token_hash="x",
                    store_id=self.store_id,
                    source="personal_qr",
                    status="submitted",
                    items=[item],
                    diy_preferences={},
                ),
                SelectionRevision(
                    id=revision_id,
                    selection_session_id=session_id,
                    revision_no=1,
                    state="submitted",
                    idempotency_key="selection-admin-explicit-zero-key",
                    snapshot={"items": [item], "pricing": {"payable_total_cents": 0}},
                ),
            ])
            db.commit()

        response = self.client.post(
            f"/api/v1/admin/v2/selection-sessions/{session_id}/confirm",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["pricing_snapshot"]["payable_total_cents"], 0)
        with self.SessionLocal() as db:
            self.assertEqual(db.get(SelectionRevision, revision_id).state, "confirmed")
            self.assertEqual(
                db.query(ServiceLine).filter_by(selection_session_id=session_id).count(),
                1,
            )

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
