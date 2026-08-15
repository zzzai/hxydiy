import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.domain.business_closure import (
    BusinessClosureState,
    ResourceBusy,
    StateConflict,
    apply_action,
)
from app.main import app
from app.models import Order, PositionOccupancy, Project, SelectionSession, Staff, Store, User
from app.models.operations import Room, Technician
from app.models.service import ServiceAssignment, ServiceOrder, StateTransition, Visit


class BusinessClosureStateMachineTests(unittest.TestCase):
    def waiting_state(self, **overrides) -> BusinessClosureState:
        values = {
            "order": "checked_in",
            "visit": "waiting_assignment",
            "service_order": "draft",
            "technician": "available",
            "room": "available",
        }
        values.update(overrides)
        return BusinessClosureState(**values)

    def test_cannot_start_service_before_assignment(self):
        with self.assertRaisesRegex(StateConflict, "start_service"):
            apply_action(self.waiting_state(), "start_service")

    def test_assignment_reserves_technician_and_room(self):
        result = apply_action(self.waiting_state(), "assign")

        self.assertEqual(result.visit, "assigned")
        self.assertEqual(result.service_order, "assigned")
        self.assertEqual(result.technician, "reserved")
        self.assertEqual(result.room, "reserved")

    def test_busy_technician_cannot_be_assigned(self):
        with self.assertRaisesRegex(ResourceBusy, "technician"):
            apply_action(
                self.waiting_state(technician="in_service"),
                "assign",
            )

    def test_busy_room_cannot_be_assigned(self):
        with self.assertRaisesRegex(ResourceBusy, "room"):
            apply_action(
                self.waiting_state(room="in_service"),
                "assign",
            )

    def test_start_service_updates_all_active_objects(self):
        assigned = apply_action(self.waiting_state(), "assign")
        result = apply_action(assigned, "start_service")

        self.assertEqual(result.order, "in_service")
        self.assertEqual(result.visit, "in_service")
        self.assertEqual(result.service_order, "in_service")
        self.assertEqual(result.technician, "in_service")
        self.assertEqual(result.room, "in_service")

    def test_finish_service_releases_technician_and_waits_for_checkout(self):
        assigned = apply_action(self.waiting_state(), "assign")
        in_service = apply_action(assigned, "start_service")
        result = apply_action(in_service, "finish_service")

        self.assertEqual(result.order, "pending_checkout")
        self.assertEqual(result.visit, "pending_checkout")
        self.assertEqual(result.service_order, "pending_checkout")
        self.assertEqual(result.technician, "available")
        self.assertEqual(result.room, "pending_checkout")

    def test_settlement_completes_business_objects_and_starts_cleaning(self):
        state = self.waiting_state()
        for action in ("assign", "start_service", "finish_service", "settle"):
            state = apply_action(state, action)

        self.assertEqual(state.order, "completed")
        self.assertEqual(state.visit, "completed")
        self.assertEqual(state.service_order, "completed")
        self.assertEqual(state.technician, "available")
        self.assertEqual(state.room, "cleaning")

    def test_room_only_becomes_available_after_cleaning(self):
        state = self.waiting_state()
        for action in ("assign", "start_service", "finish_service", "settle"):
            state = apply_action(state, action)

        result = apply_action(state, "finish_cleaning")
        self.assertEqual(result.room, "available")

    def test_same_action_is_idempotent_only_for_explicit_replay(self):
        assigned = apply_action(self.waiting_state(), "assign")

        with self.assertRaises(StateConflict):
            apply_action(assigned, "assign")

        self.assertEqual(apply_action(assigned, "assign", replay=True), assigned)


class BusinessClosureApiContractTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        Base.metadata.create_all(self.engine)

        with self.SessionLocal() as db:
            store = Store(store_code="closure-store", name="闭环测试店", address="测试地址")
            db.add(store)
            db.flush()
            staff = Staff(
                username="closure-admin",
                password_hash=hash_password("test-pass"),
                name="测试前台",
                role="admin",
                store_id=store.id,
            )
            user = User(openid="closure-user")
            db.add_all([staff, user])
            db.flush()
            project = Project(
                store_id=store.id,
                code="CLOSURE-PROJECT",
                category="balance",
                name="闭环测试项目",
                publication_status="published",
            )
            room = Room(
                store_id=store.id,
                code="CLOSURE-ROOM",
                name="闭环测试房间",
                capacity=1,
                status="available",
            )
            technician = Technician(
                store_id=store.id,
                code="CLOSURE-TECH",
                name="闭环测试技师",
                status="available",
            )
            db.add_all([project, room, technician])
            db.flush()
            order = Order(
                order_no="CLOSURE-ORDER-1",
                order_type="service",
                user_id=user.id,
                store_id=store.id,
                items=[{"project_id": project.id, "name": project.name}],
                pay_amount_cents=9900,
                pay_status="paid",
                status="paid",
            )
            second_order = Order(
                order_no="CLOSURE-ORDER-2",
                order_type="service",
                user_id=user.id,
                store_id=store.id,
                items=[{"project_id": project.id, "name": project.name}],
                pay_amount_cents=9900,
                pay_status="paid",
                status="paid",
            )
            db.add_all([order, second_order])
            db.commit()
            self.store_id = store.id
            self.staff_id = staff.id
            self.order_id = order.id
            self.second_order_id = second_order.id
            self.project_id = project.id
            self.room_id = room.id
            self.technician_id = technician.id

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.headers = {
            "Authorization": f"Bearer {create_staff_token(self.staff_id, 'admin')}"
        }

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def post(self, path: str, body: dict):
        return self.client.post(path, json=body, headers=self.headers)

    def check_in(self, order_id: int, key: str):
        return self.post(
            f"/api/v1/operations/orders/{order_id}/check-in",
            {"idempotency_key": key},
        )

    def check_in_walk_in(self, key: str):
        return self.post(
            "/api/v1/operations/visits/check-in",
            {"idempotency_key": key},
        )

    def assign(self, visit_id: int, key: str):
        return self.post(
            f"/api/v1/operations/visits/{visit_id}/assign",
            {
                "idempotency_key": key,
                "technician_id": self.technician_id,
                "room_id": self.room_id,
                "project_ids": [self.project_id],
            },
        )

    def test_walk_in_customer_can_check_in_without_an_order(self):
        response = self.check_in_walk_in("walk-in-1")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["visit_status"], "waiting_project")
        self.assertEqual(response.json()["source"], "walk_in")
        self.assertIsNone(response.json()["order_id"])
        self.assertIsNone(response.json()["service_order_id"])

    def test_complete_flow_is_atomic_and_idempotent(self):
        check_in = self.check_in(self.order_id, "check-in-1")
        self.assertEqual(check_in.status_code, 200, check_in.text)
        visit_id = check_in.json()["visit_id"]
        service_order_id = check_in.json()["service_order_id"]

        replay = self.check_in(self.order_id, "check-in-1")
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), check_in.json())

        assigned = self.assign(visit_id, "assign-1")
        self.assertEqual(assigned.status_code, 200, assigned.text)
        assignment_id = assigned.json()["assignment_id"]

        ready = self.post(
            f"/api/v1/operations/service-orders/{service_order_id}/ready",
            {"idempotency_key": "ready-1"},
        )
        self.assertEqual(ready.status_code, 200, ready.text)
        self.assertEqual(ready.json()["service_order_status"], "ready")
        self.assertEqual(ready.json()["room_status"], "occupied")

        started = self.post(
            f"/api/v1/operations/service-orders/{service_order_id}/start",
            {"idempotency_key": "start-1"},
        )
        self.assertEqual(started.status_code, 200, started.text)

        finished = self.post(
            f"/api/v1/operations/service-orders/{service_order_id}/finish",
            {"idempotency_key": "finish-1"},
        )
        self.assertEqual(finished.status_code, 200, finished.text)

        settled = self.post(
            f"/api/v1/operations/service-orders/{service_order_id}/settle",
            {
                "idempotency_key": "settle-1",
                "payment_method": "wechat",
                "received_amount_cents": 9900,
                "payment_reference": "TEST-PAYMENT-1",
            },
        )
        self.assertEqual(settled.status_code, 200, settled.text)

        cleaned = self.post(
            f"/api/v1/operations/rooms/{self.room_id}/finish-cleaning",
            {"idempotency_key": "clean-1"},
        )
        self.assertEqual(cleaned.status_code, 200, cleaned.text)

        with self.SessionLocal() as db:
            order = db.get(Order, self.order_id)
            visit = db.get(Visit, visit_id)
            service_order = db.get(ServiceOrder, service_order_id)
            assignment = db.get(ServiceAssignment, assignment_id)
            room = db.get(Room, self.room_id)
            technician = db.get(Technician, self.technician_id)
            transition_count = db.scalar(select(func.count(StateTransition.id)))

            self.assertEqual(order.status, "completed")
            self.assertEqual(visit.status, "completed")
            self.assertEqual(service_order.status, "completed")
            self.assertEqual(assignment.status, "completed")
            self.assertEqual(room.status, "available")
            self.assertEqual(technician.status, "available")
            self.assertEqual(transition_count, 7)

    def test_active_resources_cannot_be_assigned_twice(self):
        first_visit_id = self.check_in(self.order_id, "check-in-first").json()["visit_id"]
        second_visit_id = self.check_in(
            self.second_order_id,
            "check-in-second",
        ).json()["visit_id"]
        first_assignment = self.assign(first_visit_id, "assign-first")
        self.assertEqual(first_assignment.status_code, 200, first_assignment.text)

        conflict = self.assign(second_visit_id, "assign-second")
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["detail"]["code"], "RESOURCE_BUSY")

    def test_legacy_assignment_cannot_use_a_service_position_with_active_diy_occupancy(self):
        with self.SessionLocal() as db:
            session = SelectionSession(
                id="closure-diy-occupancy",
                access_token_hash="test-token-hash",
                store_id=self.store_id,
                status="submitted",
            )
            db.add(session)
            db.flush()
            db.add(PositionOccupancy(
                store_id=self.store_id,
                room_id=self.room_id,
                active_room_id=self.room_id,
                selection_session_id=session.id,
                active_session_id=session.id,
                status="waiting_service",
                source="personal_qr",
            ))
            db.commit()

        visit_id = self.check_in(self.order_id, "check-in-diy-position").json()["visit_id"]
        response = self.assign(visit_id, "assign-diy-position")

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "DIY_POSITION_OCCUPIED")
        with self.SessionLocal() as db:
            room = db.get(Room, self.room_id)
            self.assertEqual(room.status, "available")
            self.assertEqual(db.scalar(select(func.count(ServiceAssignment.id))), 0)

    def test_live_board_returns_current_store_visits(self):
        visit_id = self.check_in(self.order_id, "check-in-board").json()["visit_id"]

        response = self.client.get(
            "/api/v1/operations/live-board",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["summary"]["waiting_assignment"], 1)
        self.assertEqual(response.json()["summary"]["in_service"], 0)
        self.assertEqual(response.json()["visits"][0]["id"], visit_id)
        self.assertEqual(response.json()["visits"][0]["order_no"], "CLOSURE-ORDER-1")
        self.assertEqual(response.json()["visits"][0]["service_order_status"], "draft")

    def test_live_board_only_allows_cleaning_for_completed_service(self):
        with self.SessionLocal() as db:
            room = db.get(Room, self.room_id)
            room.status = "cleaning"
            db.commit()

        orphan_response = self.client.get(
            "/api/v1/operations/live-board",
            headers=self.headers,
        )

        self.assertEqual(orphan_response.status_code, 200, orphan_response.text)
        orphan_room = next(
            item for item in orphan_response.json()["resources"]["rooms"]
            if item["id"] == self.room_id
        )
        self.assertFalse(orphan_room["can_finish_cleaning"])

        with self.SessionLocal() as db:
            room = db.get(Room, self.room_id)
            room.status = "available"
            db.commit()

        checked_in = self.check_in(self.order_id, "check-in-cleanable").json()
        self.assign(checked_in["visit_id"], "assign-cleanable")
        service_order_id = checked_in["service_order_id"]
        self.post(
            f"/api/v1/operations/service-orders/{service_order_id}/ready",
            {"idempotency_key": "ready-cleanable"},
        )
        self.post(
            f"/api/v1/operations/service-orders/{service_order_id}/start",
            {"idempotency_key": "start-cleanable"},
        )
        self.post(
            f"/api/v1/operations/service-orders/{service_order_id}/finish",
            {"idempotency_key": "finish-cleanable"},
        )
        self.post(
            f"/api/v1/operations/service-orders/{service_order_id}/settle",
            {
                "idempotency_key": "settle-cleanable",
                "payment_method": "wechat",
                "received_amount_cents": 9900,
                "payment_reference": "TEST-CLEANABLE",
            },
        )

        cleanable_response = self.client.get(
            "/api/v1/operations/live-board",
            headers=self.headers,
        )
        self.assertEqual(cleanable_response.status_code, 200, cleanable_response.text)
        cleanable_room = next(
            item for item in cleanable_response.json()["resources"]["rooms"]
            if item["id"] == self.room_id
        )
        self.assertTrue(cleanable_room["can_finish_cleaning"])


if __name__ == "__main__":
    unittest.main()
