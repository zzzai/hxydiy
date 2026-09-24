import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.occupancies import _managed_position_qr_token
from app.db.session import Base, get_db
from app.main import app
from app.models import Project, Room, ServicePositionQr, Store


class SharedSelectionCollaborationTests(unittest.TestCase):
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
            store = Store(store_code="shared-selection", name="共享选单门店", address="测试地址")
            db.add(store)
            db.flush()
            project = Project(
                store_id=store.id,
                code="SHARED-BATH",
                category="bath",
                name="共享草本泡",
                publication_status="published",
            )
            db.add(project)
            db.commit()
            cls.store_id = store.id
            cls.project_id = project.id

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def setUp(self):
        with self.SessionLocal() as db:
            room = Room(
                store_id=self.store_id,
                code=f"shared-{uuid.uuid4().hex[:8]}",
                name="共享测试沙发",
                room_type="sofa",
                customer_label="共享测试位",
                operational_status="active",
                is_service_position=True,
                is_space_container=False,
            )
            db.add(room)
            db.flush()
            qr = ServicePositionQr(
                public_id=str(uuid.uuid4()),
                store_id=self.store_id,
                room_id=room.id,
                source="personal_qr",
                status="active",
            )
            db.add(qr)
            db.commit()
            self.position_code = room.code
            self.entry_token = _managed_position_qr_token(qr, room.code)

        self.first = TestClient(app)
        self.second = TestClient(app)

    def tearDown(self):
        self.first.close()
        self.second.close()

    def entry(self, client: TestClient):
        return client.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": self.position_code,
            "source": "personal_qr",
            "device_label": "扫码手机",
            "entry_token": self.entry_token,
        })

    def test_two_browsers_join_one_draft_with_independent_tokens(self):
        first = self.entry(self.first)
        second = self.entry(self.second)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["session"]["id"], second.json()["session"]["id"])
        self.assertTrue(first.json().get("shared_cart"))
        self.assertEqual(first.json().get("collaboration_mode"), "shared_draft")
        self.assertTrue(first.json().get("collaboration_token", "").startswith("sc1."))
        self.assertTrue(second.json().get("collaboration_token", "").startswith("sc1."))
        self.assertNotEqual(first.json()["collaboration_token"], second.json()["collaboration_token"])
        self.assertEqual(second.json()["session"]["pricing_snapshot"], {})
        self.assertEqual(second.json()["session"]["store_total_cents"], 0)

    def test_signed_qr_opens_menu_when_position_is_physically_occupied_without_an_active_selection(self):
        with self.SessionLocal() as db:
            previous_room = Room(
                store_id=self.store_id,
                code=f"previous-{uuid.uuid4().hex[:8]}",
                name="此前扫码沙发",
                room_type="sofa",
                customer_label="此前沙发",
                operational_status="active",
                is_service_position=True,
                is_space_container=False,
            )
            db.add(previous_room)
            db.flush()
            previous_qr = ServicePositionQr(
                public_id=str(uuid.uuid4()),
                store_id=self.store_id,
                room_id=previous_room.id,
                source="personal_qr",
                status="active",
            )
            db.add(previous_qr)
            room = db.query(Room).filter(Room.code == self.position_code).one()
            room.status = "occupied"
            db.commit()
            previous_code = previous_room.code
            previous_token = _managed_position_qr_token(previous_qr, previous_room.code)

        previous = self.first.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": previous_code,
            "source": "personal_qr",
            "device_label": "扫码手机",
            "entry_token": previous_token,
        })
        self.assertEqual(previous.status_code, 200, previous.text)

        response = self.entry(self.first)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["session"]["status"], "draft")
        self.assertEqual(response.json()["collaboration_mode"], "shared_draft")
        self.assertEqual(response.json()["entry_notice"], "该位置当前有人，已进入菜单")

    def test_stale_shared_write_returns_latest_snapshot_without_overwrite(self):
        first = self.entry(self.first).json()
        second = self.entry(self.second).json()
        session_id = first["session"]["id"]
        initial_version = first["cart_version"]
        payload = {
            "items": [{"project_id": self.project_id, "quantity": 1}],
            "diy_preferences": {},
            "expected_version": initial_version,
        }

        saved = self.first.patch(
            f"/api/v1/selection-sessions/{session_id}",
            headers={"X-Collaboration-Token": first["collaboration_token"]},
            json=payload,
        )
        stale = self.second.patch(
            f"/api/v1/selection-sessions/{session_id}",
            headers={"X-Collaboration-Token": second["collaboration_token"]},
            json={**payload, "items": []},
        )

        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["pricing_snapshot"], {})
        self.assertEqual(saved.json()["store_total_cents"], 0)
        self.assertGreater(saved.json()["cart_version"], initial_version)
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["detail"]["code"], "CART_VERSION_CONFLICT")
        self.assertEqual(stale.json()["detail"]["cart_version"], saved.json()["cart_version"])
        self.assertEqual(stale.json()["detail"]["session"]["items"], saved.json()["items"])

    def test_collaboration_token_is_bound_to_its_browser_cookie(self):
        entry = self.entry(self.first).json()
        response = self.second.get(
            f"/api/v1/selection-sessions/{entry['session']['id']}",
            headers={"X-Collaboration-Token": entry["collaboration_token"]},
        )

        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "COLLABORATION_TOKEN_INVALID")

    def test_submit_locks_shared_draft_and_idempotent_replay_is_safe(self):
        first = self.entry(self.first).json()
        second = self.entry(self.second).json()
        session_id = first["session"]["id"]
        saved = self.first.patch(
            f"/api/v1/selection-sessions/{session_id}",
            headers={"X-Collaboration-Token": first["collaboration_token"]},
            json={
                "items": [{"project_id": self.project_id, "quantity": 1}],
                "diy_preferences": {},
                "expected_version": first["cart_version"],
            },
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        headers = {
            "X-Collaboration-Token": first["collaboration_token"],
            "Idempotency-Key": "shared-submit-once",
        }
        payload = {
            "items": [{"project_id": self.project_id, "quantity": 1}],
            "diy_preferences": {},
            "expected_version": saved.json()["cart_version"],
        }

        submitted = self.first.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers=headers,
            json=payload,
        )
        replay = self.first.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers=headers,
            json=payload,
        )
        blocked = self.second.patch(
            f"/api/v1/selection-sessions/{session_id}",
            headers={"X-Collaboration-Token": second["collaboration_token"]},
            json={**payload, "items": []},
        )
        rescanned = self.entry(self.second)

        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), submitted.json())
        self.assertEqual(blocked.status_code, 403, blocked.text)
        self.assertEqual(blocked.json()["detail"]["code"], "COLLABORATION_READ_ONLY")
        self.assertEqual(rescanned.status_code, 200, rescanned.text)
        self.assertEqual(rescanned.json()["collaboration_mode"], "browse_only")
        self.assertEqual(rescanned.json()["session"]["items"], [])
        self.assertEqual(rescanned.json()["session"]["pricing_snapshot"], {})

    def test_disabled_qr_invalidates_existing_collaboration_token(self):
        entry = self.entry(self.first).json()
        with self.SessionLocal() as db:
            qr = db.query(ServicePositionQr).filter(ServicePositionQr.room_id == entry["position"]["id"]).one()
            qr.status = "disabled"
            db.commit()

        response = self.first.get(
            f"/api/v1/selection-sessions/{entry['session']['id']}",
            headers={"X-Collaboration-Token": entry["collaboration_token"]},
        )

        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "COLLABORATION_TOKEN_INVALID")

    def test_collaboration_token_cannot_cross_selection_or_position(self):
        first_position = self.entry(self.first).json()
        with self.SessionLocal() as db:
            room = Room(
                store_id=self.store_id,
                code=f"other-{uuid.uuid4().hex[:8]}",
                name="其他测试沙发",
                room_type="sofa",
                customer_label="其他测试位",
                operational_status="active",
                is_service_position=True,
                is_space_container=False,
            )
            db.add(room)
            db.flush()
            qr = ServicePositionQr(
                public_id=str(uuid.uuid4()), store_id=self.store_id,
                room_id=room.id, source="personal_qr", status="active",
            )
            db.add(qr)
            db.commit()
            other_code = room.code
            other_token = _managed_position_qr_token(qr, room.code)
        with TestClient(app) as other_browser:
            second_position = other_browser.post("/api/v1/entry-sessions", json={
                "store_id": self.store_id,
                "position_code": other_code,
                "source": "personal_qr",
                "device_label": "另一台扫码手机",
                "entry_token": other_token,
            }).json()

        response = self.first.get(
            f"/api/v1/selection-sessions/{second_position['session']['id']}",
            headers={"X-Collaboration-Token": first_position["collaboration_token"]},
        )

        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "COLLABORATION_TOKEN_INVALID")

    def test_signed_qr_can_join_an_occupied_position_when_browser_is_bound_elsewhere(self):
        self.entry(self.first)
        with self.SessionLocal() as db:
            room = Room(
                store_id=self.store_id,
                code=f"occupied-{uuid.uuid4().hex[:8]}",
                name="已有顾客的测试沙发",
                room_type="sofa",
                customer_label="已有顾客的测试位",
                operational_status="active",
                is_service_position=True,
                is_space_container=False,
            )
            db.add(room)
            db.flush()
            qr = ServicePositionQr(
                public_id=str(uuid.uuid4()), store_id=self.store_id,
                room_id=room.id, source="personal_qr", status="active",
            )
            db.add(qr)
            db.commit()
            occupied_code = room.code
            occupied_token = _managed_position_qr_token(qr, room.code)

        with TestClient(app) as occupant:
            occupied = occupant.post("/api/v1/entry-sessions", json={
                "store_id": self.store_id,
                "position_code": occupied_code,
                "source": "personal_qr",
                "device_label": "座位原顾客",
                "entry_token": occupied_token,
            })
        joined = self.first.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": occupied_code,
            "source": "personal_qr",
            "device_label": "同行人手机",
            "entry_token": occupied_token,
        })

        self.assertEqual(occupied.status_code, 200, occupied.text)
        self.assertEqual(joined.status_code, 200, joined.text)
        self.assertEqual(joined.json()["session"]["id"], occupied.json()["session"]["id"])
        self.assertEqual(joined.json()["collaboration_mode"], "shared_draft")

    def test_signed_qr_does_not_let_one_browser_hold_two_empty_positions(self):
        self.entry(self.first)
        with self.SessionLocal() as db:
            room = Room(
                store_id=self.store_id,
                code=f"empty-{uuid.uuid4().hex[:8]}",
                name="空闲测试沙发",
                room_type="sofa",
                customer_label="空闲测试位",
                operational_status="active",
                is_service_position=True,
                is_space_container=False,
            )
            db.add(room)
            db.flush()
            qr = ServicePositionQr(
                public_id=str(uuid.uuid4()), store_id=self.store_id,
                room_id=room.id, source="personal_qr", status="active",
            )
            db.add(qr)
            db.commit()
            empty_code = room.code
            empty_token = _managed_position_qr_token(qr, room.code)

        response = self.first.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": empty_code,
            "source": "personal_qr",
            "device_label": "重复占位手机",
            "entry_token": empty_token,
        })

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "BROWSER_ACTIVE_ELSEWHERE")

    def test_repeated_signed_qr_entry_is_rate_limited_and_audited(self):
        with patch("app.api.occupancies.COLLABORATION_ENTRY_RATE_LIMIT", 1):
            first = self.entry(self.first)
            limited = self.entry(self.first)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(limited.status_code, 429, limited.text)
        self.assertEqual(limited.json()["detail"]["code"], "SHARED_ENTRY_RATE_LIMITED")
        self.assertIn("Retry-After", limited.headers)

    def test_invalid_login_cannot_silently_fall_back_during_shared_quote(self):
        entry = self.entry(self.first).json()
        response = self.first.post(
            f"/api/v1/selection-sessions/{entry['session']['id']}/quote",
            headers={
                "X-Collaboration-Token": entry["collaboration_token"],
                "Authorization": "Bearer invalid-token",
            },
            json={
                "items": [{"project_id": self.project_id, "quantity": 1}],
                "diy_preferences": {},
                "expected_version": entry["cart_version"],
            },
        )

        self.assertEqual(response.status_code, 401, response.text)


if __name__ == "__main__":
    unittest.main()
