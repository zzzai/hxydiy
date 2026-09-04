import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import admin_v2
from app.api.admin import hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import Addon, Project, Store, Staff


class AdminAddonContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        cls.SessionLocal = sessionmaker(bind=cls.engine, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            store = Store(store_code="addon-contract", name="加项测试店", address="测试")
            other = Store(store_code="addon-other", name="另一门店", address="测试")
            db.add_all([store, other])
            db.flush()
            admin = Staff(username="addon-admin", password_hash=hash_password("pass"), name="总部", role="admin", store_id=None, status="active")
            manager = Staff(username="addon-manager", password_hash=hash_password("pass"), name="店长", role="manager", store_id=store.id, status="active")
            employee = Staff(username="addon-employee", password_hash=hash_password("pass"), name="员工", role="staff", store_id=store.id, status="active")
            other_project = Project(store_id=other.id, code="P-OTHER-ADDON", category="bath", name="另一店项目")
            db.add_all([admin, manager, employee, other_project])
            db.flush()
            own_addon = Addon(store_id=store.id, code="A-1", name="店内加项", duration_min=15, summary="原简介", image_url="media/original", price_cents=1000, store_price_cents=1000, member_price_cents=800, member_price_enabled=True, publication_status="published")
            other_addon = Addon(store_id=other.id, code="A-2", name="另一店加项", parent_project_id=other_project.id, price_cents=1200, store_price_cents=1200, member_price_cents=900, member_price_enabled=True, publication_status="published")
            db.add_all([own_addon, other_addon])
            db.commit()
            cls.store_id, cls.other_store_id = store.id, other.id
            cls.admin_id, cls.manager_id, cls.employee_id = admin.id, manager.id, employee.id
            cls.own_addon_id, cls.other_addon_id = own_addon.id, other_addon.id

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.current_staff_id = cls.admin_id
        cls.auth_patch = patch.object(
            admin_v2,
            "_current_staff",
            side_effect=lambda _authorization, db: db.get(Staff, cls.current_staff_id),
        )
        cls.auth_patch.start()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.auth_patch.stop()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def setUp(self):
        self.__class__.current_staff_id = self.admin_id
        with self.SessionLocal() as db:
            own = db.get(Addon, self.own_addon_id)
            own.name, own.summary, own.image_url = "店内加项", "原简介", "media/original"
            own.price_cents, own.store_price_cents = 1000, 1000
            own.member_price_cents, own.member_price_enabled = 800, True
            own.parent_project_id, own.duration_min, own.publication_status = None, 15, "published"
            other = db.get(Addon, self.other_addon_id)
            other.name, other.member_price_cents = "另一店加项", 900
            other.member_price_enabled, other.publication_status = True, "published"
            db.commit()

    def patch_addon(self, addon_id, payload):
        return self.client.patch(f"/api/v1/admin/v2/addons/{addon_id}", json=payload)

    def test_headquarters_can_patch_across_stores_and_clear_nullable_fields(self):
        response = self.patch_addon(self.other_addon_id, {
            "name": "总部跨店修改",
            "parent_project_id": None,
            "member_price_cents": None,
            "member_price_enabled": False,
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "总部跨店修改")
        self.assertIsNone(response.json()["member_price_cents"])
        listing = self.client.get(f"/api/v1/admin/v2/addons?store_id={self.other_store_id}")
        self.assertIsNone(listing.json()[0]["member_price_cents"])
        with self.SessionLocal() as db:
            addon = db.get(Addon, self.other_addon_id)
            self.assertIsNone(addon.parent_project_id)
            self.assertIsNone(addon.member_price_cents)

    def test_manager_cross_store_patch_is_hidden(self):
        self.__class__.current_staff_id = self.manager_id
        response = self.patch_addon(self.other_addon_id, {"publication_status": "inactive"})
        self.assertEqual(response.status_code, 404, response.text)

    def test_manager_cannot_edit_master_fields_via_patch_or_legacy_post(self):
        self.__class__.current_staff_id = self.manager_id
        for payload in ({"name": "越权名称"}, {"store_price_cents": 1}, {"image_url": "media/forbidden"}, {"parent_project_id": None}):
            response = self.patch_addon(self.own_addon_id, payload)
            self.assertEqual(response.status_code, 403, (payload, response.text))
            self.assertEqual(response.json()["detail"]["code"], "HEADQUARTERS_ADMIN_REQUIRED")
        legacy = self.client.post(f"/api/v1/admin/v2/addons/{self.own_addon_id}", json={"name": "兼容接口也不能越权"})
        self.assertEqual(legacy.status_code, 403, legacy.text)
        self.assertEqual(legacy.json()["detail"]["code"], "HEADQUARTERS_ADMIN_REQUIRED")

    def test_manager_can_toggle_both_directions_but_cannot_restore_archived(self):
        self.__class__.current_staff_id = self.manager_id
        inactive = self.patch_addon(self.own_addon_id, {"publication_status": "inactive"})
        self.assertEqual(inactive.status_code, 200, inactive.text)
        published = self.client.post(f"/api/v1/admin/v2/addons/{self.own_addon_id}", json={"publication_status": "published"})
        self.assertEqual(published.status_code, 200, published.text)
        self.__class__.current_staff_id = self.admin_id
        archived = self.patch_addon(self.own_addon_id, {"publication_status": "archived"})
        self.assertEqual(archived.status_code, 200, archived.text)
        self.__class__.current_staff_id = self.manager_id
        restored = self.patch_addon(self.own_addon_id, {"publication_status": "published"})
        self.assertEqual(restored.status_code, 403, restored.text)

    def test_non_nullable_patch_fields_reject_explicit_null(self):
        for field in ("summary", "image_url", "store_price_cents", "publication_status"):
            response = self.patch_addon(self.own_addon_id, {field: None})
            self.assertEqual(response.status_code, 422, (field, response.text))

    def test_employee_cannot_list_or_patch_catalog(self):
        self.__class__.current_staff_id = self.employee_id
        listing = self.client.get("/api/v1/admin/v2/addons")
        self.assertEqual(listing.status_code, 403, listing.text)
        update = self.patch_addon(self.own_addon_id, {"publication_status": "inactive"})
        self.assertEqual(update.status_code, 403, update.text)

    def test_store_listing_is_isolated_and_headquarters_can_select_store(self):
        self.__class__.current_staff_id = self.manager_id
        own = self.client.get("/api/v1/admin/v2/addons")
        self.assertEqual(own.status_code, 200, own.text)
        self.assertEqual({item["store_id"] for item in own.json()}, {self.store_id})
        cross = self.client.get(f"/api/v1/admin/v2/addons?store_id={self.other_store_id}")
        self.assertEqual(cross.status_code, 403, cross.text)
        self.__class__.current_staff_id = self.admin_id
        headquarters = self.client.get(f"/api/v1/admin/v2/addons?store_id={self.other_store_id}")
        self.assertEqual(headquarters.status_code, 200, headquarters.text)
        self.assertEqual({item["store_id"] for item in headquarters.json()}, {self.other_store_id})

    def test_addon_listing_supports_server_pagination(self):
        response = self.client.get("/api/v1/admin/v2/addons?page=1&page_size=1")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 2)
        self.assertEqual(len(response.json()["items"]), 1)

    def test_member_price_cannot_exceed_store_price_on_create_patch_or_post(self):
        created = self.client.post("/api/v1/admin/v2/addons", json={
            "store_id": self.store_id,
            "code": "A-PRICE-LIMIT",
            "name": "非法价格加项",
            "store_price_cents": 1000,
            "member_price_cents": 1200,
            "member_price_enabled": True,
        })
        self.assertEqual(created.status_code, 400, created.text)
        for method in (self.client.patch, self.client.post):
            response = method(
                f"/api/v1/admin/v2/addons/{self.own_addon_id}",
                json={"store_price_cents": 1000, "member_price_cents": 1200, "member_price_enabled": True},
            )
            self.assertEqual(response.status_code, 400, response.text)


if __name__ == "__main__":
    unittest.main()
