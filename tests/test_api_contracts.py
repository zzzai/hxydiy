import unittest
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
from app.models import CouponTemplate, Order, PriceBook, Product, Project, Staff, Store, User
from app.models.operations import Room, Technician
from app.models.room_assign import RoomAssignment
from app.models.orders import ORDER_STATUSES


class AdminV2ContractTests(unittest.TestCase):
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
                staff, read_only_staff, user, other_user, room, tech, other_room, other_tech,
                own_project, other_project, own_product, other_product,
            ])
            db.flush()
            coupon = CouponTemplate(
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
        staff = SimpleNamespace(store_id=1)
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

    def test_read_only_staff_cannot_read_management_configuration_apis(self):
        self.__class__.current_staff_id = self.read_only_staff_id
        try:
            for path in ("products", "users", "tags", "segments", "automations"):
                with self.subTest(path=path):
                    response = self.client.get(f"/api/v1/admin/v2/{path}")
                    self.assertEqual(response.status_code, 403)
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

    def test_store_staff_cannot_read_another_store_room_detail(self):
        response = self.client.get(
            f"/api/v1/admin/v2/assignments/room/{self.other_room_id}"
        )
        self.assertEqual(response.status_code, 404)

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

    def test_assignments_endpoint_resolves_room_assignment_model(self):
        response = self.client.get(
            "/api/v1/admin/v2/assignments",
            params={"room_id": self.room_id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_coupon_status_can_be_updated_without_resending_full_coupon(self):
        response = self.client.post(
            f"/api/v1/admin/coupons/{self.coupon_id}",
            json={"status": "published"},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "published")

    def test_analytics_works_on_sqlite_preview_database(self):
        response = self.client.get(
            "/api/v1/admin/analytics",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("daily_views", response.json())


if __name__ == "__main__":
    unittest.main()
