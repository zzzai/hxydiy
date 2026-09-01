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
