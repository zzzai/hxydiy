import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import admin_v2
from app.api.admin import create_staff_token, hash_password, staff_snapshot
from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    CouponTemplate,
    UserCoupon,
    AuditLog,
    EventLog,
    Order,
    PageContent,
    PageContentVersion,
    OperationalException,
    PositionOccupancy,
    PriceBook,
    Product,
    Project,
    SelectionSession,
    ServiceFeedback,
    ServiceLine,
    Staff,
    Store,
    User,
)
from app.models.operations import Room, Technician
from app.models.scrm import AutomationLog, AutomationRule
from app.models.room_assign import RoomAssignment
from app.models.orders import ORDER_STATUSES


class AdminV2ContractTests(unittest.TestCase):
    def test_staff_snapshot_preserves_headquarters_admin_role(self):
        headquarters = SimpleNamespace(role="admin", store_id=None, technician_id=None, id=1, name="总部")
        store_admin = SimpleNamespace(role="admin", store_id=2, technician_id=None, id=2, name="店长")

        self.assertEqual(staff_snapshot(headquarters)["role"], "admin")
        self.assertEqual(staff_snapshot(store_admin)["role"], "manager")

    def test_project_write_contract_preserves_legacy_diy_options(self):
        body = admin_v2.ProjectCreate(
            store_id=1,
            code="P-DIY-CONTRACT",
            name="兼容 DIY 项目",
            prices={"store": 3_990},
            detail_modules=[],
            diy_options=[{"label": "力度", "note": "适中"}],
        )
        self.assertEqual(body.diy_options[0]["label"], "力度")
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(
            bind=cls.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        Base.metadata.create_all(cls.engine)

        with cls.SessionLocal() as db:
            store = Store(
                store_code="test-store",
                name="测试门店",
                city="安阳",
                address="测试地址",
                status="open",
            )
            db.add(store)
            db.flush()
            other_store = Store(
                store_code="other-store",
                name="其他门店",
                city="安阳",
                address="其他地址",
                status="open",
            )
            db.add(other_store)
            db.flush()
            staff = Staff(
                username="admin",
                password_hash=hash_password("preview-pass"),
                name="管理员",
                role="admin",
                store_id=store.id,
                status="active",
            )
            read_only_staff = Staff(
                username="staff",
                password_hash=hash_password("staff-pass"),
                name="店员",
                role="staff",
                store_id=store.id,
                status="active",
            )
            headquarters_admin = Staff(
                username="headquarters",
                password_hash=hash_password("headquarters-pass"),
                name="总部管理员",
                role="admin",
                store_id=None,
                status="active",
            )
            user = User(openid="test-openid")
            other_user = User(openid="other-openid", nickname="其他门店顾客")
            room = Room(
                store_id=store.id,
                code="R-01",
                name="1号沙发",
                room_type="sofa",
                room_group="sofa",
                capacity=2,
                used_count=1,
                current_tech="王师傅",
                status="occupied",
            )
            tech = Technician(
                store_id=store.id,
                code="T-01",
                name="王师傅",
            )
            other_room = Room(
                store_id=other_store.id,
                code="R-OTHER",
                name="其他门店房间",
            )
            other_tech = Technician(
                store_id=other_store.id,
                code="T-OTHER",
                name="其他门店技师",
            )
            own_project = Project(
                store_id=store.id,
                code="P-OWN",
                category="bath",
                name="本店项目",
            )
            other_project = Project(
                store_id=other_store.id,
                code="P-OTHER",
                category="bath",
                name="其他门店项目",
            )
            own_product = Product(
                store_id=store.id,
                code="G-OWN",
                name="本店商品",
                product_type="foot",
                price_cents=990,
            )
            other_product = Product(
                store_id=other_store.id,
                code="G-OTHER",
                name="其他门店商品",
                product_type="foot",
                price_cents=990,
            )
            db.add_all([
                staff, read_only_staff, headquarters_admin, user, other_user, room, tech, other_room, other_tech,
                own_project, other_project, own_product, other_product,
            ])
            db.flush()
            coupon = CouponTemplate(
                store_id=store.id,
                code="test-coupon",
                name="测试券",
                amount_cents=500,
                status="draft",
            )
            db.add(coupon)
            db.add(RoomAssignment(
                room_id=room.id,
                technician_id=tech.id,
                project_ids=[],
            ))
            db.add_all([
                Order(
                    order_no="PENDING-1",
                    order_type="service",
                    user_id=user.id,
                    store_id=store.id,
                    items=[],
                    pay_amount_cents=9900,
                    status="pending_checkout",
                ),
                Order(
                    order_no="COMPLETED-1",
                    order_type="service",
                    user_id=user.id,
                    store_id=store.id,
                    items=[],
                    pay_amount_cents=6900,
                    status="completed",
                ),
                Order(
                    order_no="OTHER-PENDING",
                    order_type="service",
                    user_id=other_user.id,
                    store_id=other_store.id,
                    items=[],
                    pay_amount_cents=19900,
                    status="pending_checkout",
                ),
                Order(
                    order_no="OTHER-PAID",
                    order_type="service",
                    user_id=other_user.id,
                    store_id=other_store.id,
                    items=[],
                    pay_amount_cents=29900,
                    status="paid",
                ),
            ])
            db.commit()
            cls.staff_id = staff.id
            cls.read_only_staff_id = read_only_staff.id
            cls.headquarters_admin_id = headquarters_admin.id
            cls.current_staff_id = staff.id
            cls.room_id = room.id
            cls.other_store_id = other_store.id
            cls.other_room_id = other_room.id
            cls.own_project_id = own_project.id
            cls.other_project_id = other_project.id
            cls.coupon_id = coupon.id
            cls.auth_headers = {
                "Authorization": f"Bearer {create_staff_token(staff.id, staff.role)}"
            }
            cls.staff_auth_headers = {
                "Authorization": f"Bearer {create_staff_token(read_only_staff.id, read_only_staff.role)}"
            }

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.auth_patch = patch.object(
            admin_v2,
            "_current_staff",
            side_effect=lambda _authorization, db: db.get(Staff, cls.current_staff_id),
        )
        cls.auth_patch.start()
        cls.client = TestClient(app)

    def test_openapi_is_available_under_the_api_prefix(self):
        response = self.client.get("/api/v1/openapi.json")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"].split(";")[0], "application/json")
        self.assertIn("/api/v1/selection-sessions", response.json()["paths"])

    def test_openapi_describes_admin_catalog_security_and_responses(self):
        document = self.client.get("/api/v1/openapi.json").json()

        bearer = document["components"]["securitySchemes"]["StaffBearer"]
        self.assertEqual(bearer, {"type": "http", "scheme": "bearer"})

        operations = {
            ("/api/v1/admin/v2/projects", "get"),
            ("/api/v1/admin/v2/projects", "post"),
            ("/api/v1/admin/v2/projects/{proj_id}", "patch"),
            ("/api/v1/admin/v2/products", "get"),
            ("/api/v1/admin/v2/products", "post"),
            ("/api/v1/admin/v2/products/{prod_id}", "patch"),
        }
        for path, method in operations:
            with self.subTest(path=path, method=method):
                operation = document["paths"][path][method]
                self.assertEqual(operation["security"], [{"StaffBearer": []}])
                self.assertNotIn(
                    "authorization",
                    {
                        parameter.get("name")
                        for parameter in operation.get("parameters", [])
                        if parameter.get("in") == "header"
                    },
                )
                response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
                self.assertTrue(response_schema)

        self.assertIn("AdminProject", document["components"]["schemas"])
        self.assertIn("AdminProduct", document["components"]["schemas"])

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.auth_patch.stop()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def test_store_model_contains_publication_fields(self):
        self.assertTrue(hasattr(Store, "status"))
        self.assertTrue(hasattr(Store, "published_at"))
        self.assertTrue(hasattr(Store, "updated_at"))

    def test_order_statuses_include_pending_checkout(self):
        self.assertIn("pending_checkout", ORDER_STATUSES)

    def test_login_returns_staff_store_context(self):
        response = self.client.post(
            "/api/v1/admin/login",
            json={"username": "admin", "password": "preview-pass"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["staff"]["store_id"], 1)
        self.assertEqual(response.json()["staff"]["store_name"], "测试门店")

    def test_public_store_endpoint_serializes_store_status(self):
        response = self.client.get("/api/v1/stores")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["status"], "open")

    def test_public_store_list_hides_non_open_stores(self):
        with self.SessionLocal() as db:
            store = Store(
                store_code="hidden-preparing-store",
                name="筹备门店",
                city="安阳",
                address="筹备地址",
                status="preparing",
            )
            db.add(store)
            db.commit()
        response = self.client.get("/api/v1/stores")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("hidden-preparing-store", [item["store_code"] for item in response.json()])

    def test_closed_store_rejects_new_selection_session(self):
        with self.SessionLocal() as db:
            store = Store(
                store_code="closed-selection-store",
                name="停业门店",
                city="安阳",
                address="停业地址",
                status="closed",
            )
            db.add(store)
            db.commit()
            store_id = store.id
        response = self.client.post(
            "/api/v1/selection-sessions",
            json={"store_id": store_id, "source": "in_store"},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "STORE_NOT_OPEN")

    def test_closed_store_rejects_new_order(self):
        with self.SessionLocal() as db:
            store = Store(
                store_code="closed-order-store",
                name="停业下单门店",
                city="安阳",
                address="停业下单地址",
                status="closed",
            )
            user = User(openid="closed-order-customer", phone="13800009999")
            db.add_all([store, user])
            db.commit()
            store_id, token = store.id, create_access_token(
                str(user.id), user.openid, user.customer_login_version,
            )
        response = self.client.post(
            "/api/v1/orders",
            json={"store_id": store_id, "items": [], "order_type": "service"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "STORE_NOT_OPEN")

    def test_room_list_exposes_dashboard_fields(self):
        response = self.client.get("/api/v1/admin/v2/rooms")
        self.assertEqual(response.status_code, 200)
        room = response.json()["items"][0]
        self.assertEqual(room["room_group"], "sofa")
        self.assertEqual(room["used_count"], 1)
        self.assertEqual(room["current_tech"], "王师傅")

    def test_room_stats_excludes_inactive_positions_from_available(self):
        with self.SessionLocal() as db:
            room = Room(
                store_id=1,
                code="INACTIVE-STATS-01",
                name="停用统计测试位",
                room_type="sofa",
                room_group="sofa",
                is_service_position=True,
                customer_selectable=True,
                status="available",
                operational_status="inactive",
            )
            db.add(room)
            db.commit()
            room_id = room.id
        try:
            response = self.client.get("/api/v1/admin/v2/rooms/stats")
            self.assertEqual(response.status_code, 200, response.text)
            stats = response.json()
            self.assertGreaterEqual(stats["inactive"], 1)
            self.assertGreaterEqual(stats["total"], stats["available"] + stats["inactive"])
        finally:
            with self.SessionLocal() as db:
                db.query(Room).filter(Room.id == room_id).delete()
                db.commit()

    def test_room_container_can_own_independent_bed_positions(self):
        container = self.client.post(
            "/api/v1/admin/v2/rooms",
            json={
                "store_id": 1,
                "code": "SPACE-01",
                "name": "测试双床房",
                "room_type": "room",
                "room_group": "massage",
                "is_space_container": True,
            },
        )
        self.assertEqual(container.status_code, 200, container.text)
        container_id = container.json()["id"]
        try:
            for code, name in (("BED-01A", "A床"), ("BED-01B", "B床")):
                response = self.client.post(
                    "/api/v1/admin/v2/rooms",
                    json={
                        "store_id": 1,
                        "code": code,
                        "name": name,
                        "room_type": "bed",
                        "room_group": "massage",
                        "parent_room_id": container_id,
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)

            listing = self.client.get("/api/v1/admin/v2/rooms")
            children = [
                item for item in listing.json()["items"]
                if item.get("parent_room_id") == container_id
            ]
            self.assertEqual([item["code"] for item in children], ["BED-01A", "BED-01B"])
            self.assertTrue(all(item["is_service_position"] for item in children))
            parent = next(item for item in listing.json()["items"] if item["id"] == container_id)
            self.assertTrue(parent["is_space_container"])
            self.assertFalse(parent["is_service_position"])
            self.assertEqual(parent["bed_count"], 2)
        finally:
            with self.SessionLocal() as db:
                db.query(Room).filter(Room.parent_room_id == container_id).delete()
                db.query(Room).filter(Room.id == container_id).delete()
                db.commit()

    def test_diy_cannot_operate_physical_service_position(self):
        with self.SessionLocal() as db:
            container = Room(
                store_id=1,
                code="SPACE-NO-OPERATE",
                name="不可占用房间",
                room_type="room",
                room_group="massage",
                is_space_container=True,
            )
            db.add(container)
            db.commit()
            container_id = container.id
        try:
            response = self.client.post(
                f"/api/v1/admin/v2/rooms/{container_id}/operate",
                json={"action": "occupied"},
            )
            self.assertEqual(response.status_code, 410, response.text)
            self.assertEqual(response.json()["detail"]["code"], "DIY_PHYSICAL_RESOURCE_FORBIDDEN")
        finally:
            with self.SessionLocal() as db:
                db.query(Room).filter(Room.id == container_id).delete()
                db.commit()

    def test_live_operations_board_excludes_space_containers(self):
        with self.SessionLocal() as db:
            container = Room(
                store_id=1,
                code="SPACE-NOT-A-RESOURCE",
                name="运营看板不可见容器",
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
            response = self.client.get("/api/v1/operations/live-board", headers=self.auth_headers)
            self.assertEqual(response.status_code, 200, response.text)
            resource_names = [item["name"] for item in response.json()["resources"]["rooms"]]
            self.assertNotIn("运营看板不可见容器", resource_names)
        finally:
            with self.SessionLocal() as db:
                db.query(Room).filter(Room.id == container_id).delete()
                db.commit()

    def test_headquarters_admin_can_manage_store_master_data(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        created_id = None
        try:
            listing = self.client.get("/api/v1/admin/v2/stores")
            self.assertEqual(listing.status_code, 200, listing.text)
            self.assertGreaterEqual(listing.json()["total"], 2)

            created = self.client.post(
                "/api/v1/admin/v2/stores",
                json={
                    "store_code": "milestone-store",
                    "name": "里程碑测试门店",
                    "city": "安阳",
                    "address": "测试路 1 号",
                    "phone": "03720000000",
                    "business_hours": "10:00-22:00",
                    "status": "preparing",
                },
            )
            self.assertEqual(created.status_code, 200, created.text)
            created_id = created.json()["id"]
            with self.SessionLocal() as db:
                db.add_all([
                    Room(
                        store_id=created_id,
                        code=f"milestone-room-{created_id}",
                        name="里程碑服务位",
                        room_type="sofa",
                        is_service_position=True,
                        is_space_container=False,
                        operational_status="active",
                    ),
                    Project(
                        store_id=created_id,
                        code=f"milestone-project-{created_id}",
                        category="bath",
                        name="里程碑项目",
                        publication_status="published",
                    ),
                    PageContent(store_id=created_id, page_key="diy-home", published=True),
                ])
                db.commit()

            updated = self.client.patch(
                f"/api/v1/admin/v2/stores/{created_id}",
                json={"name": "里程碑正式门店", "status": "open"},
            )
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertEqual(updated.json()["name"], "里程碑正式门店")
            self.assertEqual(updated.json()["status"], "open")
        finally:
            self.__class__.current_staff_id = self.staff_id
            if created_id:
                with self.SessionLocal() as db:
                    db.query(PageContent).filter(PageContent.store_id == created_id).delete()
                    db.query(Project).filter(Project.store_id == created_id).delete()
                    db.query(Room).filter(Room.store_id == created_id).delete()
                    db.query(Store).filter(Store.id == created_id).delete()
                    db.commit()

    def test_store_lifecycle_transition_and_close_guard(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        store_id = user_id = order_id = None
        try:
            with self.SessionLocal() as db:
                store = Store(
                    store_code="lifecycle-guard-store",
                    name="生命周期测试门店",
                    city="安阳",
                    address="测试路 2 号",
                    business_hours="10:00-22:00",
                    status="preparing",
                )
                user = User(openid="lifecycle-guard-user", phone="13800008888")
                db.add_all([store, user])
                db.flush()
                db.add_all([
                    Room(
                        store_id=store.id,
                        code=f"lifecycle-room-{store.id}",
                        name="生命周期服务位",
                        room_type="sofa",
                        is_service_position=True,
                        is_space_container=False,
                        operational_status="active",
                    ),
                    Project(
                        store_id=store.id,
                        code=f"lifecycle-project-{store.id}",
                        category="bath",
                        name="生命周期项目",
                        publication_status="published",
                    ),
                    PageContent(store_id=store.id, page_key="diy-home", published=True),
                ])
                order = Order(
                    store_id=store.id,
                    user_id=user.id,
                    order_no="LIFECYCLE-ACTIVE-1",
                    order_type="service",
                    status="paid",
                    pay_status="paid",
                    pay_amount_cents=9900,
                )
                db.add(order)
                db.commit()
                store_id, user_id, order_id = store.id, user.id, order.id

            invalid = self.client.patch(
                f"/api/v1/admin/v2/stores/{store_id}",
                json={"status": "suspended"},
            )
            self.assertEqual(invalid.status_code, 409, invalid.text)
            self.assertEqual(invalid.json()["detail"]["code"], "INVALID_STORE_TRANSITION")

            opened = self.client.patch(
                f"/api/v1/admin/v2/stores/{store_id}",
                json={"status": "open", "reason": "完成开业准备"},
            )
            self.assertEqual(opened.status_code, 200, opened.text)

            blocked = self.client.patch(
                f"/api/v1/admin/v2/stores/{store_id}",
                json={"status": "closed", "reason": "测试停业"},
            )
            self.assertEqual(blocked.status_code, 409, blocked.text)
            self.assertEqual(blocked.json()["detail"]["code"], "STORE_HAS_ACTIVE_BUSINESS")

            suspended = self.client.patch(
                f"/api/v1/admin/v2/stores/{store_id}",
                json={"status": "suspended", "reason": "临时暂停"},
            )
            self.assertEqual(suspended.status_code, 200, suspended.text)

            with self.SessionLocal() as db:
                db.query(Order).filter(Order.id == order_id).delete()
                db.commit()

            closed = self.client.patch(
                f"/api/v1/admin/v2/stores/{store_id}",
                json={"status": "closed", "reason": "完成收尾"},
            )
            self.assertEqual(closed.status_code, 200, closed.text)
            self.assertEqual(closed.json()["status"], "closed")
        finally:
            with self.SessionLocal() as db:
                if order_id:
                    db.query(Order).filter(Order.id == order_id).delete()
                if store_id:
                    db.query(PageContent).filter(PageContent.store_id == store_id).delete()
                    db.query(Project).filter(Project.store_id == store_id).delete()
                    db.query(Room).filter(Room.store_id == store_id).delete()
                    db.query(Store).filter(Store.id == store_id).delete()
                if user_id:
                    db.query(User).filter(User.id == user_id).delete()
                db.commit()
            self.__class__.current_staff_id = self.staff_id

    def test_store_open_requires_opening_readiness(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        store_id = None
        try:
            with self.SessionLocal() as db:
                store = Store(
                    store_code="opening-check-store",
                    name="未准备好门店",
                    city="安阳",
                    address="测试路 3 号",
                    business_hours="10:00-22:00",
                    status="preparing",
                )
                db.add(store)
                db.commit()
                store_id = store.id

            check = self.client.get(f"/api/v1/admin/v2/stores/{store_id}/opening-check")
            self.assertEqual(check.status_code, 200, check.text)
            self.assertFalse(check.json()["ready"])
            self.assertEqual(
                {item["key"] for item in check.json()["checks"] if not item["passed"]},
                {"service_position", "published_project", "published_page"},
            )

            blocked = self.client.patch(
                f"/api/v1/admin/v2/stores/{store_id}",
                json={"status": "open", "reason": "提前开业"},
            )
            self.assertEqual(blocked.status_code, 409, blocked.text)
            self.assertEqual(blocked.json()["detail"]["code"], "STORE_OPENING_CHECK_FAILED")
        finally:
            if store_id:
                with self.SessionLocal() as db:
                    db.query(Store).filter(Store.id == store_id).delete()
                    db.commit()
            self.__class__.current_staff_id = self.staff_id

    def test_page_content_publish_creates_versions_and_rolls_back(self):
        page_key = "test-version-page"
        payload = {
            "title": "版本一",
            "subtitle": "第一版",
            "promo_banners": [],
            "tea_options": [],
            "coupon_prompt": {},
            "brand_story": {},
            "published": True,
        }
        try:
            first = self.client.put(
                "/api/v1/admin/v2/page-content",
                params={"page_key": page_key},
                json=payload,
                headers=self.auth_headers,
            )
            self.assertEqual(first.status_code, 200, first.text)
            versions = self.client.get(
                "/api/v1/admin/v2/page-content/versions",
                params={"page_key": page_key},
                headers=self.auth_headers,
            )
            self.assertEqual(versions.status_code, 200, versions.text)
            self.assertEqual(versions.json()["total"], 1)
            first_version_id = versions.json()["items"][0]["id"]

            second = self.client.put(
                "/api/v1/admin/v2/page-content",
                params={"page_key": page_key},
                json={**payload, "title": "版本二", "subtitle": "第二版"},
                headers=self.auth_headers,
            )
            self.assertEqual(second.status_code, 200, second.text)
            versions = self.client.get(
                "/api/v1/admin/v2/page-content/versions",
                params={"page_key": page_key},
                headers=self.auth_headers,
            )
            self.assertEqual(versions.json()["total"], 2)

            rollback = self.client.post(
                f"/api/v1/admin/v2/page-content/versions/{first_version_id}/rollback",
                params={"page_key": page_key},
                headers=self.auth_headers,
            )
            self.assertEqual(rollback.status_code, 200, rollback.text)
            self.assertEqual(rollback.json()["title"], "版本一")
            versions = self.client.get(
                "/api/v1/admin/v2/page-content/versions",
                params={"page_key": page_key},
                headers=self.auth_headers,
            )
            self.assertEqual(versions.json()["total"], 3)
            self.assertEqual(versions.json()["items"][0]["version_no"], 3)
        finally:
            with self.SessionLocal() as db:
                db.query(PageContentVersion).filter(PageContentVersion.page_key == page_key).delete()
                db.query(PageContent).filter(PageContent.page_key == page_key).delete()
                db.query(AuditLog).filter(AuditLog.action.in_(["update_page_content", "rollback_page_content"])).delete()
                db.commit()

    def test_headquarters_admin_can_open_content_marketing_automation(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        headers = {"Authorization": f"Bearer {create_staff_token(self.headquarters_admin_id, 'admin')}"}
        try:
            for path in (
                "/api/v1/admin/v2/page-content",
                "/api/v1/admin/coupons",
                "/api/v1/admin/v2/automations",
                "/api/v1/admin/v2/automations/trigger-events",
            ):
                response = self.client.get(path, headers=headers)
                self.assertEqual(response.status_code, 200, f"{path}: {response.text}")
        finally:
            self.__class__.current_staff_id = self.staff_id

    def test_headquarters_admin_can_view_cross_store_exception_queue(self):
        with self.SessionLocal() as db:
            store_id = db.get(Staff, self.staff_id).store_id
            db.add_all([
                OperationalException(
                    store_id=store_id,
                    exception_type="missing_selection",
                    severity="warning",
                    status="open",
                    dedupe_key="hq-test-main",
                    title="主店对账异常",
                    detail={},
                    entity_type="order",
                    entity_id="1",
                ),
                OperationalException(
                    store_id=self.other_store_id,
                    exception_type="amount_mismatch",
                    severity="warning",
                    status="open",
                    dedupe_key="hq-test-other",
                    title="其他门店对账异常",
                    detail={},
                    entity_type="order",
                    entity_id="2",
                ),
            ])
            db.commit()
        self.__class__.current_staff_id = self.headquarters_admin_id
        headers = {"Authorization": f"Bearer {create_staff_token(self.headquarters_admin_id, 'admin')}"}
        try:
            response = self.client.get("/api/v1/admin/v2/brand/exceptions", headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["total"], 2)
            self.assertEqual({row["store_id"] for row in body["items"]}, {store_id, self.other_store_id})
            self.assertEqual(len(body["summary"]["by_store"]), 2)
        finally:
            self.__class__.current_staff_id = self.staff_id
            with self.SessionLocal() as db:
                db.query(OperationalException).filter(OperationalException.dedupe_key.in_(["hq-test-main", "hq-test-other"])).delete()
                db.commit()

    def test_automation_rule_logs_are_visible_and_scoped(self):
        with self.SessionLocal() as db:
            staff = db.get(Staff, self.staff_id)
            user = User(openid="automation-log-user", phone="13700001234")
            db.add(user)
            db.flush()
            rule = AutomationRule(store_id=staff.store_id, name="日志测试规则", trigger_event="new_user")
            db.add(rule)
            db.flush()
            db.add(AutomationLog(rule_id=rule.id, user_id=user.id, action_type="grant_coupon", success=False, error_message="库存不足"))
            db.commit()
            rule_id, user_id = rule.id, user.id
        try:
            response = self.client.get(f"/api/v1/admin/v2/automations/{rule_id}/logs")
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["total"], 1)
            self.assertEqual(body["items"][0]["customer"], "用户%d" % user_id)
            self.assertFalse(body["items"][0]["success"])
            self.assertEqual(body["items"][0]["error_message"], "库存不足")
        finally:
            with self.SessionLocal() as db:
                db.query(AutomationLog).filter(AutomationLog.rule_id == rule_id).delete()
                db.query(AutomationRule).filter(AutomationRule.id == rule_id).delete()
                db.query(User).filter(User.id == user_id).delete()
                db.commit()

    def test_store_manager_can_only_toggle_project_publication(self):
        self.__class__.current_staff_id = self.staff_id
        blocked = self.client.patch(
            "/api/v1/admin/v2/projects/1",
            json={"name": "店长不应修改的名称"},
        )
        self.assertEqual(blocked.status_code, 403, blocked.text)
        self.assertEqual(blocked.json()["detail"]["code"], "HEADQUARTERS_ADMIN_REQUIRED")

        allowed = self.client.patch(
            "/api/v1/admin/v2/projects/1",
            json={"publication_status": "inactive"},
        )
        self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_store_manager_cannot_modify_product_master_data(self):
        self.__class__.current_staff_id = self.staff_id
        blocked = self.client.post(
            "/api/v1/admin/v2/products/1",
            json={"name": "店长不应修改商品"},
        )
        self.assertEqual(blocked.status_code, 403, blocked.text)
        self.assertEqual(blocked.json()["detail"]["code"], "HEADQUARTERS_ADMIN_REQUIRED")

    def test_headquarters_admin_can_modify_project_and_product_master_data(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        project = self.client.patch(
            "/api/v1/admin/v2/projects/1",
            json={"name": "总部修改项目"},
        )
        self.assertEqual(project.status_code, 200, project.text)
        product = self.client.post(
            "/api/v1/admin/v2/products/1",
            json={"name": "总部修改商品"},
        )
        self.assertEqual(product.status_code, 200, product.text)
        self.__class__.current_staff_id = self.staff_id

    def test_product_patch_supports_headquarters_edit_and_store_manager_toggle(self):
        """管理端 Refine 使用 PATCH；总部可编辑主数据，店长只能改上下架。"""
        self.__class__.current_staff_id = self.headquarters_admin_id
        with self.SessionLocal() as db:
            product = db.get(Product, 1)
            original = {
                "name": product.name,
                "price_cents": product.price_cents,
                "image_url": product.image_url,
                "publication_status": product.publication_status,
            }
        try:
            updated = self.client.patch(
                "/api/v1/admin/v2/products/1",
                json={"name": "总部编辑商品", "price_cents": 1290, "image_url": "media/1"},
            )
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertEqual(updated.json()["name"], "总部编辑商品")

            self.__class__.current_staff_id = self.staff_id
            allowed = self.client.patch(
                "/api/v1/admin/v2/products/1",
                json={"publication_status": "published"},
            )
            self.assertEqual(allowed.status_code, 200, allowed.text)

            invalid_status = self.client.patch(
                "/api/v1/admin/v2/products/1",
                json={"publication_status": "archived"},
            )
            self.assertEqual(invalid_status.status_code, 403, invalid_status.text)

            self.__class__.current_staff_id = self.headquarters_admin_id
            forced_offline = self.client.patch(
                "/api/v1/admin/v2/products/1",
                json={"publication_status": "archived"},
            )
            self.assertEqual(forced_offline.status_code, 200, forced_offline.text)

            self.__class__.current_staff_id = self.staff_id
            restore_forbidden = self.client.patch(
                "/api/v1/admin/v2/products/1",
                json={"publication_status": "published"},
            )
            self.assertEqual(restore_forbidden.status_code, 403, restore_forbidden.text)

            blocked = self.client.patch(
                "/api/v1/admin/v2/products/1",
                json={"name": "店长不应修改商品"},
            )
            self.assertEqual(blocked.status_code, 403, blocked.text)
            self.assertEqual(blocked.json()["detail"]["code"], "HEADQUARTERS_ADMIN_REQUIRED")
        finally:
            self.__class__.current_staff_id = self.headquarters_admin_id
            self.client.patch("/api/v1/admin/v2/products/1", json=original)
            self.__class__.current_staff_id = self.staff_id

    def test_headquarters_can_manage_product_member_price_order_and_details(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        with self.SessionLocal() as db:
            product = db.get(Product, 1)
            original = {
                "price_cents": product.price_cents,
                "member_price_cents": product.member_price_cents,
                "display_order": product.display_order,
                "detail_modules": product.detail_modules,
            }
        try:
            response = self.client.patch(
                "/api/v1/admin/v2/products/1",
                json={
                    "price_cents": 1990,
                    "member_price_cents": 1590,
                    "display_order": 3,
                    "detail_modules": [{"type": "text", "body": "门店使用说明"}],
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["member_price_cents"], 1590)
            self.assertEqual(response.json()["display_order"], 3)
            self.assertEqual(response.json()["detail_modules"], [{
                "type": "text",
                "title": "",
                "body": "门店使用说明",
                "image_url": "",
            }])

            cleared = self.client.patch(
                "/api/v1/admin/v2/products/1",
                json={"member_price_cents": None},
            )
            self.assertEqual(cleared.status_code, 200, cleared.text)
            self.assertIsNone(cleared.json()["member_price_cents"])
        finally:
            self.client.patch("/api/v1/admin/v2/products/1", json=original)
            self.__class__.current_staff_id = self.staff_id

    def test_product_member_price_cannot_exceed_store_price(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        response = self.client.patch(
            "/api/v1/admin/v2/products/1",
            json={"price_cents": 1000, "member_price_cents": 1001},
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["detail"]["code"], "MEMBER_PRICE_EXCEEDS_STORE_PRICE")
        self.__class__.current_staff_id = self.staff_id

    def test_product_details_reject_unknown_module_types(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        with self.SessionLocal() as db:
            original = db.get(Product, 1).detail_modules
        try:
            response = self.client.patch(
                "/api/v1/admin/v2/products/1",
                json={"detail_modules": [{"type": "script", "body": "不受控内容"}]},
            )
            self.assertEqual(response.status_code, 422, response.text)
        finally:
            self.client.patch("/api/v1/admin/v2/products/1", json={"detail_modules": original})
            self.__class__.current_staff_id = self.staff_id

    def test_legacy_product_post_accepts_full_object_and_keeps_legacy_response(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        with self.SessionLocal() as db:
            product = db.get(Product, 1)
            original_name = product.name
            store_id = product.store_id
        try:
            response = self.client.post(
                "/api/v1/admin/v2/products/1",
                json={
                    "id": 1,
                    "store_id": store_id,
                    "name": "旧客户端更新商品",
                    "legacy_client_field": "ignored",
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {"ok": True})
            with self.SessionLocal() as db:
                self.assertEqual(db.get(Product, 1).name, "旧客户端更新商品")
        finally:
            self.client.patch("/api/v1/admin/v2/products/1", json={"name": original_name})
            self.__class__.current_staff_id = self.staff_id

    def test_headquarters_product_update_audit_uses_target_store(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        response = self.client.patch(
            "/api/v1/admin/v2/products/1",
            json={"desc": "审计门店归属测试"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        with self.SessionLocal() as db:
            product = db.get(Product, 1)
            audit = db.scalar(
                select(AuditLog)
                .where(AuditLog.action == "update_product", AuditLog.entity_id == "1")
                .order_by(AuditLog.id.desc())
            )
            self.assertIsNotNone(audit)
            self.assertEqual(audit.store_id, product.store_id)
        self.__class__.current_staff_id = self.staff_id

    def test_product_list_supports_server_pagination_without_breaking_legacy_list(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        first_page = self.client.get("/api/v1/admin/v2/products", params={"page": 1, "page_size": 1})
        second_page = self.client.get("/api/v1/admin/v2/products", params={"page": 2, "page_size": 1})
        legacy = self.client.get("/api/v1/admin/v2/products")
        self.assertEqual(first_page.status_code, 200, first_page.text)
        self.assertEqual(second_page.status_code, 200, second_page.text)
        self.assertEqual(first_page.json()["total"], 2)
        self.assertEqual(len(first_page.json()["items"]), 1)
        self.assertEqual(len(second_page.json()["items"]), 1)
        self.assertNotEqual(first_page.json()["items"][0]["id"], second_page.json()["items"][0]["id"])
        self.assertIsInstance(legacy.json(), list)
        self.__class__.current_staff_id = self.staff_id

    def test_project_list_rejects_page_that_would_overflow_database_offset(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        client = TestClient(app, raise_server_exceptions=False)
        try:
            response = client.get(
                "/api/v1/admin/v2/projects",
                params={"page": 92_233_720_368_547_760, "page_size": 100},
            )
            self.assertEqual(response.status_code, 422, response.text)
        finally:
            client.close()
            self.__class__.current_staff_id = self.staff_id

    def test_product_list_rejects_store_id_outside_database_integer_range(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        client = TestClient(app, raise_server_exceptions=False)
        try:
            response = client.get(
                "/api/v1/admin/v2/products",
                params={"store_id": 9_223_372_036_854_775_808},
            )
            self.assertEqual(response.status_code, 422, response.text)
        finally:
            client.close()
            self.__class__.current_staff_id = self.staff_id

    def test_legacy_staff_product_write_returns_structured_forbidden(self):
        self.__class__.current_staff_id = self.read_only_staff_id
        client = TestClient(app, raise_server_exceptions=False)
        try:
            response = client.patch(
                "/api/v1/admin/v2/products/1",
                json={"publication_status": "published"},
            )
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(response.json()["detail"]["code"], "HEADQUARTERS_ADMIN_REQUIRED")
        finally:
            client.close()
            self.__class__.current_staff_id = self.staff_id

    def test_bound_admin_cannot_manage_store_master_data(self):
        self.__class__.current_staff_id = self.staff_id
        try:
            response = self.client.get("/api/v1/admin/v2/stores")
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(response.json()["detail"]["code"], "HEADQUARTERS_ADMIN_REQUIRED")
        finally:
            self.__class__.current_staff_id = self.staff_id

    def test_store_staff_only_lists_rooms_from_own_store(self):
        response = self.client.get("/api/v1/admin/v2/rooms")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([room["code"] for room in response.json()["items"]], ["R-01"])
        self.assertEqual(response.json()["items"][0]["operational_status"], "active")

    def test_store_staff_cannot_select_another_store_in_query(self):
        response = self.client.get(
            "/api/v1/admin/v2/rooms",
            params={"store_id": self.other_store_id},
        )
        self.assertEqual(response.status_code, 403)

    def test_store_staff_only_lists_own_technicians_projects_and_products(self):
        technicians = self.client.get("/api/v1/admin/v2/technicians")
        projects = self.client.get("/api/v1/admin/v2/projects")
        products = self.client.get("/api/v1/admin/v2/products")
        self.assertEqual([item["code"] for item in technicians.json()["items"]], ["T-01"])
        self.assertEqual([item["code"] for item in projects.json()], ["P-OWN"])
        self.assertEqual([item["code"] for item in products.json()], ["G-OWN"])

    def test_project_list_uses_the_latest_price_for_each_price_type(self):
        project = SimpleNamespace(
            id=1, store_id=1, code="P-OWN", category="bath", category_mark="",
            name="本店项目", duration_min=None, summary="", image_url="", tags=[],
            detail_modules=[], diy_options=[], display_order=0, independently_visible=True, price_label="",
            publication_status="published",
        )
        latest_price = SimpleNamespace(price_type="store", amount_cents=7_900)
        stale_price = SimpleNamespace(price_type="store", amount_cents=6_900)

        class _ScalarResult:
            def __init__(self, rows):
                self.rows = rows

            def all(self):
                return self.rows

        class _Result:
            def __init__(self, rows):
                self.rows = rows

            def scalars(self):
                return _ScalarResult(self.rows)

        class _Db:
            def __init__(self):
                self.statements = []
                self.rows = iter(([project], [latest_price, stale_price]))

            def execute(self, statement):
                self.statements.append(statement)
                return _Result(next(self.rows))

        db = _Db()
        staff = SimpleNamespace(store_id=1, role="manager", technician_id=None)
        with patch.object(admin_v2, "_current_staff", return_value=staff):
            result = admin_v2.list_projects_admin(store_id=None, db=db, authorization=None)

        self.assertEqual(result[0]["prices"]["store"], 7_900)
        compiled = str(db.statements[1].compile())
        self.assertIn(
            "ORDER BY price_book.price_type, price_book.published_at DESC, price_book.id DESC",
            compiled,
        )

    def test_only_headquarters_can_change_project_standalone_visibility(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        try:
            updated = self.client.patch(
                f"/api/v1/admin/v2/projects/{self.own_project_id}",
                json={"independently_visible": False},
            )
            self.assertEqual(updated.status_code, 200, updated.text)
            listing = self.client.get("/api/v1/admin/v2/projects")
            self.assertEqual(listing.status_code, 200, listing.text)
            item = next(project for project in listing.json() if project["id"] == self.own_project_id)
            self.assertIs(item["independently_visible"], False)
            self.__class__.current_staff_id = self.staff_id
            blocked = self.client.patch(
                f"/api/v1/admin/v2/projects/{self.own_project_id}",
                json={"independently_visible": True},
            )
            self.assertEqual(blocked.status_code, 403, blocked.text)
        finally:
            self.__class__.current_staff_id = self.headquarters_admin_id
            self.client.patch(
                f"/api/v1/admin/v2/projects/{self.own_project_id}",
                json={"independently_visible": True},
            )
            self.__class__.current_staff_id = self.staff_id

    def test_store_staff_only_lists_users_with_an_own_store_order(self):
        response = self.client.get("/api/v1/admin/v2/users")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertNotIn("其他门店顾客", [item["nickname"] for item in response.json()["items"]])

    def test_read_only_staff_can_read_scrm_but_not_sensitive_management_apis(self):
        self.__class__.current_staff_id = self.read_only_staff_id
        try:
            for path in ("products", "users"):
                with self.subTest(path=path):
                    response = self.client.get(f"/api/v1/admin/v2/{path}")
                    self.assertEqual(response.status_code, 403)
            for path in ("tags", "segments", "automations"):
                with self.subTest(path=path):
                    response = self.client.get(f"/api/v1/admin/v2/{path}")
                    self.assertEqual(response.status_code, 200)
        finally:
            self.__class__.current_staff_id = self.staff_id

    def test_read_only_staff_cannot_read_legacy_management_apis(self):
        for path in ("analytics", "coupons"):
            with self.subTest(path=path):
                response = self.client.get(
                    f"/api/v1/admin/{path}",
                    headers=self.staff_auth_headers,
                )
                self.assertEqual(response.status_code, 403)

    def test_diy_cannot_read_physical_room_assignments(self):
        response = self.client.get(
            f"/api/v1/admin/v2/assignments/room/{self.other_room_id}"
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json()["detail"]["code"], "DIY_PHYSICAL_RESOURCE_FORBIDDEN")

    def test_store_admin_cannot_create_resource_for_another_store(self):
        response = self.client.post(
            "/api/v1/admin/v2/rooms",
            json={
                "store_id": self.other_store_id,
                "code": "ILLEGAL-ROOM",
                "name": "越权房间",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_pending_checkout_list_uses_pending_checkout_status(self):
        response = self.client.get("/api/v1/admin/v2/rooms/pending-checkout")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [order["order_no"] for order in response.json()],
            ["PENDING-1"],
        )

    def test_admin_order_list_only_contains_own_store_orders(self):
        response = self.client.get("/api/v1/admin/orders", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        order_numbers = [order["order_no"] for order in response.json()["items"]]
        self.assertNotIn("OTHER-PENDING", order_numbers)
        self.assertNotIn("OTHER-PAID", order_numbers)

    def test_customer_phone_reveal_is_store_scoped_and_audited(self):
        with self.SessionLocal() as db:
            staff = db.get(Staff, self.staff_id)
            user = User(openid="phone-audit-user", phone="13912345678")
            db.add(user)
            db.flush()
            db.add(Order(
                store_id=staff.store_id,
                user_id=user.id,
                order_no="PHONE-AUDIT-1",
                order_type="service",
                status="paid",
                pay_status="paid",
                pay_amount_cents=9900,
            ))
            db.commit()
            user_id = user.id

        try:
            response = self.client.get(f"/api/v1/admin/v2/users/{user_id}/phone")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["phone"], "13912345678")
            with self.SessionLocal() as db:
                audit = db.scalar(select(AuditLog).where(
                    AuditLog.action == "view_customer_phone",
                    AuditLog.entity_id == str(user_id),
                ))
                self.assertIsNotNone(audit)
                self.assertEqual(audit.store_id, staff.store_id)
        finally:
            with self.SessionLocal() as db:
                db.query(Order).filter(Order.order_no == "PHONE-AUDIT-1").delete()
                db.query(AuditLog).filter(AuditLog.action == "view_customer_phone").delete()
                db.query(User).filter(User.id == user_id).delete()
                db.commit()

    def test_store_manager_can_issue_published_coupon_to_store_customer(self):
        with self.SessionLocal() as db:
            staff = db.get(Staff, self.staff_id)
            user = User(openid="coupon-issue-user", phone="13600001234")
            db.add(user)
            db.flush()
            db.add(Order(
                store_id=staff.store_id,
                user_id=user.id,
                order_no="COUPON-ISSUE-1",
                order_type="service",
                status="paid",
                pay_status="paid",
                pay_amount_cents=9900,
            ))
            template = CouponTemplate(
                store_id=staff.store_id,
                code="coupon-issue-template",
                name="测试发券",
                amount_cents=500,
                status="published",
                claim_limit=1,
            )
            db.add(template)
            db.commit()
            user_id, template_id = user.id, template.id

        try:
            response = self.client.post(
                f"/api/v1/admin/v2/coupons/{template_id}/issue",
                json={"user_id": user_id},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["template_id"], template_id)
            with self.SessionLocal() as db:
                coupon = db.scalar(select(UserCoupon).where(
                    UserCoupon.user_id == user_id,
                    UserCoupon.template_id == template_id,
                ))
                self.assertIsNotNone(coupon)
                self.assertEqual(coupon.status, "unused")
                audit = db.scalar(select(AuditLog).where(
                    AuditLog.action == "issue_customer_coupon",
                    AuditLog.entity_id == str(coupon.id),
                ))
                self.assertIsNotNone(audit)

            listing = self.client.get("/api/v1/admin/coupons", headers=self.auth_headers)
            self.assertEqual(listing.status_code, 200, listing.text)
            listed = next(item for item in listing.json()["items"] if item["id"] == template_id)
            self.assertEqual(listed["issued_count"], 1)
            self.assertEqual(listed["unused_count"], 1)
            self.assertEqual(listed["usage_rate_percent"], 0.0)

            duplicate = self.client.post(
                f"/api/v1/admin/v2/coupons/{template_id}/issue",
                json={"user_id": user_id},
            )
            self.assertEqual(duplicate.status_code, 409, duplicate.text)
            self.assertEqual(duplicate.json()["detail"]["code"], "COUPON_CLAIM_LIMIT_REACHED")
        finally:
            with self.SessionLocal() as db:
                db.query(UserCoupon).filter(UserCoupon.template_id == template_id).delete()
                db.query(CouponTemplate).filter(CouponTemplate.id == template_id).delete()
                db.query(Order).filter(Order.order_no == "COUPON-ISSUE-1").delete()
                db.query(AuditLog).filter(AuditLog.action == "issue_customer_coupon").delete()
                db.query(User).filter(User.id == user_id).delete()
                db.commit()

    def test_customer_export_is_masked_and_audited(self):
        response = self.client.get("/api/v1/admin/v2/customers/export")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertIn("顾客ID", response.text)
        self.assertIn("手机号(脱敏)", response.text)
        with self.SessionLocal() as db:
            audit = db.scalar(select(AuditLog).where(
                AuditLog.action == "export_customer_list",
                AuditLog.entity_type == "customer_export",
            ))
            self.assertIsNotNone(audit)
            self.assertEqual(audit.detail.get("phone_mode"), "masked")
        with self.SessionLocal() as db:
            db.query(AuditLog).filter(AuditLog.action == "export_customer_list").delete()
            db.commit()

    def test_order_reconciliation_surfaces_missing_selection(self):
        response = self.client.get("/api/v1/admin/order-reconciliation?days=30", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertGreater(body["summary"]["orders_checked"], 0)
        self.assertIn("missing_selection", body["summary"]["by_type"])

    def test_reconciliation_sync_creates_and_resolves_exception_queue_items(self):
        sync = self.client.post("/api/v1/admin/order-reconciliation/sync?days=30", headers=self.auth_headers)
        self.assertEqual(sync.status_code, 200, sync.text)
        body = sync.json()
        self.assertGreater(body["anomaly_count"], 0)
        self.assertGreater(body["created"], 0)

        listing = self.client.get("/api/v1/admin/exceptions?status=open", headers=self.auth_headers)
        self.assertEqual(listing.status_code, 200, listing.text)
        items = listing.json()["items"]
        self.assertTrue(items)
        exception_id = items[0]["id"]

        resolved = self.client.post(
            f"/api/v1/admin/exceptions/{exception_id}/resolve",
            headers=self.auth_headers,
            json={"resolution_note": "已人工核对并修正关联"},
        )
        self.assertEqual(resolved.status_code, 200, resolved.text)
        self.assertEqual(resolved.json()["status"], "resolved")
        with self.SessionLocal() as db:
            row = db.get(OperationalException, exception_id)
            self.assertEqual(row.status, "resolved")
            self.assertEqual(row.resolution_note, "已人工核对并修正关联")
            db.query(OperationalException).filter(OperationalException.store_id == row.store_id).delete()
            db.query(AuditLog).filter(AuditLog.action.in_(["sync_order_reconciliation", "resolve_operational_exception"])).delete()
            db.commit()

    def test_store_staff_cannot_check_in_another_store_order(self):
        with self.SessionLocal() as db:
            other_order = db.scalar(select(Order).where(Order.order_no == "OTHER-PAID"))
            other_order_id = other_order.id
        response = self.client.post(
            f"/api/v1/admin/orders/{other_order_id}/check-in",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_diy_cannot_list_physical_room_assignments(self):
        response = self.client.get(
            "/api/v1/admin/v2/assignments",
            params={"room_id": self.room_id},
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json()["detail"]["code"], "DIY_PHYSICAL_RESOURCE_FORBIDDEN")

    def test_coupon_status_can_be_updated_without_resending_full_coupon(self):
        response = self.client.post(
            f"/api/v1/admin/coupons/{self.coupon_id}",
            json={"status": "published"},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "published")

    def _cleanup_metric_fixtures(self):
        with self.SessionLocal() as db:
            db.query(EventLog).filter(EventLog.data["anonymous_id"].as_string().like("browser-metric-%")).delete(synchronize_session=False)
            db.query(EventLog).filter(EventLog.data["anonymous_id"].as_string() == "other-store-browser").delete(synchronize_session=False)
            db.query(Order).filter(Order.order_no.like("METRIC-%")).delete(synchronize_session=False)
            metric_users = list(db.scalars(select(User).where(User.openid.in_(("metric-new-user", "metric-repeat-user", "anon_metric-user")))))
            for user in metric_users:
                db.delete(user)
            db.commit()

    def test_operations_summary_deduplicates_funnel_and_scopes_store_and_date(self):
        self.addCleanup(self._cleanup_metric_fixtures)
        period_start = datetime(2026, 8, 20, tzinfo=timezone.utc)
        period_end = period_start + timedelta(days=1)
        with self.SessionLocal() as db:
            new_user = User(
                openid="metric-new-user",
                is_member=True,
                member_type="annual",
                created_at=period_start + timedelta(hours=1),
            )
            repeat_user = User(
                openid="metric-repeat-user",
                created_at=period_start - timedelta(days=30),
            )
            anonymous_user = User(
                openid="anon_metric-user",
                created_at=period_start + timedelta(hours=1),
            )
            db.add_all([new_user, repeat_user, anonymous_user])
            db.flush()
            db.add_all([
                Order(
                    order_no="METRIC-HISTORY",
                    order_type="service",
                    user_id=repeat_user.id,
                    store_id=1,
                    items=[{"project_id": self.own_project_id, "name": "销量项目", "quantity": 2}],
                    total_amount_cents=1000,
                    pay_amount_cents=1000,
                    status="completed",
                    pay_status="paid",
                    created_at=period_start - timedelta(days=2),
                ),
                Order(
                    order_no="METRIC-NEW",
                    order_type="service",
                    user_id=new_user.id,
                    store_id=1,
                    items=[{"project_id": self.own_project_id, "name": "销量项目", "quantity": 2}],
                    total_amount_cents=10000,
                    discount_cents=1000,
                    member_discount_cents=500,
                    pay_amount_cents=9000,
                    status="completed",
                    pay_status="paid",
                    created_at=period_start + timedelta(hours=2),
                ),
                Order(
                    order_no="METRIC-REPEAT",
                    order_type="service",
                    user_id=repeat_user.id,
                    store_id=1,
                    items=[{"project_id": self.own_project_id, "name": "销量项目", "quantity": 1}],
                    total_amount_cents=20000,
                    discount_cents=2000,
                    pay_amount_cents=18000,
                    status="completed",
                    pay_status="paid",
                    created_at=period_start + timedelta(hours=3),
                ),
                Order(
                    order_no="METRIC-OTHER-STORE",
                    order_type="service",
                    user_id=new_user.id,
                    store_id=self.other_store_id,
                    items=[{"project_id": self.other_project_id, "name": "其他门店项目", "quantity": 9}],
                    total_amount_cents=50000,
                    pay_amount_cents=50000,
                    status="completed",
                    pay_status="paid",
                    created_at=period_start + timedelta(hours=4),
                ),
            ])
            for event in (
                "diy_entry_view",
                "project_view",
                "project_config_save",
                "selection_submit_success",
                "feedback_submit_success",
            ):
                db.add(EventLog(
                    user_id=new_user.id,
                    store_id=1,
                    event=event,
                    data={"store_id": 1, "anonymous_id": "browser-metric-1"},
                    created_at=period_start + timedelta(hours=5),
                ))
            db.add(EventLog(
                user_id=new_user.id,
                store_id=1,
                event="diy_entry_view",
                data={"store_id": 1, "anonymous_id": "browser-metric-1"},
                created_at=period_start + timedelta(hours=6),
            ))
            db.add(EventLog(
                store_id=1,
                event="project_view",
                data={"store_id": 1, "anonymous_id": "browser-metric-2"},
                created_at=period_start + timedelta(hours=6),
            ))
            db.add(EventLog(
                event="anonymous_to_logged_in",
                user_id=new_user.id,
                store_id=1,
                data={"store_id": 1, "anonymous_id": "browser-metric-1"},
                created_at=period_start + timedelta(hours=7),
            ))
            db.add(EventLog(
                store_id=self.other_store_id,
                event="diy_entry_view",
                data={"store_id": self.other_store_id, "anonymous_id": "other-store-browser"},
                created_at=period_start + timedelta(hours=7),
            ))
            db.commit()

        response = self.client.get(
            "/api/v1/admin/operations-summary",
            params={"start_date": "2026-08-20", "end_date": "2026-08-20"},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["transactions"]["orders_count"], 2)
        self.assertEqual(body["transactions"]["gross_amount_cents"], 30000)
        self.assertEqual(body["transactions"]["paid_amount_cents"], 27000)
        self.assertEqual(body["transactions"]["average_order_value_cents"], 13500)
        self.assertIn("data_quality", body)
        self.assertIn("warnings", body["data_quality"])
        self.assertIn("definitions", body)
        self.assertEqual(body["transactions"]["discount_cents"], 3000)
        self.assertEqual(body["customers"]["new_count"], 1)
        self.assertEqual(body["customers"]["repeat_count"], 1)
        self.assertEqual(body["customers"]["member_count"], 1)
        self.assertEqual(body["customers"]["anonymous_to_logged_in_count"], 1)
        self.assertEqual(body["funnel"]["diy_entry_view"], 1)
        self.assertEqual(body["funnel"]["project_view"], 2)
        self.assertEqual(body["funnel"]["feedback_submit_success"], 1)
        self.assertEqual(body["project_sales"], [{
            "project_id": self.own_project_id,
            "name": "销量项目",
            "quantity": 3,
            "order_count": 2,
        }])
        self.assertGreaterEqual(body["service_positions"]["total_count"], 1)

    def test_operations_summary_requires_admin_role(self):
        response = self.client.get(
            "/api/v1/admin/operations-summary",
            headers=self.staff_auth_headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_operations_summary_reports_duration_turnover_exceptions_and_funnel_rates(self):
        self.addCleanup(self._cleanup_operations_duration_fixtures)
        period_start = datetime(2026, 8, 20, tzinfo=timezone.utc)
        with self.SessionLocal() as db:
            sessions = [
                SelectionSession(
                    id="metric-duration-session-1",
                    access_token_hash="duration-token-1",
                    store_id=1,
                    status="confirmed",
                    items=[],
                    created_at=period_start,
                ),
                SelectionSession(
                    id="metric-duration-session-2",
                    access_token_hash="duration-token-2",
                    store_id=1,
                    status="confirmed",
                    items=[],
                    created_at=period_start + timedelta(hours=2),
                ),
            ]
            db.add_all(sessions)
            db.flush()
            db.add_all([
                PositionOccupancy(
                    store_id=1,
                    room_id=self.room_id,
                    selection_session_id=sessions[0].id,
                    status="released",
                    actual_start_at=period_start + timedelta(hours=1),
                    actual_service_end_at=period_start + timedelta(hours=2),
                    departed_at=period_start + timedelta(hours=2, minutes=15),
                    released_at=period_start + timedelta(hours=2, minutes=30),
                    created_at=period_start + timedelta(hours=1),
                ),
                PositionOccupancy(
                    store_id=1,
                    room_id=self.room_id + 1,
                    selection_session_id=sessions[1].id,
                    status="released",
                    actual_start_at=period_start + timedelta(hours=3),
                    actual_service_end_at=period_start + timedelta(hours=3, minutes=30),
                    departed_at=period_start + timedelta(hours=3, minutes=40),
                    released_at=period_start + timedelta(hours=4),
                    release_reason="顾客身体不适，异常结束",
                    created_at=period_start + timedelta(hours=3),
                ),
            ])
            db.add(AuditLog(
                actor_type="staff",
                actor_id=str(self.staff_id),
                action="force_release",
                entity_type="position_occupancy",
                entity_id="2",
                detail={"reason": "顾客身体不适，异常结束"},
                created_at=period_start + timedelta(hours=4),
            ))
            db.add_all([
                EventLog(store_id=1, event="diy_entry_view", data={"store_id": 1, "anonymous_id": "duration-1"}, created_at=period_start),
                EventLog(store_id=1, event="project_view", data={"store_id": 1, "anonymous_id": "duration-1"}, created_at=period_start),
                EventLog(store_id=1, event="project_view", data={"store_id": 1, "anonymous_id": "duration-2"}, created_at=period_start),
                EventLog(store_id=1, event="selection_submit_success", data={"store_id": 1, "anonymous_id": "duration-1"}, created_at=period_start),
                EventLog(store_id=1, event="feedback_submit_success", data={"store_id": 1, "anonymous_id": "duration-1"}, created_at=period_start),
            ])
            db.commit()

        response = self.client.get(
            "/api/v1/admin/operations-summary",
            params={"start_date": "2026-08-20", "end_date": "2026-08-20"},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        operations = body["service_positions"]["operations"]
        self.assertEqual(operations["completed_services_count"], 2)
        self.assertEqual(operations["average_service_minutes"], 45)
        self.assertEqual(operations["average_departure_to_release_minutes"], 17.5)
        self.assertEqual(operations["turnover_count"], 2)
        self.assertEqual(operations["exception_release_count"], 1)
        self.assertEqual(body["funnel_rates"]["project_view_to_selection_submit_success_percent"], 50)
        self.assertEqual(body["funnel_rates"]["selection_submit_success_to_feedback_submit_success_percent"], 100)

    def _cleanup_operations_duration_fixtures(self):
        with self.SessionLocal() as db:
            db.query(EventLog).filter(EventLog.data["anonymous_id"].as_string().like("duration-%")).delete(synchronize_session=False)
            db.query(AuditLog).filter(AuditLog.entity_id == "2", AuditLog.action == "force_release").delete(synchronize_session=False)
            db.query(PositionOccupancy).filter(PositionOccupancy.selection_session_id.like("metric-duration-%")).delete(synchronize_session=False)
            db.query(SelectionSession).filter(SelectionSession.id.like("metric-duration-%")).delete(synchronize_session=False)
            db.commit()

    def test_audit_logs_are_paginated_scoped_and_redacted(self):
        with self.SessionLocal() as db:
            db.add_all([
                AuditLog(
                    actor_type="staff",
                    actor_id=str(self.staff_id),
                    action="position_qr_disabled",
                    entity_type="service_position_qr",
                    entity_id="1",
                    detail={"store_id": 1, "phone": "13800138000", "openid": "openid-secret", "token": "raw-token", "reason": "测试"},
                    created_at=datetime(2026, 8, 20, 10, tzinfo=timezone.utc),
                ),
                AuditLog(
                    actor_type="staff",
                    actor_id="999",
                    action="other_store_action",
                    entity_type="room",
                    entity_id="2",
                    detail={"store_id": self.other_store_id, "phone": "13900139000"},
                    created_at=datetime(2026, 8, 20, 11, tzinfo=timezone.utc),
                ),
            ])
            db.commit()
        response = self.client.get(
            "/api/v1/admin/audit-logs",
            params={"action": "position_qr_disabled", "start_date": "2026-08-20", "end_date": "2026-08-20", "page": 1, "page_size": 1},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["page_size"], 1)
        detail = body["items"][0]["detail"]
        self.assertEqual(detail["phone"], "138****8000")
        self.assertEqual(detail["openid"], "open****cret")
        self.assertEqual(detail["token"], "[REDACTED]")
        self.assertNotIn("raw-token", response.text)

        exported = self.client.get(
            "/api/v1/admin/audit-logs",
            params={"action": "position_qr_disabled", "start_date": "2026-08-20", "end_date": "2026-08-20", "export": "true"},
            headers=self.auth_headers,
        )
        self.assertEqual(exported.status_code, 200, exported.text)
        self.assertIn("text/csv", exported.headers["content-type"])
        self.assertIn("[REDACTED]", exported.text)
        self.assertNotIn("13800138000", exported.text)

    def test_store_staff_cannot_query_audit_logs(self):
        response = self.client.get(
            "/api/v1/admin/audit-logs",
            headers=self.staff_auth_headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_headquarters_admin_can_filter_audit_logs_by_store(self):
        self.__class__.current_staff_id = self.headquarters_admin_id
        try:
            response = self.client.get(
                "/api/v1/admin/audit-logs",
                params={"store_id": self.other_store_id},
                headers={
                    "Authorization": f"Bearer {create_staff_token(self.headquarters_admin_id, 'admin')}"
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
        finally:
            self.__class__.current_staff_id = self.staff_id

    def test_low_rating_feedback_can_be_assigned_and_resolved(self):
        with self.SessionLocal() as db:
            session = SelectionSession(
                id="metric-feedback-session",
                access_token_hash="feedback-token",
                store_id=1,
                customer_id=1,
                status="confirmed",
                items=[],
                diy_preferences={},
            )
            db.add(session)
            db.flush()
            feedback = ServiceFeedback(
                store_id=1,
                selection_session_id=session.id,
                customer_id=1,
                rating=2,
                tags=["服务态度"],
                note="需要跟进",
                created_at=datetime.now(timezone.utc),
            )
            db.add(feedback)
            db.commit()
            feedback_id = feedback.id
        try:
            listing = self.client.get(
                "/api/v1/admin/v2/feedback",
                params={"low_rating_only": "true"},
                headers=self.auth_headers,
            )
            self.assertEqual(listing.status_code, 200, listing.text)
            self.assertEqual(listing.json()["items"][0]["follow_up_status"], "open")
            updated = self.client.patch(
                f"/api/v1/admin/v2/feedback/{feedback_id}",
                json={"follow_up_status": "resolved", "follow_up_note": "已电话回访"},
                headers=self.auth_headers,
            )
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertEqual(updated.json()["follow_up_status"], "resolved")
            self.assertEqual(updated.json()["follow_up_staff_id"], self.staff_id)
        finally:
            with self.SessionLocal() as db:
                db.query(ServiceFeedback).filter(ServiceFeedback.id == feedback_id).delete()
                db.query(SelectionSession).filter(SelectionSession.id == "metric-feedback-session").delete()
                db.commit()

    def test_analytics_works_on_sqlite_preview_database(self):
        response = self.client.get(
            "/api/v1/admin/analytics",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("daily_views", response.json())
        self.assertEqual(
            set(response.json()["funnel"]),
            {"diy_entry_view", "project_view", "project_config_save", "selection_submit_success", "feedback_submit_success"},
        )


if __name__ == "__main__":
    unittest.main()
