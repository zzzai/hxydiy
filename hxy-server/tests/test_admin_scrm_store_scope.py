import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import Staff, Store, Technician


class AdminScrmStoreScopeTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            first = Store(store_code="scrm-a", name="运营 A 店", address="A")
            second = Store(store_code="scrm-b", name="运营 B 店", address="B")
            db.add_all([first, second])
            db.flush()
            first_staff = Staff(
                username="scrm-a-admin",
                password_hash=hash_password("test-pass"),
                name="A 店长",
                role="admin",
                store_id=first.id,
            )
            second_staff = Staff(
                username="scrm-b-admin",
                password_hash=hash_password("test-pass"),
                name="B 店长",
                role="admin",
                store_id=second.id,
            )
            first_technician = Technician(
                store_id=first.id,
                code="scrm-a-tech",
                name="A 店技师",
                status="active",
            )
            db.add(first_technician)
            db.flush()
            first_operator = Staff(
                username="scrm-a-operator",
                password_hash=hash_password("test-pass"),
                name="A 店员",
                role="technician",
                store_id=first.id,
                technician_id=first_technician.id,
            )
            db.add_all([first_staff, second_staff, first_operator])
            db.commit()
            self.first_headers = {"Authorization": f"Bearer {create_staff_token(first_staff.id, 'admin')}"}
            self.second_headers = {"Authorization": f"Bearer {create_staff_token(second_staff.id, 'admin')}"}
            self.operator_headers = {"Authorization": f"Bearer {create_staff_token(first_operator.id, 'technician')}"}

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def _create_for_each_store(self, path: str, first_body: dict, second_body: dict) -> tuple[int, int]:
        first = self.client.post(path, headers=self.first_headers, json=first_body)
        second = self.client.post(path, headers=self.second_headers, json=second_body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        return first.json()["id"], second.json()["id"]

    def test_tags_are_listed_and_mutated_within_the_current_store(self):
        first_id, second_id = self._create_for_each_store(
            "/api/v1/admin/v2/tags",
            {"name": "A 店高频顾客"},
            {"name": "B 店高频顾客"},
        )

        listed = self.client.get("/api/v1/admin/v2/tags", headers=self.first_headers)
        cross_update = self.client.post(
            f"/api/v1/admin/v2/tags/{second_id}",
            headers=self.first_headers,
            json={"name": "越权修改"},
        )

        self.assertEqual([tag["id"] for tag in listed.json()], [first_id])
        self.assertEqual(cross_update.status_code, 404)

    def test_same_profile_tag_name_is_allowed_in_two_stores(self):
        first_id, second_id = self._create_for_each_store(
            "/api/v1/admin/v2/tags",
            {"name": "肩颈紧张", "tag_type": "profile"},
            {"name": "肩颈紧张", "tag_type": "profile"},
        )
        self.assertNotEqual(first_id, second_id)

    def test_segments_are_listed_and_mutated_within_the_current_store(self):
        first_id, second_id = self._create_for_each_store(
            "/api/v1/admin/v2/segments",
            {"name": "A 店沉睡顾客"},
            {"name": "B 店沉睡顾客"},
        )

        listed = self.client.get("/api/v1/admin/v2/segments", headers=self.first_headers)
        cross_update = self.client.post(
            f"/api/v1/admin/v2/segments/{second_id}",
            headers=self.first_headers,
            json={"name": "越权修改"},
        )

        self.assertEqual([segment["id"] for segment in listed.json()], [first_id])
        self.assertEqual(cross_update.status_code, 404)

    def test_automations_are_listed_and_mutated_within_the_current_store(self):
        first_id, second_id = self._create_for_each_store(
            "/api/v1/admin/v2/automations",
            {"name": "A 店回访", "trigger_event": "order_completed"},
            {"name": "B 店回访", "trigger_event": "order_completed"},
        )

        listed = self.client.get("/api/v1/admin/v2/automations", headers=self.first_headers)
        cross_delete = self.client.delete(
            f"/api/v1/admin/v2/automations/{second_id}",
            headers=self.first_headers,
        )

        self.assertEqual([rule["id"] for rule in listed.json()], [first_id])
        self.assertEqual(cross_delete.status_code, 404)

    def test_store_staff_can_read_but_cannot_write_scrm_configuration(self):
        tag_id, _ = self._create_for_each_store(
            "/api/v1/admin/v2/tags",
            {"name": "A 店只读标签"},
            {"name": "B 店只读标签"},
        )

        listed = self.client.get("/api/v1/admin/v2/tags", headers=self.operator_headers)
        write = self.client.post(
            f"/api/v1/admin/v2/tags/{tag_id}",
            headers=self.operator_headers,
            json={"name": "店员越权修改"},
        )

        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(write.status_code, 403)


if __name__ == "__main__":
    unittest.main()
