import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.api.occupancies import create_position_qr_token
from app.db.session import Base, get_db
from app.main import app
from app.models import BrowserInstance, PositionOccupancy, PriceBook, Project, Room, SelectionSession, ServicePositionQr, Staff, Store, User


class OccupancyApiTests(unittest.TestCase):
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
            store = Store(store_code="occupancy-store", name="荷小悦试用店", address="测试地址")
            db.add(store)
            db.flush()
            for index in range(1, 9):
                db.add(Room(
                    store_id=store.id,
                    code=f"sofa-{index:02d}",
                    name=f"{index}号沙发",
                    customer_label=f"{index}号沙发",
                    room_type="sofa",
                    room_group="sofa",
                    customer_selectable=True,
                    operational_status="active",
                    map_x=0.12 if index <= 4 else 0.68,
                    map_y=0.12 + ((index - 1) % 4) * 0.2,
                    sort_order=index,
                ))
            for index in range(1, 3):
                db.add(Room(
                    store_id=store.id,
                    code=f"room-{index:02d}",
                    name=f"房间{index}",
                    customer_label="当前房间",
                    room_type="room",
                    room_group="room",
                    customer_selectable=False,
                    operational_status="active",
                    sort_order=8 + index,
                ))

            foot = Project(
                store_id=store.id,
                code="hxy-qiqing-30",
                category="bath",
                category_mark="泡",
                name="草本泡脚",
                duration_min=30,
                publication_status="published",
            )
            local = Project(
                store_id=store.id,
                code="hxy-jubu-30",
                category="local-strength",
                category_mark="加",
                name="局部调理",
                duration_min=30,
                publication_status="published",
            )
            db.add_all([foot, local])
            db.flush()
            db.add_all([
                PriceBook(project_id=foot.id, price_type="store", amount_cents=3990),
                PriceBook(project_id=foot.id, price_type="member", amount_cents=2990),
                PriceBook(project_id=local.id, price_type="store", amount_cents=6900),
                PriceBook(project_id=local.id, price_type="member", amount_cents=4900),
            ])
            staff = Staff(
                username="occupancy-admin",
                password_hash=hash_password("pass"),
                name="店长",
                role="admin",
                store_id=store.id,
                status="active",
            )
            db.add(staff)
            db.commit()
            cls.store_id = store.id
            cls.foot_id = foot.id
            cls.local_id = local.id
            cls.staff_id = staff.id

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        cls.admin_headers = {"Authorization": f"Bearer {create_staff_token(cls.staff_id, 'admin')}"}

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def entry(self, code: str = "sofa-01", source: str = "personal_qr") -> dict:
        # 每个普通 helper 调用模拟新的顾客浏览器；连续性场景使用独立 TestClient 显式验证。
        self.client.cookies.delete("hxy_browser_token")
        response = self.client.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": code,
            "source": source,
            "device_label": "测试手机",
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def kiosk_entry(self, code: str = "sofa-01") -> dict:
        with self.SessionLocal() as db:
            room = db.scalar(select(Room).where(Room.code == code))
        response = self.client.post(
            "/api/v1/admin/kiosk-sessions",
            headers=self.admin_headers,
            json={"room_id": room.id, "device_label": "前台共享 iPad"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def release_if_active(self, code: str) -> None:
        with self.SessionLocal() as db:
            room = db.scalar(select(Room).where(Room.code == code))
            occupancy = db.scalar(select(PositionOccupancy).where(PositionOccupancy.active_room_id == room.id))
        if occupancy:
            response = self.client.post(
                f"/api/v1/admin/occupancies/{occupancy.id}/force-release",
                headers=self.admin_headers,
                json={"reason": "测试清理"},
            )
            self.assertEqual(response.status_code, 200, response.text)

    def set_room_status(self, code: str, status: str) -> None:
        with self.SessionLocal() as db:
            room = db.scalar(select(Room).where(Room.code == code))
            room.status = status
            db.commit()

    def test_occupancy_timestamps_are_serialized_as_utc(self):
        self.release_if_active("sofa-01")
        entry = self.entry("sofa-01")

        hold_expires_at = entry["occupancy"]["hold_expires_at"]
        parsed = datetime.fromisoformat(hold_expires_at.replace("Z", "+00:00"))

        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.utcoffset(), timedelta(0))

    def test_admin_live_map_selection_timestamps_are_serialized_as_utc(self):
        self.release_if_active("sofa-01")
        entry = self.entry("sofa-01")
        self.client.post(
            f"/api/v1/selection-sessions/{entry['session']['id']}/submit",
            headers={"X-Selection-Token": entry["access_token"]},
            json={"items": [{"project_id": self.foot_id}]},
        )

        response = self.client.get(
            "/api/v1/admin/live-service-position-map",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        position = next(item for item in response.json()["positions"] if item["code"] == "sofa-01")
        parsed = datetime.fromisoformat(position["selection"]["submitted_at"].replace("Z", "+00:00"))

        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.utcoffset(), timedelta(0))

    def test_room_status_operation_cannot_bypass_an_active_diy_occupancy(self):
        self.release_if_active("sofa-01")
        entry = self.entry("sofa-01")
        with self.SessionLocal() as db:
            room = db.scalar(select(Room).where(Room.code == "sofa-01"))

        response = self.client.post(
            f"/api/v1/admin/v2/rooms/{room.id}/operate",
            headers=self.admin_headers,
            json={"action": "occupied"},
        )

        self.assertEqual(response.status_code, 410, response.text)
        self.assertEqual(response.json()["detail"]["code"], "DIY_PHYSICAL_RESOURCE_FORBIDDEN")
        with self.SessionLocal() as db:
            room = db.get(Room, room.id)
            occupancy = db.get(PositionOccupancy, entry["occupancy"]["id"])
            self.assertEqual(room.status, "available")
            self.assertEqual(occupancy.status, "held")
            self.assertEqual(occupancy.active_room_id, room.id)

    def test_entry_rejects_a_service_position_used_by_the_legacy_service_flow(self):
        self.release_if_active("sofa-01")
        self.set_room_status("sofa-01", "in_service")
        self.addCleanup(self.set_room_status, "sofa-01", "available")

        response = self.client.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": "sofa-01",
            "source": "personal_qr",
            "device_label": "测试手机",
        })

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "POSITION_UNAVAILABLE")
        with self.SessionLocal() as db:
            room = db.scalar(select(Room).where(Room.code == "sofa-01"))
            occupancy = db.scalar(select(PositionOccupancy).where(PositionOccupancy.active_room_id == room.id))
            self.assertIsNone(occupancy)

    def test_position_map_marks_a_legacy_busy_service_position_as_unavailable(self):
        self.release_if_active("sofa-01")
        self.set_room_status("sofa-01", "cleaning")
        self.addCleanup(self.set_room_status, "sofa-01", "available")

        response = self.client.get(f"/api/v1/stores/{self.store_id}/service-position-map")

        self.assertEqual(response.status_code, 200, response.text)
        position = next(item for item in response.json()["positions"] if item["code"] == "sofa-01")
        self.assertEqual(position["state"], "unavailable")
        self.assertIsNone(position["occupancy"])

    def test_room_configuration_update_cannot_change_an_active_diy_position_status(self):
        self.release_if_active("sofa-01")
        entry = self.entry("sofa-01")
        with self.SessionLocal() as db:
            room = db.scalar(select(Room).where(Room.code == "sofa-01"))

        response = self.client.post(
            f"/api/v1/admin/v2/rooms/{room.id}",
            headers=self.admin_headers,
            json={"status": "available"},
        )

        self.assertEqual(response.status_code, 409, response.text)
        with self.SessionLocal() as db:
            room = db.get(Room, room.id)
            occupancy = db.get(PositionOccupancy, entry["occupancy"]["id"])
            self.assertEqual(room.status, "available")
            self.assertEqual(occupancy.status, "held")
            self.assertEqual(occupancy.active_room_id, room.id)

    def test_active_diy_position_cannot_be_deleted_from_room_configuration(self):
        self.release_if_active("sofa-02")
        entry = self.entry("sofa-02")
        with self.SessionLocal() as db:
            room = db.scalar(select(Room).where(Room.code == "sofa-02"))

        response = self.client.delete(
            f"/api/v1/admin/v2/rooms/{room.id}",
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 409, response.text)
        with self.SessionLocal() as db:
            room = db.get(Room, room.id)
            occupancy = db.get(PositionOccupancy, entry["occupancy"]["id"])
            self.assertIsNotNone(room)
            self.assertEqual(occupancy.status, "held")
            self.assertEqual(occupancy.active_room_id, room.id)

    def test_same_position_cannot_be_held_by_two_sessions(self):
        self.release_if_active("sofa-01")
        first = self.entry("sofa-01")
        other_browser = TestClient(app)
        second = other_browser.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": "sofa-01",
            "source": "personal_qr",
        })
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"]["code"], "POSITION_OCCUPIED")
        self.assertEqual(first["occupancy"]["status"], "held")
        other_browser.close()

    def test_same_browser_can_resume_its_own_position_after_local_storage_loss(self):
        self.release_if_active("sofa-06")
        browser = TestClient(app)
        first = browser.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id, "position_code": "sofa-06", "source": "personal_qr", "device_label": "测试手机",
        })
        self.assertEqual(first.status_code, 200, first.text)
        second = browser.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id, "position_code": "sofa-06", "source": "personal_qr", "device_label": "测试手机",
        })
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["session"]["id"], first.json()["session"]["id"])
        self.assertTrue(second.json()["resumed"])

        other_browser = TestClient(app)
        blocked = other_browser.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id, "position_code": "sofa-06", "source": "personal_qr", "device_label": "另一部手机",
        })
        self.assertEqual(blocked.status_code, 409)
        browser.close()
        other_browser.close()

        with self.SessionLocal() as db:
            occupancy = db.scalar(select(PositionOccupancy).where(PositionOccupancy.active_room_id == 6))
            if occupancy:
                db.delete(occupancy)
            db.query(SelectionSession).filter(SelectionSession.id == first.json()["session"]["id"]).delete()
            db.query(BrowserInstance).delete()
            db.query(User).filter(User.openid.like("anon_%")).delete()
            db.commit()

    def test_same_browser_can_resume_its_own_position_after_legacy_flow_reserves_the_room(self):
        self.release_if_active("sofa-06")
        browser = TestClient(app)
        first = browser.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id, "position_code": "sofa-06", "source": "personal_qr", "device_label": "测试手机",
        })
        self.assertEqual(first.status_code, 200, first.text)
        with self.SessionLocal() as db:
            room = db.scalar(select(Room).where(Room.code == "sofa-06"))
            room.status = "reserved"
            db.commit()

        resumed = browser.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id, "position_code": "sofa-06", "source": "personal_qr", "device_label": "测试手机",
        })

        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["session"]["id"], first.json()["session"]["id"])
        self.assertTrue(resumed.json()["resumed"])
        browser.close()
        self.release_if_active("sofa-06")
        self.set_room_status("sofa-06", "available")

    def test_same_browser_cannot_hold_two_positions_after_scanning_wrong_qr(self):
        self.release_if_active("sofa-07")
        self.release_if_active("sofa-08")
        browser = TestClient(app)
        first = browser.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id, "position_code": "sofa-07", "source": "personal_qr", "device_label": "测试手机",
        })
        self.assertEqual(first.status_code, 200, first.text)
        wrong_qr = browser.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id, "position_code": "sofa-08", "source": "personal_qr", "device_label": "测试手机",
        })
        self.assertEqual(wrong_qr.status_code, 409)
        self.assertEqual(wrong_qr.json()["detail"]["code"], "BROWSER_ACTIVE_ELSEWHERE")
        self.assertEqual(wrong_qr.json()["detail"]["current_position_code"], "sofa-07")
        browser.close()

    def test_production_store_qr_can_select_position_without_position_token(self):
        self.release_if_active("sofa-04")
        self.client.cookies.delete("hxy_browser_token")
        with mock.patch("app.api.occupancies.settings.environment", "production"):
            response = self.client.post("/api/v1/entry-sessions", json={
                "store_id": self.store_id,
                "position_code": "sofa-04",
                "source": "store_qr",
                "device_label": "门店二维码顾客手机",
            })

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["session"]["source"], "store_qr")
        self.release_if_active("sofa-04")

    def test_production_position_qr_still_requires_signed_token(self):
        self.release_if_active("sofa-04")
        self.client.cookies.delete("hxy_browser_token")
        with mock.patch("app.api.occupancies.settings.environment", "production"):
            response = self.client.post("/api/v1/entry-sessions", json={
                "store_id": self.store_id,
                "position_code": "sofa-04",
                "source": "personal_qr",
                "device_label": "伪造服务位直链",
            })

        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "QR_BINDING_REQUIRED")

    def test_public_entry_cannot_create_kiosk_session(self):
        self.release_if_active("sofa-01")
        response = self.client.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": "sofa-01",
            "source": "kiosk",
            "device_label": "未经前台绑定的平板",
        })

        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "KIOSK_REQUIRES_STAFF_BINDING")

    def test_signed_qr_binds_store_and_position_and_rejects_tampering(self):
        self.release_if_active("sofa-05")
        self.client.cookies.delete("hxy_browser_token")
        token = create_position_qr_token(self.store_id, "sofa-05", "personal_qr")
        valid = self.client.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": "sofa-05",
            "source": "personal_qr",
            "entry_token": token,
            "device_label": "扫码手机",
        })
        self.assertEqual(valid.status_code, 200, valid.text)
        self.release_if_active("sofa-05")
        tampered = self.client.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": "sofa-06",
            "source": "personal_qr",
            "entry_token": token,
            "device_label": "扫码手机",
        })
        self.assertEqual(tampered.status_code, 403, tampered.text)
        self.assertEqual(tampered.json()["detail"]["code"], "QR_BINDING_INVALID")

    def test_space_container_cannot_create_entry_or_qr_link(self):
        with self.SessionLocal() as db:
            container = Room(
                store_id=self.store_id,
                code="space-container",
                name="双床房容器",
                room_type="room",
                room_group="massage",
                is_space_container=True,
                is_service_position=False,
                customer_selectable=False,
            )
            db.add(container)
            db.commit()
            container_id = container.id
        try:
            entry = self.client.post("/api/v1/entry-sessions", json={
                "store_id": self.store_id,
                "position_code": "space-container",
                "source": "room_qr",
                "device_label": "测试手机",
            })
            self.assertEqual(entry.status_code, 404, entry.text)
            qr = self.client.get(
                f"/api/v1/admin/service-positions/{container_id}/qr-link",
                headers=self.admin_headers,
            )
            self.assertEqual(qr.status_code, 400, qr.text)
        finally:
            with self.SessionLocal() as db:
                db.query(Room).filter(Room.id == container_id).delete()
                db.commit()

    def test_admin_generates_room_qr_for_a_specific_bed_not_its_container(self):
        with self.SessionLocal() as db:
            container = Room(
                store_id=self.store_id,
                code="qr-room-container",
                name="双床房",
                room_type="room",
                room_group="massage",
                is_space_container=True,
                is_service_position=False,
                customer_selectable=False,
            )
            db.add(container)
            db.flush()
            bed = Room(
                store_id=self.store_id,
                code="qr-bed-a",
                name="双床房 A 床",
                room_type="bed",
                room_group="massage",
                parent_room_id=container.id,
                is_space_container=False,
                is_service_position=True,
                customer_selectable=False,
                operational_status="active",
            )
            db.add(bed)
            db.commit()
            container_id, bed_id = container.id, bed.id
        try:
            response = self.client.get(
                f"/api/v1/admin/service-positions/{bed_id}/qr-link",
                headers=self.admin_headers,
            )
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["position_code"], "qr-bed-a")
            self.assertEqual(payload["source"], "room_qr")
            self.assertIn("seat=qr-bed-a", payload["url"])
            self.assertNotIn("qr-room-container", payload["url"])
        finally:
            with self.SessionLocal() as db:
                db.query(ServicePositionQr).filter(ServicePositionQr.room_id == bed_id).delete()
                db.query(Room).filter(Room.id.in_([bed_id, container_id])).delete(synchronize_session=False)
                db.commit()

    def test_admin_can_generate_position_qr_link(self):
        with self.SessionLocal() as db:
            room = db.scalar(select(Room).where(Room.code == "sofa-06"))
        response = self.client.get(
            f"/api/v1/admin/service-positions/{room.id}/qr-link",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["store_id"], self.store_id)
        self.assertEqual(payload["position_code"], "sofa-06")
        self.assertIsInstance(payload["qr_id"], int)
        self.assertEqual(payload["status"], "active")
        self.assertIn("qr=", payload["url"])

    def test_disabled_managed_qr_cannot_create_entry(self):
        self.release_if_active("sofa-05")
        with self.SessionLocal() as db:
            room = db.scalar(select(Room).where(Room.code == "sofa-05"))
        generated = self.client.get(
            f"/api/v1/admin/service-positions/{room.id}/qr-link",
            headers=self.admin_headers,
        )
        self.assertEqual(generated.status_code, 200, generated.text)
        qr = generated.json()

        disabled = self.client.patch(
            f"/api/v1/admin/service-position-qrs/{qr['qr_id']}",
            headers=self.admin_headers,
            json={"status": "disabled", "reason": "现场二维码已损坏"},
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.client.cookies.delete("hxy_browser_token")
        entry = self.client.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": "sofa-05",
            "source": qr["source"],
            "entry_token": qr["token"],
            "device_label": "扫码手机",
        })

        self.assertEqual(entry.status_code, 403, entry.text)
        self.assertEqual(entry.json()["detail"]["code"], "QR_DISABLED")

    def test_rebinding_qr_invalidates_old_code_and_creates_new_binding(self):
        self.release_if_active("sofa-07")
        self.release_if_active("sofa-08")
        with self.SessionLocal() as db:
            source_room = db.scalar(select(Room).where(Room.code == "sofa-07"))
            target_room = db.scalar(select(Room).where(Room.code == "sofa-08"))
        original_response = self.client.get(
            f"/api/v1/admin/service-positions/{source_room.id}/qr-link",
            headers=self.admin_headers,
        )
        self.assertEqual(original_response.status_code, 200, original_response.text)
        original = original_response.json()

        rebound_response = self.client.post(
            f"/api/v1/admin/service-position-qrs/{original['qr_id']}/rebind",
            headers=self.admin_headers,
            json={"target_room_id": target_room.id, "reason": "调整现场贴码位置"},
        )
        self.assertEqual(rebound_response.status_code, 200, rebound_response.text)
        rebound = rebound_response.json()
        self.assertNotEqual(rebound["qr_id"], original["qr_id"])
        self.assertEqual(rebound["position_code"], "sofa-08")

        old_entry = self.client.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": "sofa-07",
            "source": original["source"],
            "entry_token": original["token"],
            "device_label": "旧二维码",
        })
        self.assertEqual(old_entry.status_code, 403, old_entry.text)
        self.assertEqual(old_entry.json()["detail"]["code"], "QR_DISABLED")

        self.client.cookies.delete("hxy_browser_token")
        new_entry = self.client.post("/api/v1/entry-sessions", json={
            "store_id": self.store_id,
            "position_code": "sofa-08",
            "source": rebound["source"],
            "entry_token": rebound["token"],
            "device_label": "新二维码",
        })
        self.assertEqual(new_entry.status_code, 200, new_entry.text)

    def test_customer_map_has_eight_sofas_and_hides_room_numbers(self):
        self.release_if_active("sofa-02")
        entry = self.entry("sofa-02")
        response = self.client.get(
            f"/api/v1/stores/{self.store_id}/service-position-map",
            headers={"X-Selection-Token": entry["access_token"]},
            params={"session_id": entry["session"]["id"]},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["positions"]), 8)
        self.assertTrue(all(item["type"] == "sofa" for item in data["positions"]))
        self.assertEqual(next(item for item in data["positions"] if item["is_current"])["code"], "sofa-02")

        room_entry = self.entry("room-01", "room_qr")
        self.assertEqual(room_entry["position"]["customer_label"], "当前房间")
        self.assertNotIn("1", room_entry["position"]["customer_label"])
        room_map = self.client.get(
            f"/api/v1/stores/{self.store_id}/service-position-map",
            headers={"X-Selection-Token": room_entry["access_token"]},
            params={"session_id": room_entry["session"]["id"]},
        )
        current_room = next(item for item in room_map.json()["positions"] if item["is_current"])
        self.assertEqual(current_room["type"], "room")
        self.assertEqual(current_room["customer_label"], "当前房间")
        self.assertNotIn("1", current_room["customer_label"])

    def test_expired_hold_is_released_and_selection_expires(self):
        self.release_if_active("sofa-03")
        entry = self.entry("sofa-03")
        with self.SessionLocal() as db:
            occupancy = db.get(PositionOccupancy, entry["occupancy"]["id"])
            occupancy.hold_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        response = self.client.get(f"/api/v1/stores/{self.store_id}/service-position-map")
        self.assertEqual(response.status_code, 200)
        with self.SessionLocal() as db:
            occupancy = db.get(PositionOccupancy, entry["occupancy"]["id"])
            session = db.get(SelectionSession, entry["session"]["id"])
            self.assertEqual(occupancy.status, "released")
            self.assertIsNone(occupancy.active_room_id)
            self.assertEqual(session.status, "expired")

    def test_tea_only_can_submit_and_two_local_items_apply_discount(self):
        self.release_if_active("sofa-04")
        entry = self.entry("sofa-04")
        session_id = entry["session"]["id"]
        headers = {"X-Selection-Token": entry["access_token"]}
        tea_only = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/submit",
            headers=headers,
            json={"items": [{
                "project_id": "tea",
                "item_type": "preference",
                "chargeable": False,
                "diy_preferences": ["老姜茶"],
            }]},
        )
        self.assertEqual(tea_only.status_code, 200, tea_only.text)

        # 第二个会话验证泡脚减免（幂等提交不会覆盖第一次提交的快照）。
        self.release_if_active("sofa-03")
        second = self.entry("sofa-03")
        headers2 = {"X-Selection-Token": second["access_token"]}
        payload = {"items": [
            {"project_id": self.foot_id, "diy_preferences": ["艾草方"]},
            {"project_id": self.local_id, "diy_preferences": ["肩颈", "精油"]},
            {"project_id": self.local_id, "diy_preferences": ["腿部", "活络油"]},
            {"project_id": "tea", "item_type": "preference", "chargeable": False, "diy_preferences": ["陈皮茶"]},
        ]}
        submitted = self.client.post(
            f"/api/v1/selection-sessions/{second['session']['id']}/submit",
            headers=headers2,
            json=payload,
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(submitted.json()["pricing_snapshot"]["promotion_adjustment_cents"], 0)
        confirmed = self.client.post(
            f"/api/v1/admin/v2/selection-sessions/{second['session']['id']}/confirm",
            headers=self.admin_headers,
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        data = confirmed.json()
        self.assertEqual(data["pricing_snapshot"]["promotion_adjustment_cents"], -3990)
        self.assertEqual(data["store_total_cents"], 13800)
        self.assertEqual(data["member_total_cents"], 9800)
        with self.SessionLocal() as db:
            occupancy = db.get(PositionOccupancy, entry["occupancy"]["id"])
            self.assertEqual(occupancy.status, "waiting_service")
            self.assertIsNone(occupancy.hold_expires_at)

    def test_service_completion_does_not_release_position(self):
        self.release_if_active("sofa-05")
        entry = self.entry("sofa-05")
        session_id = entry["session"]["id"]
        self.client.post(
            f"/api/v1/selection-sessions/{session_id}/submit",
            headers={"X-Selection-Token": entry["access_token"]},
            json={"items": [{"project_id": self.foot_id}]},
        )
        occupancy_id = entry["occupancy"]["id"]
        started = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy_id}/start-service",
            headers=self.admin_headers,
            json={},
        )
        self.assertEqual(started.status_code, 200, started.text)
        finished = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy_id}/finish-service",
            headers=self.admin_headers,
            json={},
        )
        self.assertEqual(finished.status_code, 200, finished.text)
        self.assertEqual(finished.json()["status"], "post_service_present")
        self.assertIsNotNone(finished.json()["active_room_id"])

        departed = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy_id}/confirm-departure",
            headers=self.admin_headers,
            json={},
        )
        self.assertEqual(departed.json()["status"], "cleaning")
        cleaned = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy_id}/finish-cleaning",
            headers=self.admin_headers,
            json={},
        )
        self.assertEqual(cleaned.json()["status"], "released")
        self.assertIsNone(cleaned.json()["active_room_id"])

    def test_force_release_during_service_moves_to_cleaning_instead_of_available(self):
        self.release_if_active("sofa-06")
        entry = self.entry("sofa-06")
        session_id = entry["session"]["id"]
        submitted = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/submit",
            headers={"X-Selection-Token": entry["access_token"]},
            json={"items": [{"project_id": self.foot_id}]},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        occupancy_id = entry["occupancy"]["id"]
        started = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy_id}/start-service",
            headers=self.admin_headers,
            json={},
        )
        self.assertEqual(started.status_code, 200, started.text)

        response = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy_id}/force-release",
            headers=self.admin_headers,
            json={
                "reason_code": "service_aborted",
                "target_state": "cleaning",
                "reason": "顾客身体不适，服务中止并已离位",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "cleaning")
        self.assertIsNotNone(response.json()["active_room_id"])
        self.assertIsNotNone(response.json()["actual_service_end_at"])

    def test_admin_can_move_active_occupancy(self):
        self.release_if_active("sofa-06")
        self.release_if_active("sofa-07")
        entry = self.entry("sofa-06")
        with self.SessionLocal() as db:
            target = db.scalar(select(Room).where(Room.code == "sofa-07"))

        response = self.client.post(
            f"/api/v1/admin/occupancies/{entry['occupancy']['id']}/move",
            headers=self.admin_headers,
            json={
                "target_room_id": target.id,
                "version": entry["occupancy"]["version"],
                "reason": "顾客现场确认换位",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["active_room_id"], target.id)
        self.assertEqual(response.json()["room_id"], target.id)

    def test_customer_move_rejects_a_service_position_used_by_the_legacy_service_flow(self):
        self.release_if_active("sofa-01")
        self.release_if_active("sofa-02")
        entry = self.entry("sofa-01")
        self.set_room_status("sofa-02", "in_service")
        self.addCleanup(self.set_room_status, "sofa-02", "available")

        with self.SessionLocal() as db:
            target = db.scalar(select(Room).where(Room.code == "sofa-02"))
        response = self.client.post(
            f"/api/v1/occupancies/{entry['occupancy']['id']}/move",
            headers={"X-Selection-Token": entry["access_token"]},
            json={
                "target_room_id": target.id,
                "version": entry["occupancy"]["version"],
                "reason": "顾客误选服务位",
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "POSITION_UNAVAILABLE")

    def test_customer_cannot_move_after_the_selection_is_submitted(self):
        self.release_if_active("sofa-01")
        self.release_if_active("sofa-02")
        entry = self.entry("sofa-01")
        submitted = self.client.post(
            f"/api/v1/selection-sessions/{entry['session']['id']}/submit",
            headers={"X-Selection-Token": entry["access_token"]},
            json={"items": [{"project_id": self.foot_id}]},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        with self.SessionLocal() as db:
            target = db.scalar(select(Room).where(Room.code == "sofa-02"))
            occupancy = db.get(PositionOccupancy, entry["occupancy"]["id"])

        response = self.client.post(
            f"/api/v1/occupancies/{occupancy.id}/move",
            headers={"X-Selection-Token": entry["access_token"]},
            json={
                "target_room_id": target.id,
                "version": occupancy.version,
                "reason": "测试提交后换位",
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "POSITION_LOCKED")

    def test_admin_move_rejects_a_service_position_used_by_the_legacy_service_flow(self):
        self.release_if_active("sofa-03")
        self.release_if_active("sofa-04")
        entry = self.entry("sofa-03")
        self.set_room_status("sofa-04", "cleaning")
        self.addCleanup(self.set_room_status, "sofa-04", "available")

        with self.SessionLocal() as db:
            target = db.scalar(select(Room).where(Room.code == "sofa-04"))
        response = self.client.post(
            f"/api/v1/admin/occupancies/{entry['occupancy']['id']}/move",
            headers=self.admin_headers,
            json={
                "target_room_id": target.id,
                "version": entry["occupancy"]["version"],
                "reason": "前台调整服务位",
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "POSITION_UNAVAILABLE")

    def test_admin_move_rejects_an_occupied_target(self):
        self.release_if_active("sofa-07")
        self.release_if_active("sofa-08")
        first = self.entry("sofa-07")
        second = self.entry("sofa-08")
        with self.SessionLocal() as db:
            occupied_target = db.scalar(select(Room).where(Room.code == "sofa-08"))

        response = self.client.post(
            f"/api/v1/admin/occupancies/{first['occupancy']['id']}/move",
            headers=self.admin_headers,
            json={
                "target_room_id": occupied_target.id,
                "version": first["occupancy"]["version"],
                "reason": "测试冲突",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "POSITION_OCCUPIED")
        self.assertEqual(second["position"]["code"], "sofa-08")

    def test_kiosk_and_room_entries_cannot_change_position(self):
        cases = [
            ("sofa-01", "kiosk", "sofa-02"),
            ("room-01", "room_qr", "sofa-03"),
        ]
        for current_code, source, target_code in cases:
            with self.subTest(source=source):
                self.release_if_active(current_code)
                self.release_if_active(target_code)
                entry = self.kiosk_entry(current_code) if source == "kiosk" else self.entry(current_code, source)
                with self.SessionLocal() as db:
                    target = db.scalar(select(Room).where(Room.code == target_code))

                response = self.client.post(
                    f"/api/v1/occupancies/{entry['occupancy']['id']}/move",
                    headers={"X-Selection-Token": entry["access_token"]},
                    json={
                        "target_room_id": target.id,
                        "version": entry["occupancy"]["version"],
                        "reason": "顾客尝试自行换位",
                    },
                )

                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(response.json()["detail"]["code"], "POSITION_LOCKED")
                self.release_if_active(current_code)


if __name__ == "__main__":
    unittest.main()
