import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import CustomerProfileRecord, PositionOccupancy, SelectionSession, Staff, Store, User
from app.models.operations import Room, Technician


class TestTechnicianServiceHistoryApi:
    def setup_method(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            store = Store(store_code="history-store", name="历史测试店", address="测试地址")
            customer = User(
                openid="history-customer",
                nickname="悦客",
                phone="13800000000",
                is_member=True,
                member_type="annual",
            )
            tech_a = Technician(store_id=1, code="HISTORY-A", name="技师甲", status="available")
            tech_b = Technician(store_id=1, code="HISTORY-B", name="技师乙", status="available")
            db.add_all([store, customer, tech_a, tech_b])
            db.flush()
            tech_a.store_id = store.id
            tech_b.store_id = store.id
            staff_a = Staff(
                username="history-a",
                password_hash=hash_password("tech-pass"),
                name="技师甲",
                role="technician",
                status="active",
                store_id=store.id,
                technician_id=tech_a.id,
            )
            staff_b = Staff(
                username="history-b",
                password_hash=hash_password("tech-pass"),
                name="技师乙",
                role="technician",
                status="active",
                store_id=store.id,
                technician_id=tech_b.id,
            )
            room = Room(
                store_id=store.id,
                code="HISTORY-SOFA",
                name="大厅沙发 1",
                room_type="sofa",
                status="occupied",
            )
            session = SelectionSession(
                id="history-session",
                access_token_hash="history-token",
                store_id=store.id,
                customer_id=customer.id,
                status="submitted",
                items=[{
                    "name": "舒缓泡脚",
                    "quantity": 1,
                    "store_price_cents": 999999,
                    "member_price_cents": 888888,
                    "customer_note": "不得返回的自由原话",
                }],
                pricing_snapshot={"membership": "annual", "total_cents": 999999},
            )
            db.add_all([staff_a, staff_b, room, session])
            db.flush()
            occupancy = PositionOccupancy(
                store_id=store.id,
                room_id=room.id,
                active_room_id=room.id,
                selection_session_id=session.id,
                active_session_id=session.id,
                status="waiting_service",
            )
            db.add(occupancy)
            db.commit()
            self.occupancy_id = occupancy.id
            self.store_id = store.id
            self.customer_id = customer.id
            self.tech_a_id = tech_a.id
            self.tech_b_id = tech_b.id
            self.staff_a_id = staff_a.id
            self.staff_b_id = staff_b.id

        app.dependency_overrides[get_db] = self._override_get_db
        self.client = TestClient(app)
        self.tech_a_headers = {
            "Authorization": f"Bearer {create_staff_token(self.staff_a_id, 'technician')}"
        }
        self.tech_b_headers = {
            "Authorization": f"Bearer {create_staff_token(self.staff_b_id, 'technician')}"
        }

    def teardown_method(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()

    def _override_get_db(self):
        with self.SessionLocal() as db:
            yield db

    def test_confirm_binds_technician_and_history_returns_only_own_finished_services(self):
        confirmed = self.client.post(
            f"/api/v1/technician/occupancies/{self.occupancy_id}/confirm",
            json={"idempotency_key": "history-confirm-a"},
            headers=self.tech_a_headers,
        )
        assert confirmed.status_code == 200, confirmed.text
        with self.SessionLocal() as db:
            occupancy = db.get(PositionOccupancy, self.occupancy_id)
            assert occupancy.serviced_by_technician_id == self.tech_a_id

        finished = self.client.post(
            f"/api/v1/technician/occupancies/{self.occupancy_id}/finish",
            json={"idempotency_key": "history-finish-a"},
            headers=self.tech_a_headers,
        )
        assert finished.status_code == 200, finished.text

        own = self.client.get(
            "/api/v1/technician/service-history",
            headers=self.tech_a_headers,
        )
        other = self.client.get(
            "/api/v1/technician/service-history",
            headers=self.tech_b_headers,
        )
        assert own.status_code == 200, own.text
        assert own.json()["total"] == 1
        assert other.status_code == 200, other.text
        assert other.json()["total"] == 0

    def test_finish_rejects_a_different_technician_and_keeps_owner_after_service_end(self):
        confirmed = self.client.post(
            f"/api/v1/technician/occupancies/{self.occupancy_id}/confirm",
            json={"idempotency_key": "history-owner-confirm"},
            headers=self.tech_a_headers,
        )
        assert confirmed.status_code == 200, confirmed.text

        rejected = self.client.post(
            f"/api/v1/technician/occupancies/{self.occupancy_id}/finish",
            json={"idempotency_key": "history-owner-finish-b"},
            headers=self.tech_b_headers,
        )
        assert rejected.status_code == 409, rejected.text
        assert rejected.json()["detail"]["code"] == "TECHNICIAN_SERVICE_OWNER_MISMATCH"

        finished = self.client.post(
            f"/api/v1/technician/occupancies/{self.occupancy_id}/finish",
            json={"idempotency_key": "history-owner-finish-a"},
            headers=self.tech_a_headers,
        )
        assert finished.status_code == 200, finished.text
        with self.SessionLocal() as db:
            occupancy = db.get(PositionOccupancy, self.occupancy_id)
            assert occupancy.serviced_by_technician_id == self.tech_a_id
            assert occupancy.actual_service_end_at is not None

    def test_confirm_rejects_when_another_technician_claimed_owner_first(self):
        # Simulate a competing writer having won before this request's
        # conditional NULL-only ownership update; the losing branch must not
        # overwrite the owner.
        with self.SessionLocal() as db:
            occupancy = db.get(PositionOccupancy, self.occupancy_id)
            occupancy.serviced_by_technician_id = self.tech_b_id
            db.commit()

        rejected = self.client.post(
            f"/api/v1/technician/occupancies/{self.occupancy_id}/confirm",
            json={"idempotency_key": "history-owner-race-a"},
            headers=self.tech_a_headers,
        )

        assert rejected.status_code == 409, rejected.text
        assert rejected.json()["detail"]["code"] == "TECHNICIAN_SERVICE_OWNER_MISMATCH"
        with self.SessionLocal() as db:
            occupancy = db.get(PositionOccupancy, self.occupancy_id)
            assert occupancy.serviced_by_technician_id == self.tech_b_id

    def test_history_returns_only_whitelisted_service_and_confirmed_profile_fields(self):
        self.client.post(
            f"/api/v1/technician/occupancies/{self.occupancy_id}/confirm",
            json={"idempotency_key": "history-safe-confirm"},
            headers=self.tech_a_headers,
        )
        with self.SessionLocal() as db:
            occupancy = db.get(PositionOccupancy, self.occupancy_id)
            occupancy.actual_start_at = datetime.now(timezone.utc) - timedelta(minutes=65)
            db.add(CustomerProfileRecord(
                store_id=self.store_id,
                user_id=self.customer_id,
                selection_session_id="history-session",
                technician_id=self.tech_a_id,
                created_by_staff_id=self.staff_a_id,
                schema_version=3,
                taxonomy_version="service_reference_v2",
                customer_confirmed=True,
                confirmed_at=datetime.now(timezone.utc),
                profile={
                    "schema_version": 3,
                    "taxonomy_version": "service_reference_v2",
                    "customer_reported": {
                        "personal_context": {"age_band": "25_34", "build": "balanced"},
                        "work_lifestyle": {"occupation_contexts": ["desk_work"]},
                        "service_related_context": {
                            "contexts": ["medication_mentioned"],
                            "quote": "正在服用某药",
                        },
                    },
                    "technician_observed": {"session_response": {"relaxation": "gradual"}},
                    "next_visit": {},
                },
            ))
            db.add(CustomerProfileRecord(
                store_id=self.store_id,
                user_id=self.customer_id,
                selection_session_id="history-session",
                technician_id=self.tech_b_id,
                created_by_staff_id=self.staff_b_id,
                schema_version=3,
                taxonomy_version="service_reference_v2",
                customer_confirmed=True,
                confirmed_at=datetime.now(timezone.utc),
                profile={
                    "schema_version": 3,
                    "taxonomy_version": "service_reference_v2",
                    "customer_reported": {
                        "work_lifestyle": {"occupation_contexts": ["standing_work"]},
                    },
                    "technician_observed": {"session_response": {"relaxation": "tense"}},
                },
            ))
            db.commit()
        self.client.post(
            f"/api/v1/technician/occupancies/{self.occupancy_id}/finish",
            json={"idempotency_key": "history-safe-finish"},
            headers=self.tech_a_headers,
        )

        response = self.client.get(
            "/api/v1/technician/service-history?profile_status=confirmed",
            headers=self.tech_a_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["occupancy_id"] == self.occupancy_id
        assert item["duration_minutes"] >= 65
        assert item["profile_status"] == "confirmed"
        assert item["customer"] == {"display_name": f"顾客 #{self.customer_id}"}
        assert item["projects"] == ["舒缓泡脚"]
        assert item["service_position"] == "大厅沙发 1"
        assert item["profile_summary"] == {
            "schema_version": 3,
            "taxonomy_version": "service_reference_v2",
            "occupation_contexts": ["久坐办公"],
            "relaxation": "逐渐",
        }
        serialized = response.text
        for forbidden in (
            "13800000000",
            "999999",
            "888888",
            "annual",
            "不得返回的自由原话",
            "正在服用某药",
            "medication_mentioned",
            "age_band",
            "build",
            "phone",
            "member",
            "price",
        ):
            assert forbidden not in serialized


def test_legacy_backfill_only_assigns_a_unique_audited_technician():
    project_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
        database_path = Path(directory) / "legacy-history.db"
        database_url = f"sqlite:///{database_path}"
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE stores (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE technicians (id INTEGER PRIMARY KEY, store_id INTEGER)"))
            connection.execute(text("CREATE TABLE staff (id INTEGER PRIMARY KEY, store_id INTEGER, technician_id INTEGER)"))
            connection.execute(text("CREATE TABLE position_occupancies (id INTEGER PRIMARY KEY, store_id INTEGER, actual_service_end_at DATETIME)"))
            connection.execute(text("CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, actor_type VARCHAR(16), actor_id VARCHAR(64), store_id INTEGER, action VARCHAR(64), entity_type VARCHAR(32), entity_id VARCHAR(64))"))
            connection.execute(text("INSERT INTO stores(id) VALUES (1)"))
            connection.execute(text("INSERT INTO technicians(id, store_id) VALUES (11, 1), (12, 1)"))
            connection.execute(text("INSERT INTO staff(id, store_id, technician_id) VALUES (21, 1, 11), (22, 1, 12)"))
            connection.execute(text("INSERT INTO position_occupancies(id, store_id, actual_service_end_at) VALUES (31, 1, CURRENT_TIMESTAMP), (32, 1, CURRENT_TIMESTAMP), (33, 1, CURRENT_TIMESTAMP), (34, 1, CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO audit_logs(id, actor_type, actor_id, store_id, action, entity_type, entity_id) VALUES (1, 'staff', '21', 1, 'technician_confirm_service', 'position_occupancy', '31'), (2, 'staff', '21', 1, 'technician_finish_service', 'position_occupancy', '31'), (3, 'staff', '21', 1, 'technician_confirm_service', 'position_occupancy', '32'), (4, 'staff', '22', 1, 'technician_finish_service', 'position_occupancy', '32'), (5, 'staff', '21', 1, 'technician_confirm_service', 'position_occupancy', '34'), (6, 'staff', '999', 1, 'technician_finish_service', 'position_occupancy', '34')"))
        engine.dispose()

        env = os.environ.copy()
        env["DATABASE_URL"] = database_url
        stamped = subprocess.run(
            [sys.executable, "-m", "alembic", "stamp", "20260904_service_reference_v2"],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert stamped.returncode == 0, stamped.stderr
        upgraded = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert upgraded.returncode == 0, upgraded.stderr

        engine = create_engine(database_url)
        assert "serviced_by_technician_id" in {
            column["name"] for column in inspect(engine).get_columns("position_occupancies")
        }
        with engine.connect() as connection:
            rows = dict(connection.execute(text(
                "SELECT id, serviced_by_technician_id FROM position_occupancies ORDER BY id"
            )).tuples().all())
        engine.dispose()
        assert rows == {31: 11, 32: None, 33: None, 34: None}
