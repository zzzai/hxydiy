"""Synthetic contracts for assigning a submitted selection to its first position."""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token
from app.db.session import Base, get_db
from app.main import app
from app.models import Addon, AuditLog, BrowserInstance, PositionOccupancy, PriceBook, Project, Room, SelectionSession, Staff, Store, Technician, User


class SelectionPositionAssignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.postgres = os.environ.get("HXY_SEAT_OPTIONAL_PG") == "1"
        # This opt-in target is an isolated synthetic test container, never app settings.
        cls.engine = create_engine(
            "postgresql+psycopg://seat_optional_test:seat_optional_test@seat-optional-pg/seat_optional_test"
        ) if cls.postgres else create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)

        def override_db():
            with cls.SessionLocal() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def setUp(self):
        self.client.cookies.clear()
        self.key = uuid4().hex[:16]
        with self.SessionLocal() as db:
            stores = [Store(store_code=f"{self.key}-{n}", name=f"Synthetic store {n}", address="test") for n in (1, 2)]
            db.add_all(stores)
            db.flush()
            self.store_id, self.other_store_id = [store.id for store in stores]
            staff = Staff(username=self.key, name="Test manager", password_hash="unused", role="manager", status="active", store_id=self.store_id)
            readonly = Staff(username=f"staff-{self.key}", name="Test staff", password_hash="unused", role="staff", status="active", store_id=self.store_id)
            db.add_all([staff, readonly])
            project = Project(store_id=self.store_id, code=self.key, name="Synthetic service", category="care", publication_status="published")
            db.add(project)
            db.flush()
            self.project_id = project.id
            addon = Addon(store_id=self.store_id, code=f"addon-{self.key}", name="Synthetic add-on", parent_project_id=project.id, price_cents=1200, publication_status="published")
            db.add(addon)
            db.flush()
            self.addon_id = addon.id
            self.headers = {"Authorization": f"Bearer {create_staff_token(staff.id, 'manager')}"}
            self.readonly_headers = {"Authorization": f"Bearer {create_staff_token(readonly.id, 'staff')}"}
            db.add_all([PriceBook(project_id=project.id, price_type=kind, amount_cents=amount) for kind, amount in (("store", 9900), ("member", 7900), ("group", 8900))])
            room = Room(store_id=self.store_id, code=self.key, name="Synthetic sofa", room_type="sofa", room_group="sofa")
            other = Room(store_id=self.other_store_id, code=f"other-{self.key}", name="Other store sofa", room_type="sofa")
            db.add_all([room, other])
            db.commit()
            self.room_id, self.other_room_id = room.id, other.id

    def selection(self, status="submitted", store_id=None):
        session_id = str(uuid4())
        with self.SessionLocal() as db:
            db.add(SelectionSession(
                id=session_id, store_id=store_id or self.store_id, access_token_hash="test-only",
                status=status, source="in_store",
                items=[{"project_id": self.project_id, "quantity": 1, "diy_preferences": ["gentle"]}],
                diy_preferences={"temperature": "warm"},
                pricing_snapshot={"payable_total_cents": 9900, "marker": "frozen"},
                store_total_cents=9900, member_total_cents=7900,
            ))
            db.commit()
        return session_id

    def assign(self, session_id, room_id=None, headers=None):
        return self.client.post(
            f"/api/v1/admin/v2/selection-sessions/{session_id}/assign-position",
            json={"room_id": room_id or self.room_id},
            headers=self.headers if headers is None else headers,
        )

    def test_anonymous_submit_is_listed_without_creating_an_occupancy(self):
        created = self.client.post("/api/v1/selection-sessions", json={"store_id": self.store_id})
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["session"]["id"]
        headers = {"X-Selection-Token": created.json()["access_token"], "Idempotency-Key": self.key}
        body = {"items": [{"project_id": self.project_id, "quantity": 1, "addon_ids": [self.addon_id], "diy_preferences": ["gentle"]}], "diy_preferences": {"temperature": "warm"}}
        quoted = self.client.post(f"/api/v1/selection-sessions/{session_id}/quote", headers=headers, json=body)
        self.assertEqual(quoted.status_code, 200, quoted.text)
        self.assertEqual(quoted.json()["pricing"]["store_total_cents"], 11100)
        submitted = self.client.post(f"/api/v1/selection-sessions/{session_id}/revisions", headers=headers, json=body)
        self.assertEqual(submitted.status_code, 200, submitted.text)
        repeated = self.client.post(f"/api/v1/selection-sessions/{session_id}/revisions", headers=headers, json=body)
        self.assertEqual(repeated.json()["id"], submitted.json()["id"])
        with self.SessionLocal() as db:
            anonymous_id = db.get(SelectionSession, session_id).customer_id
            self.assertIsNotNone(anonymous_id)
            self.assertTrue(db.get(User, anonymous_id).openid.startswith("anon_"))
            self.assertEqual(db.scalar(select(func.count()).select_from(PositionOccupancy).where(PositionOccupancy.selection_session_id == session_id)), 0)
        listed = self.client.get("/api/v1/admin/v2/selection-sessions", headers=self.headers).json()["items"]
        item = next(item for item in listed if item["id"] == session_id)
        self.assertIn("needs_position_assignment", item)
        self.assertTrue(item["needs_position_assignment"])
        self.assertIsNone(item["position"])
        filtered = self.client.get("/api/v1/admin/v2/selection-sessions?needs_position_assignment=true", headers=self.headers).json()["items"]
        self.assertIn(session_id, [item["id"] for item in filtered])
        self.assertEqual(self.assign(session_id).status_code, 200)
        state = self.client.get(f"/api/v1/selection-sessions/{session_id}/service-status", headers=headers).json()
        self.assertEqual(state["occupancy_status"], "waiting_service")
        self.assertFalse(state["can_evaluate"])
        with self.SessionLocal() as db:
            saved = db.get(SelectionSession, session_id)
            self.assertEqual(saved.diy_preferences, {"temperature": "warm"})
            self.assertEqual(saved.items[0]["addon_ids"], [self.addon_id])
            self.assertEqual(saved.store_total_cents, 11100)

    def test_assigned_bed_is_read_back_only_with_the_original_selection_token(self):
        self.assert_assigned_position_readback("bed", True)

    def test_assigned_nonselectable_sofa_is_read_back_only_with_the_original_selection_token(self):
        self.assert_assigned_position_readback("sofa", False)

    def assert_assigned_position_readback(self, room_type, customer_selectable):
        with self.SessionLocal() as db:
            targets = [Room(
                store_id=self.store_id, code=f"private-{index}-{self.key}",
                name=f"Synthetic private position {index}", room_type=room_type,
                customer_selectable=customer_selectable,
            ) for index in (1, 2)]
            db.add_all(targets)
            db.commit()
            target_ids = [target.id for target in targets]
        sessions = []
        for index, target_id in enumerate(target_ids):
            self.client.cookies.clear()
            created = self.client.post("/api/v1/selection-sessions", json={"store_id": self.store_id})
            self.assertEqual(created.status_code, 200, created.text)
            created = created.json()
            session_id, token = created["session"]["id"], created["access_token"]
            submitted = self.client.post(
                f"/api/v1/selection-sessions/{session_id}/revisions",
                headers={"X-Selection-Token": token, "Idempotency-Key": f"readback-{index}-{self.key}"},
                json={"items": [{"project_id": self.project_id}], "diy_preferences": {}},
            )
            self.assertEqual(submitted.status_code, 200, submitted.text)
            assigned = self.assign(session_id, target_id)
            self.assertEqual(assigned.status_code, 200, assigned.text)
            sessions.append((session_id, token, assigned.json()["id"]))

        map_url = f"/api/v1/stores/{self.store_id}/service-position-map"
        public = self.client.get(map_url)
        self.assertEqual(public.status_code, 200, public.text)
        self.assertEqual([item["id"] for item in public.json()["positions"]], [self.room_id])
        token_without_session = self.client.get(map_url, headers={"X-Selection-Token": sessions[0][1]})
        self.assertEqual(token_without_session.json(), public.json())
        for index, (session_id, token, occupancy_id) in enumerate(sessions):
            for denied_token in (None, "wrong-synthetic-token", sessions[1 - index][1]):
                denied = self.client.get(
                    map_url, params={"session_id": session_id},
                    headers={"X-Selection-Token": denied_token} if denied_token else {},
                )
                self.assertEqual(denied.status_code, 403, denied.text)
                for target_id in target_ids:
                    self.assertNotIn(f'"id":{target_id},', denied.text)

            original = self.client.get(
                f"/api/v1/selection-sessions/{session_id}",
                headers={"X-Selection-Token": token},
            )
            self.assertEqual(original.status_code, 200, original.text)
            self.assertEqual(original.json()["id"], session_id)
            restored = self.client.get(
                map_url, params={"session_id": session_id},
                headers={"X-Selection-Token": token},
            )
            self.assertEqual(restored.status_code, 200, restored.text)
            positions = restored.json()["positions"]
            self.assertEqual({item["id"] for item in positions}, {self.room_id, target_ids[index]})
            current = [item for item in positions if item["is_current"]]
            self.assertEqual(len(current), 1)
            self.assertEqual(current[0]["id"], target_ids[index])
            self.assertEqual(current[0]["type"], room_type)
            self.assertEqual(current[0]["customer_selectable"], customer_selectable)
            self.assertEqual(current[0]["state"], "waiting_service")
            self.assertEqual(current[0]["occupancy"]["id"], occupancy_id)
            self.assertEqual(current[0]["occupancy"]["selection_session_id"], session_id)

    def test_assignment_is_idempotent_and_preserves_the_entire_selection(self):
        session_id = self.selection()
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            before = {column.name: deepcopy(getattr(session, column.name)) for column in SelectionSession.__table__.columns}
        first = self.assign(session_id)
        self.assertEqual(first.status_code, 200, first.text)
        second = self.assign(session_id)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(first.json()["status"], "waiting_service")
        self.assertIsNone(first.json()["actual_start_at"])
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            after = {column.name: deepcopy(getattr(session, column.name)) for column in SelectionSession.__table__.columns}
            self.assertEqual(after, before)
            self.assertEqual(db.scalar(select(func.count()).select_from(PositionOccupancy).where(PositionOccupancy.selection_session_id == session_id)), 1)
            self.assertEqual(db.get(Room, self.room_id).status, "available")
            self.assertEqual(db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "assign_selection_position", AuditLog.entity_id == session_id)), 1)
        item = next(item for item in self.client.get("/api/v1/admin/v2/selection-sessions", headers=self.headers).json()["items"] if item["id"] == session_id)
        self.assertFalse(item["needs_position_assignment"])
        self.assertEqual(item["position"]["room_id"], self.room_id)

    def test_confirmed_unseated_selection_can_be_assigned(self):
        self.assertEqual(self.assign(self.selection("confirmed")).status_code, 200)

    def test_cross_store_and_readonly_requests_cannot_assign(self):
        own, other = self.selection(), self.selection(store_id=self.other_store_id)
        self.assertEqual(self.assign(other).status_code, 404)
        self.assertEqual(self.assign(own, self.other_room_id).status_code, 404)
        self.assertEqual(self.assign(own, headers=self.readonly_headers).status_code, 403)
        self.assertEqual(self.assign(own, headers={}).status_code, 401)
        with self.SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(PositionOccupancy).where(PositionOccupancy.store_id == self.store_id)), 0)

    def test_ineligible_sessions_and_positions_do_not_create_occupancy(self):
        for status in ("draft", "cancelled", "expired"):
            with self.subTest(status=status):
                self.assertEqual(self.assign(self.selection(status)).status_code, 409)
        session_id = self.selection()
        for change in ({"operational_status": "inactive"}, {"status": "cleaning"}, {"is_space_container": True}, {"is_service_position": False}):
            with self.subTest(change=change):
                with self.SessionLocal() as db:
                    room = db.get(Room, self.room_id)
                    for field, value in change.items():
                        setattr(room, field, value)
                    db.commit()
                self.assertEqual(self.assign(session_id).status_code, 409)
                with self.SessionLocal() as db:
                    room = db.get(Room, self.room_id)
                    room.operational_status, room.status = "active", "available"
                    room.is_space_container, room.is_service_position = False, True
                    db.commit()

    def test_existing_occupancy_and_parent_room_conflicts_are_not_overwritten(self):
        first, second = self.selection(), self.selection()
        self.assertEqual(self.assign(first).status_code, 200)
        self.assertEqual(self.assign(second).status_code, 409)
        with self.SessionLocal() as db:
            parent = Room(store_id=self.store_id, code=f"parent-{self.key}", name="Room", is_space_container=True, is_service_position=False)
            db.add(parent)
            db.flush()
            beds = [Room(store_id=self.store_id, code=f"bed-{i}-{self.key}", name=f"Bed {i}", room_type="bed", parent_room_id=parent.id) for i in (1, 2)]
            db.add_all(beds)
            db.commit()
            bed_ids = [bed.id for bed in beds]
        third, fourth = self.selection(), self.selection()
        self.assertEqual(self.assign(third, bed_ids[0]).status_code, 200)
        conflict = self.assign(fourth, bed_ids[1])
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["detail"]["code"], "POSITION_OCCUPANCY_CONFLICT")
        self.assertEqual(self.assign(first, bed_ids[1]).status_code, 409)

    def test_released_selection_cannot_be_reseated(self):
        session_id = self.selection()
        self.assertEqual(self.assign(session_id).status_code, 200)
        with self.SessionLocal() as db:
            occupancy = db.scalar(select(PositionOccupancy).where(PositionOccupancy.selection_session_id == session_id))
            occupancy.status = "released"
            occupancy.active_session_id = occupancy.active_room_id = None
            db.commit()
        self.assertEqual(self.assign(session_id).status_code, 409)

    @unittest.skipUnless(os.environ.get("HXY_SEAT_OPTIONAL_PG") == "1", "requires isolated synthetic PostgreSQL")
    def test_concurrent_same_room_assignments_have_one_winner(self):
        sessions = [self.selection(), self.selection()]
        barrier = Barrier(2)

        def submit(session_id):
            barrier.wait(timeout=5)
            return self.assign(session_id).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(submit, sessions))
        self.assertEqual(sorted(codes), [200, 409])
        with self.SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(PositionOccupancy).where(PositionOccupancy.active_room_id == self.room_id)), 1)



    def test_assignment_reaches_technician_tasks_without_starting_service(self):
        created = self.client.post("/api/v1/selection-sessions", json={"store_id": self.store_id}).json()
        session_id = created["session"]["id"]
        submitted = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": created["access_token"], "Idempotency-Key": self.key},
            json={"items": [{"project_id": self.project_id}], "diy_preferences": {}},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        with self.SessionLocal() as db:
            tech = Technician(store_id=self.store_id, code=f"tech-{self.key}", name="Synthetic technician", status="available")
            db.add(tech)
            db.flush()
            staff = Staff(username=f"tech-{self.key}", name="Synthetic technician", password_hash="unused", role="technician", status="active", store_id=self.store_id, technician_id=tech.id)
            db.add(staff)
            db.commit()
            headers = {"Authorization": f"Bearer {create_staff_token(staff.id, 'technician')}"}
        before = self.client.get("/api/v1/technician/tasks", headers=headers)
        self.assertEqual(before.status_code, 200, before.text)
        before_payload = before.json()
        self.assertNotIn(session_id, [item["selection_session_id"] for item in before_payload["items"]])
        unassigned = next(item for item in before_payload["unassigned_items"] if item["selection_session_id"] == session_id)
        self.assertEqual(unassigned["occupancy_status"], "unassigned")
        self.assertIsNone(unassigned["occupancy_id"])
        self.assertEqual(unassigned["room_name"], "待安排座位")
        self.assertTrue(unassigned["items"])
        self.assertEqual(unassigned["selection_status"], "submitted")
        self.assertEqual(self.assign(session_id).status_code, 200)
        after = self.client.get("/api/v1/technician/tasks", headers=headers)
        after_payload = after.json()
        self.assertNotIn(session_id, [item["selection_session_id"] for item in after_payload["unassigned_items"]])
        task = next(item for item in after_payload["items"] if item["selection_session_id"] == session_id)
        self.assertEqual(task["occupancy_status"], "waiting_service")
        self.assertFalse(task["conflict"])
        self.assertIsNotNone(task["user_id"])
        for action in ("confirm", "finish"):
            result = self.client.post(
                f"/api/v1/technician/occupancies/{task['occupancy_id']}/{action}",
                headers=headers, json={"idempotency_key": f"{action}-{self.key}"},
            )
            self.assertEqual(result.status_code, 200, result.text)
        record_body = {
            "user_id": task["user_id"], "selection_session_id": session_id,
            "schema_version": 7, "taxonomy_version": "service_handoff_v1",
            "profile": {"schema_version": 7, "taxonomy_version": "service_handoff_v1", "recording_outcome": "no_additional_notes"},
            "signals": [], "note": "",
        }
        recorded = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**headers, "Idempotency-Key": f"record-{self.key}"}, json=record_body,
        )
        self.assertEqual(recorded.status_code, 200, recorded.text)
        self.assertEqual(recorded.json()["user_id"], task["user_id"])

    def concurrent_assign(self, requests):
        barrier = Barrier(2)

        def submit(pair):
            barrier.wait(timeout=5)
            return self.assign(*pair)

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(submit, requests))

    @unittest.skipUnless(os.environ.get("HXY_SEAT_OPTIONAL_PG") == "1", "requires isolated synthetic PostgreSQL")
    def test_concurrent_same_selection_retries_return_one_occupancy(self):
        session_id = self.selection()
        responses = self.concurrent_assign([(session_id, self.room_id)] * 2)
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(responses[0].json()["id"], responses[1].json()["id"])

    @unittest.skipUnless(os.environ.get("HXY_SEAT_OPTIONAL_PG") == "1", "requires isolated synthetic PostgreSQL")
    def test_concurrent_sibling_beds_obey_the_technician_room_boundary(self):
        with self.SessionLocal() as db:
            parent = Room(store_id=self.store_id, code=f"p-{self.key}", name="Room", is_space_container=True, is_service_position=False)
            db.add(parent)
            db.flush()
            beds = [Room(store_id=self.store_id, code=f"b{i}-{self.key}", name=f"Bed {i}", room_type="bed", parent_room_id=parent.id) for i in (1, 2)]
            db.add_all(beds)
            db.commit()
            targets = [bed.id for bed in beds]
        responses = self.concurrent_assign([(self.selection(), target) for target in targets])
        self.assertEqual(sorted(response.status_code for response in responses), [200, 409])



    def test_anonymous_browser_is_reused_without_inheriting_a_member_identity(self):
        created = self.client.post("/api/v1/selection-sessions", json={"store_id": self.store_id, "customer_id": 999999})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertIn("HttpOnly", created.headers["set-cookie"])
        first_id = created.json()["session"]["id"]
        again = self.client.post("/api/v1/selection-sessions", json={"store_id": self.store_id}).json()["session"]["id"]
        with self.SessionLocal() as db:
            first = db.get(SelectionSession, first_id)
            original_customer_id = first.customer_id
            self.assertEqual(db.get(SelectionSession, again).customer_id, original_customer_id)
            member = User(openid=f"member-{self.key}", phone="13000000001", is_member=True, member_type="annual")
            db.add(member)
            db.flush()
            member_id = member.id
            browser = db.scalar(select(BrowserInstance).where(BrowserInstance.customer_id == original_customer_id))
            browser.customer_id = member_id
            first.customer_id = member_id
            db.commit()
        renewed = self.client.post("/api/v1/selection-sessions", json={"store_id": self.store_id}).json()
        with self.SessionLocal() as db:
            new_session = db.get(SelectionSession, renewed["session"]["id"])
            self.assertNotEqual(new_session.customer_id, member_id)
            self.assertTrue(db.get(User, new_session.customer_id).openid.startswith("anon_"))
            self.assertEqual(db.get(SelectionSession, first_id).customer_id, member_id)
        quote = self.client.post(
            f"/api/v1/selection-sessions/{renewed['session']['id']}/quote",
            headers={"X-Selection-Token": renewed["access_token"]},
            json={"items": [{"project_id": self.project_id}], "diy_preferences": {}},
        )
        self.assertEqual(quote.json()["pricing"]["payable_total_cents"], 9900)


if __name__ == "__main__":
    unittest.main()
