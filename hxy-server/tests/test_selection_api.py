import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models import Order, PositionOccupancy, Project, SelectionSession, ServiceFeedback, Store


class SelectionSessionApiTests(unittest.TestCase):
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
            store = Store(store_code="selection-store", name="选单测试门店", address="测试地址")
            other_store = Store(store_code="selection-other", name="其他门店", address="其他地址")
            db.add_all([store, other_store])
            db.flush()
            project = Project(
                store_id=store.id,
                code="SEL-BATH",
                category="bath",
                name="悦泡·悦轻松",
                publication_status="published",
            )
            other_project = Project(
                store_id=other_store.id,
                code="SEL-OTHER",
                category="bath",
                name="其他门店项目",
                publication_status="published",
            )
            db.add_all([project, other_project])
            db.commit()
            cls.store_id = store.id
            cls.project_id = project.id
            cls.other_project_id = other_project.id

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

    def create_session(self):
        response = self.client.post(
            "/api/v1/selection-sessions",
            json={"store_id": self.store_id, "source": "tablet", "device_label": "前台平板"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        return data["session"]["id"], data["access_token"]

    def test_create_save_and_read_draft(self):
        session_id, token = self.create_session()
        payload = {
            "items": [{
                "project_id": self.project_id,
                "quantity": 1,
                "addon_ids": [],
                "diy_preferences": ["肩颈", "精油"],
                "item_type": "service",
                "chargeable": True,
            }, {
                "project_id": "tea",
                "quantity": 1,
                "addon_ids": [],
                "diy_preferences": ["老姜茶"],
                "item_type": "preference",
                "chargeable": False,
            }],
            "diy_preferences": {"tea_flavor": "老姜茶"},
        }
        saved = self.client.patch(
            f"/api/v1/selection-sessions/{session_id}",
            headers={"X-Selection-Token": token},
            json=payload,
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["status"], "draft")
        self.assertFalse(saved.json()["items"][1]["chargeable"])

        read = self.client.get(
            f"/api/v1/selection-sessions/{session_id}",
            headers={"X-Selection-Token": token},
        )
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.json()["diy_preferences"]["tea_flavor"], "老姜茶")

    def test_session_requires_its_anonymous_access_token(self):
        session_id, _ = self.create_session()
        response = self.client.get(f"/api/v1/selection-sessions/{session_id}")
        self.assertEqual(response.status_code, 403)

    def test_client_cannot_bind_another_customer_when_creating_session(self):
        response = self.client.post(
            "/api/v1/selection-sessions",
            json={"store_id": self.store_id, "customer_id": 999999},
        )
        self.assertEqual(response.status_code, 200)
        session_id = response.json()["session"]["id"]
        with self.SessionLocal() as db:
            self.assertIsNone(db.get(SelectionSession, session_id).customer_id)

    def test_submit_is_idempotent_and_does_not_create_order(self):
        session_id, token = self.create_session()
        payload = {"items": [{"project_id": self.project_id, "diy_preferences": ["腿部"]}]}
        with self.SessionLocal() as db:
            before = db.scalar(select(func.count()).select_from(Order))

        first = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/submit",
            headers={"X-Selection-Token": token},
            json=payload,
        )
        second = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/submit",
            headers={"X-Selection-Token": token},
            json=payload,
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["status"], "submitted")
        self.assertEqual(first.json()["submitted_at"], second.json()["submitted_at"])
        with self.SessionLocal() as db:
            after = db.scalar(select(func.count()).select_from(Order))
            self.assertEqual(before, after)
            self.assertEqual(db.get(SelectionSession, session_id).status, "submitted")

    def test_repeated_submit_keeps_the_first_submission_snapshot(self):
        session_id, token = self.create_session()
        first = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/submit",
            headers={"X-Selection-Token": token},
            json={"items": [{"project_id": self.project_id, "diy_preferences": ["肩颈"]}]},
        )
        retry = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/submit",
            headers={"X-Selection-Token": token},
            json={"items": [{"project_id": "local-strength", "item_type": "service", "chargeable": True}]},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["items"], first.json()["items"])
        self.assertEqual(retry.json()["pricing_snapshot"], first.json()["pricing_snapshot"])
        self.assertEqual(retry.json()["submitted_at"], first.json()["submitted_at"])

    def test_submitted_session_cannot_be_modified(self):
        session_id, token = self.create_session()
        self.client.post(
            f"/api/v1/selection-sessions/{session_id}/submit",
            headers={"X-Selection-Token": token},
            json={"items": [{"project_id": self.project_id}]},
        )
        response = self.client.patch(
            f"/api/v1/selection-sessions/{session_id}",
            headers={"X-Selection-Token": token},
            json={"items": []},
        )
        self.assertEqual(response.status_code, 409)

    def test_project_from_another_store_is_rejected(self):
        session_id, token = self.create_session()
        response = self.client.patch(
            f"/api/v1/selection-sessions/{session_id}",
            headers={"X-Selection-Token": token},
            json={"items": [{"project_id": self.other_project_id}]},
        )
        self.assertEqual(response.status_code, 404)

    def test_local_strength_can_be_submitted_as_chargeable_service(self):
        session_id, token = self.create_session()
        response = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/submit",
            headers={"X-Selection-Token": token},
            json={"items": [{"project_id": "local-strength", "item_type": "service", "chargeable": True, "diy_preferences": ["肩颈", "精油"]}]},
        )
        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["name"], "局部加强")
        self.assertTrue(item["chargeable"])

    def test_feedback_is_closed_until_service_ends_and_is_idempotent(self):
        session_id, token = self.create_session()
        self.client.post(
            f"/api/v1/selection-sessions/{session_id}/submit",
            headers={"X-Selection-Token": token},
            json={"items": [{"project_id": self.project_id}]},
        )
        with self.SessionLocal() as db:
            occupancy = PositionOccupancy(
                store_id=self.store_id, room_id=1, selection_session_id=session_id,
                status="waiting_service", source="tablet",
            )
            db.add(occupancy)
            db.commit()

        status = self.client.get(f"/api/v1/selection-sessions/{session_id}/service-status", headers={"X-Selection-Token": token})
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["can_evaluate"])
        blocked = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/feedback",
            headers={"X-Selection-Token": token},
            json={"rating": 5, "tags": ["服务细致"], "note": "很好"},
        )
        self.assertEqual(blocked.status_code, 409)

        with self.SessionLocal() as db:
            occupancy = db.scalar(select(PositionOccupancy).where(PositionOccupancy.selection_session_id == session_id))
            occupancy.status = "post_service_present"
            occupancy.actual_service_end_at = datetime.now(timezone.utc)
            db.commit()

        ready = self.client.get(f"/api/v1/selection-sessions/{session_id}/service-status", headers={"X-Selection-Token": token})
        self.assertTrue(ready.json()["can_evaluate"])
        feedback = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/feedback",
            headers={"X-Selection-Token": token},
            json={"rating": 5, "tags": ["服务细致", "环境安心"], "note": "很好"},
        )
        self.assertEqual(feedback.status_code, 200)
        duplicate = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/feedback",
            headers={"X-Selection-Token": token},
            json={"rating": 3, "tags": [], "note": "修改"},
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.json()["rating"], 5)
        with self.SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(ServiceFeedback).where(ServiceFeedback.selection_session_id == session_id)), 1)


if __name__ == "__main__":
    unittest.main()
