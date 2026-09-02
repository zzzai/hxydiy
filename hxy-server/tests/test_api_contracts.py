import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import admin_v2
from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    CouponTemplate,
    AuditLog,
    EventLog,
    Order,
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
from app.models.room_assign import RoomAssignment
from app.models.orders import ORDER_STATUSES


class AdminV2ContractTests(unittest.TestCase):
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
                status="preparing",
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
        self.assertEqual(response.json()[0]["status"], "preparing")

    def test_room_list_exposes_dashboard_fields(self):
        response = self.client.get("/api/v1/admin/v2/rooms")
        self.assertEqual(response.status_code, 200)
        room = response.json()["items"][0]
        self.assertEqual(room["room_group"], "sofa")
        self.assertEqual(room["used_count"], 1)
        self.assertEqual(room["current_tech"], "王师傅")

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
                    db.query(Store).filter(Store.id == created_id).delete()
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
            json={"publication_status": "candidate"},
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
            detail_modules=[], diy_options=[], display_order=0, price_label="",
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
                    items=[],
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
                    items=[],
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
                    items=[],
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
                    items=[],
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
        self.assertEqual(body["transactions"]["discount_cents"], 3000)
        self.assertEqual(body["customers"]["new_count"], 1)
        self.assertEqual(body["customers"]["repeat_count"], 1)
        self.assertEqual(body["customers"]["member_count"], 1)
        self.assertEqual(body["customers"]["anonymous_to_logged_in_count"], 1)
        self.assertEqual(body["funnel"]["diy_entry_view"], 1)
        self.assertEqual(body["funnel"]["project_view"], 2)
        self.assertEqual(body["funnel"]["feedback_submit_success"], 1)
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
