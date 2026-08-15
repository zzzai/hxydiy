import unittest
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    AuditLog,
    OptionChoicePrice,
    PriceBook,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    Staff,
    Store,
)


class AdminCatalogOptionsApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            self.store = Store(store_code="admin-catalog-store", name="目录门店", address="测试地址")
            self.other_store = Store(store_code="other-catalog-store", name="其他门店", address="测试地址")
            db.add_all([self.store, self.other_store])
            db.flush()
            self.admin = Staff(username="catalog-admin", name="目录管理员", role="admin", status="active", password_hash=hash_password("pass"), store_id=self.store.id)
            self.staff = Staff(username="catalog-staff", name="目录员工", role="staff", status="active", password_hash=hash_password("pass"), store_id=self.store.id)
            self.other_admin = Staff(username="other-catalog-admin", name="其他管理员", role="admin", status="active", password_hash=hash_password("pass"), store_id=self.other_store.id)
            db.add_all([self.admin, self.staff, self.other_admin])
            db.flush()
            self.main = self._add_project(db, self.store, "MAIN", name="主项目")
            self.linked = self._add_project(db, self.store, "LINKED", name="引用项目")
            self.archived = self._add_project(db, self.store, "ARCHIVED", name="归档项目", publication_status="archived")
            self.other_project = self._add_project(db, self.other_store, "OTHER", name="其他项目")
            for project, store_price, member_price in (
                (self.main, 10000, 8000),
                (self.linked, 3000, 2500),
                (self.other_project, 9000, 7000),
            ):
                db.add(PriceBook(project_id=project.id, price_type="store", amount_cents=store_price))
                db.add(PriceBook(project_id=project.id, price_type="member", amount_cents=member_price))
            linked_version = ProjectCatalogVersion(project_id=self.linked.id, version=1, status="published")
            db.add(linked_version)
            db.flush()
            self.linked.current_published_version_id = linked_version.id
            db.commit()
            self.store_id = self.store.id
            self.main_id = self.main.id
            self.linked_id = self.linked.id
            self.archived_id = self.archived.id
            self.other_project_id = self.other_project.id
            self.admin_id = self.admin.id
            self.staff_id = self.staff.id
            self.other_admin_id = self.other_admin.id

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.admin_headers = {"Authorization": f"Bearer {create_staff_token(self.admin_id, 'admin')}"}
        self.staff_headers = {"Authorization": f"Bearer {create_staff_token(self.staff_id, 'staff')}"}
        self.other_headers = {"Authorization": f"Bearer {create_staff_token(self.other_admin_id, 'admin')}"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    @staticmethod
    def _add_project(db, store, code, *, name=None, publication_status="published"):
        project = Project(
            store_id=store.id,
            code=code,
            category="catalog-test",
            name=name or code,
            publication_status=publication_status,
            diy_options=[{"label": "旧选项", "price_cents": 100}],
        )
        db.add(project)
        db.flush()
        return project

    def _create_valid_draft(self):
        group_response = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups",
            headers=self.admin_headers,
            json={"code": "touch", "name": "手法", "selection_mode": "multiple", "required": True, "min_select": 1, "max_select": 3, "display_order": 1},
        )
        self.assertEqual(group_response.status_code, 200, group_response.text)
        group_id = group_response.json()["id"]
        free_response = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{group_id}/choices",
            headers=self.admin_headers,
            json={"code": "soft", "name": "轻柔", "choice_type": "preference", "charge_mode": "free", "display_order": 1},
        )
        self.assertEqual(free_response.status_code, 200, free_response.text)
        linked_response = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{group_id}/choices",
            headers=self.admin_headers,
            json={"code": "neck", "name": "加做肩颈", "choice_type": "linked_project", "charge_mode": "inherit_linked_price", "linked_project_id": self.linked_id, "coupon_eligible": True, "display_order": 2},
        )
        self.assertEqual(linked_response.status_code, 200, linked_response.text)
        custom_response = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{group_id}/choices",
            headers=self.admin_headers,
            json={
                "code": "hot-pack",
                "name": "热敷包",
                "choice_type": "dedicated_charge",
                "charge_mode": "custom_price",
                "annual_gift_eligible": True,
                "qualifies_for_foot_bath_bundle": True,
                "display_order": 3,
                "prices": [
                    {"price_type": "store", "amount_cents": 2000, "effective_from": "2026-08-01T00:00:00+00:00"},
                    {"price_type": "member", "amount_cents": 1500, "effective_from": "2026-08-01T00:00:00+00:00"},
                ],
            },
        )
        self.assertEqual(custom_response.status_code, 200, custom_response.text)
        return {"group_id": group_id, "free_choice_id": free_response.json()["id"], "linked_choice_id": linked_response.json()["id"], "custom_choice_id": custom_response.json()["id"]}

    def test_admin_can_publish_project_with_free_linked_and_custom_options(self):
        ids = self._create_valid_draft()

        response = self.client.post(f"/api/v1/admin/v2/projects/{self.main_id}/publish", headers=self.admin_headers)

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "published")
        self.assertEqual(len(body["snapshot_hash"]), 64)
        with self.SessionLocal() as db:
            project = db.get(Project, self.main_id)
            self.assertEqual(project.publication_status, "published")
            published = db.get(ProjectCatalogVersion, project.current_published_version_id)
            self.assertEqual(published.status, "published")
            self.assertEqual(published.published_by, self.admin_id)
            actions = [row.action for row in db.scalars(select(AuditLog)).all()]
            self.assertIn("publish_catalog_version", actions)
            self.assertEqual(db.get(ProjectOptionChoice, ids["custom_choice_id"]).status, "active")

    def test_permissions_and_store_scope_are_enforced(self):
        unauthenticated = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups",
            json={"code": "x", "name": "X"},
        )
        self.assertEqual(unauthenticated.status_code, 401)
        staff_write = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups",
            headers=self.staff_headers,
            json={"code": "x", "name": "X"},
        )
        self.assertEqual(staff_write.status_code, 403)
        staff_read = self.client.get(f"/api/v1/admin/v2/projects/{self.main_id}/option-groups", headers=self.staff_headers)
        self.assertEqual(staff_read.status_code, 200)
        cross_store = self.client.get(f"/api/v1/admin/v2/projects/{self.main_id}/option-groups", headers=self.other_headers)
        self.assertEqual(cross_store.status_code, 404)

    def test_linked_project_create_patch_and_preview_reject_cross_store_without_leaking_source(self):
        ids = self._create_valid_draft()
        cross_store_create = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}/choices",
            headers=self.admin_headers,
            json={
                "code": "cross-store",
                "name": "跨店项目",
                "choice_type": "linked_project",
                "charge_mode": "inherit_linked_price",
                "linked_project_id": self.other_project_id,
            },
        )
        self.assertEqual(cross_store_create.status_code, 404)
        self.assertNotIn("OTHER", cross_store_create.text)

        cross_store_patch = self.client.patch(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}/choices/{ids['linked_choice_id']}",
            headers=self.admin_headers,
            json={"linked_project_id": self.other_project_id},
        )
        self.assertEqual(cross_store_patch.status_code, 404)
        self.assertNotIn("OTHER", cross_store_patch.text)

        with self.SessionLocal() as db:
            dirty = db.get(ProjectOptionChoice, ids["linked_choice_id"])
            dirty.linked_project_id = self.other_project_id
            db.commit()
        preview = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/price-preview",
            headers=self.staff_headers,
            json={
                "choice_ids": [ids["linked_choice_id"]],
                "is_member": False,
                "confirmed_at": "2026-08-04T10:00:00+08:00",
                "store_timezone": "Asia/Shanghai",
            },
        )
        self.assertEqual(preview.status_code, 404)
        self.assertNotIn("OTHER", preview.text)
        self.assertNotIn("source_ref", preview.text)

    def test_price_preview_rejects_duplicate_and_invalid_group_selection_counts(self):
        ids = self._create_valid_draft()
        duplicate = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/price-preview",
            headers=self.staff_headers,
            json={
                "choice_ids": [ids["custom_choice_id"], ids["custom_choice_id"]],
                "is_member": False,
                "confirmed_at": "2026-08-04T10:00:00+08:00",
                "store_timezone": "Asia/Shanghai",
            },
        )
        self.assertEqual(duplicate.status_code, 422)

        required_missing = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/price-preview",
            headers=self.staff_headers,
            json={
                "choice_ids": [],
                "is_member": False,
                "confirmed_at": "2026-08-04T10:00:00+08:00",
                "store_timezone": "Asia/Shanghai",
            },
        )
        self.assertEqual(required_missing.status_code, 422)
        self.assertIn("groups.touch", required_missing.text)

        single_group = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups",
            headers=self.admin_headers,
            json={"code": "single-room", "name": "单选房间", "selection_mode": "single", "max_select": 1},
        )
        self.assertEqual(single_group.status_code, 200, single_group.text)
        first = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{single_group.json()['id']}/choices",
            headers=self.admin_headers,
            json={"code": "a", "name": "A", "choice_type": "preference", "charge_mode": "free"},
        )
        second = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{single_group.json()['id']}/choices",
            headers=self.admin_headers,
            json={"code": "b", "name": "B", "choice_type": "preference", "charge_mode": "free"},
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        too_many = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/price-preview",
            headers=self.staff_headers,
            json={
                "choice_ids": [ids["free_choice_id"], first.json()["id"], second.json()["id"]],
                "is_member": False,
                "confirmed_at": "2026-08-04T10:00:00+08:00",
                "store_timezone": "Asia/Shanghai",
            },
        )
        self.assertEqual(too_many.status_code, 422)
        self.assertIn("groups.single-room", too_many.text)

    def test_strict_input_returns_422_before_database_errors(self):
        invalid_group_payloads = [
            {"code": "x", "name": "X", "requierd": True},
            {"code": "x", "name": "X", "required": "false"},
            {"code": None, "name": "X"},
            {"code": "x", "name": None},
        ]
        for payload in invalid_group_payloads:
            response = self.client.post(
                f"/api/v1/admin/v2/projects/{self.main_id}/option-groups",
                headers=self.admin_headers,
                json=payload,
            )
            self.assertEqual(response.status_code, 422, response.text)

        ids = self._create_valid_draft()
        invalid_choice_payloads = [
            {"code": "bad", "name": "Bad", "choice_type": "preference", "charge_mode": "free", "coupon_eligible": "false"},
            {
                "code": "bad-price",
                "name": "Bad Price",
                "choice_type": "dedicated_charge",
                "charge_mode": "custom_price",
                "prices": [{"price_type": "store", "amount_cents": "100", "effective_from": "2026-08-01T00:00:00+00:00"}],
            },
            {
                "code": "naive-time",
                "name": "Naive Time",
                "choice_type": "dedicated_charge",
                "charge_mode": "custom_price",
                "prices": [{"price_type": "store", "amount_cents": 100, "effective_from": "2026-08-01T00:00:00"}],
            },
            {
                "code": "reverse-time",
                "name": "Reverse Time",
                "choice_type": "dedicated_charge",
                "charge_mode": "custom_price",
                "prices": [{
                    "price_type": "store",
                    "amount_cents": 100,
                    "effective_from": "2026-08-02T00:00:00+00:00",
                    "effective_to": "2026-08-01T00:00:00+00:00",
                }],
            },
        ]
        for payload in invalid_choice_payloads:
            response = self.client.post(
                f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}/choices",
                headers=self.admin_headers,
                json=payload,
            )
            self.assertEqual(response.status_code, 422, response.text)

        null_patch = self.client.patch(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}",
            headers=self.admin_headers,
            json={"name": None},
        )
        self.assertEqual(null_patch.status_code, 422)

    def test_copy_on_write_edits_new_draft_and_keeps_published_snapshot_immutable(self):
        ids = self._create_valid_draft()
        publish_response = self.client.post(f"/api/v1/admin/v2/projects/{self.main_id}/publish", headers=self.admin_headers)
        self.assertEqual(publish_response.status_code, 200, publish_response.text)
        edit_response = self.client.patch(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}",
            headers=self.admin_headers,
            json={"name": "发布组不能直接改"},
        )
        self.assertEqual(edit_response.status_code, 409)
        new_group = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups",
            headers=self.admin_headers,
            json={"code": "room", "name": "房间偏好"},
        )
        self.assertEqual(new_group.status_code, 200, new_group.text)
        self.assertEqual(new_group.json()["catalog_version"]["status"], "draft")
        with self.SessionLocal() as db:
            project = db.get(Project, self.main_id)
            published = db.get(ProjectCatalogVersion, project.current_published_version_id)
            draft = db.scalar(select(ProjectCatalogVersion).where(ProjectCatalogVersion.project_id == self.main_id, ProjectCatalogVersion.status == "draft"))
            published_codes = [group.code for group in db.scalars(select(ProjectOptionGroup).where(ProjectOptionGroup.catalog_version_id == published.id))]
            draft_codes = [group.code for group in db.scalars(select(ProjectOptionGroup).where(ProjectOptionGroup.catalog_version_id == draft.id))]
            self.assertEqual(published_codes, ["touch"])
            self.assertEqual(draft.version, published.version + 1)
            self.assertIn("touch", draft_codes)
            self.assertIn("room", draft_codes)

    def test_draft_group_choice_and_prices_can_be_updated_and_physically_deleted(self):
        ids = self._create_valid_draft()
        choice_patch = self.client.patch(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}/choices/{ids['custom_choice_id']}",
            headers=self.admin_headers,
            json={
                "name": "热敷包升级",
                "prices": [
                    {"price_type": "store", "amount_cents": 2200, "effective_from": "2026-08-01T00:00:00+00:00"},
                    {"price_type": "group", "amount_cents": 1800, "effective_from": "2026-08-01T00:00:00+00:00"},
                ],
            },
        )
        self.assertEqual(choice_patch.status_code, 200, choice_patch.text)
        self.assertEqual(choice_patch.json()["name"], "热敷包升级")
        self.assertEqual({price["price_type"] for price in choice_patch.json()["prices"]}, {"group", "store"})

        delete_choice = self.client.delete(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}/choices/{ids['custom_choice_id']}",
            headers=self.admin_headers,
        )
        self.assertEqual(delete_choice.status_code, 200, delete_choice.text)
        delete_group = self.client.delete(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}",
            headers=self.admin_headers,
        )
        self.assertEqual(delete_group.status_code, 200, delete_group.text)
        with self.SessionLocal() as db:
            self.assertIsNone(db.get(ProjectOptionChoice, ids["custom_choice_id"]))
            self.assertEqual(
                db.scalar(select(OptionChoicePrice).where(OptionChoicePrice.option_choice_id == ids["custom_choice_id"])),
                None,
            )
            self.assertEqual(
                db.scalar(select(ProjectOptionGroup).where(ProjectOptionGroup.id == ids["group_id"])),
                None,
            )

    def test_published_and_superseded_children_cannot_be_patched_or_deleted(self):
        ids = self._create_valid_draft()
        first_publish = self.client.post(f"/api/v1/admin/v2/projects/{self.main_id}/publish", headers=self.admin_headers)
        self.assertEqual(first_publish.status_code, 200, first_publish.text)
        next_group = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups",
            headers=self.admin_headers,
            json={"code": "next", "name": "下一版"},
        )
        self.assertEqual(next_group.status_code, 200, next_group.text)
        next_choice = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{next_group.json()['id']}/choices",
            headers=self.admin_headers,
            json={"code": "one", "name": "一个", "choice_type": "preference", "charge_mode": "free"},
        )
        self.assertEqual(next_choice.status_code, 200, next_choice.text)
        second_publish = self.client.post(f"/api/v1/admin/v2/projects/{self.main_id}/publish", headers=self.admin_headers)
        self.assertEqual(second_publish.status_code, 200, second_publish.text)
        versions = self.client.get(f"/api/v1/admin/v2/projects/{self.main_id}/versions", headers=self.staff_headers)
        self.assertEqual(versions.status_code, 200, versions.text)
        self.assertEqual([item["version"] for item in versions.json()["items"]], [2, 1])
        self.assertEqual([item["status"] for item in versions.json()["items"]], ["published", "superseded"])
        self.assertEqual(len(versions.json()["items"][0]["hash"]), 64)
        for method, url, json_body in (
            ("patch", f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}", {"name": "改"}),
            ("delete", f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}", None),
            ("patch", f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}/choices/{ids['custom_choice_id']}", {"prices": [{"price_type": "store", "amount_cents": 1, "effective_from": "2026-08-01T00:00:00+00:00"}]}),
            ("delete", f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}/choices/{ids['custom_choice_id']}", None),
        ):
            if json_body is None:
                response = getattr(self.client, method)(url, headers=self.admin_headers)
            else:
                response = getattr(self.client, method)(url, headers=self.admin_headers, json=json_body)
            self.assertEqual(response.status_code, 409, response.text)

    def test_validate_publication_returns_structured_errors_and_publish_is_atomic(self):
        group_response = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups",
            headers=self.admin_headers,
            json={"code": "empty", "name": "空必选组", "required": True, "min_select": 1, "max_select": 1},
        )
        self.assertEqual(group_response.status_code, 200, group_response.text)
        validation = self.client.get(f"/api/v1/admin/v2/projects/{self.main_id}/validate-publication", headers=self.staff_headers)
        self.assertEqual(validation.status_code, 200)
        self.assertIn("required_group_empty", {error["code"] for error in validation.json()["errors"]})
        publish = self.client.post(f"/api/v1/admin/v2/projects/{self.main_id}/publish", headers=self.admin_headers)
        self.assertEqual(publish.status_code, 409)
        self.assertIn("path", publish.json()["errors"][0])
        with self.SessionLocal() as db:
            draft = db.scalar(select(ProjectCatalogVersion).where(ProjectCatalogVersion.project_id == self.main_id))
            self.assertEqual(draft.status, "draft")
            self.assertIsNone(draft.published_at)

    def test_price_preview_uses_server_prices_for_tuesday_free_linked_and_custom_lines(self):
        ids = self._create_valid_draft()
        response = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/price-preview",
            headers=self.staff_headers,
            json={
                "choice_ids": [ids["free_choice_id"], ids["linked_choice_id"], ids["custom_choice_id"]],
                "is_member": True,
                "confirmed_at": "2026-08-04T10:00:00+08:00",
                "store_timezone": "Asia/Shanghai",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual([line["basis"] for line in body["lines"]], ["tuesday_68", "free", "tuesday_68", "tuesday_68"])
        self.assertEqual([line["amount_cents"] for line in body["lines"]], [6800, 0, 2040, 1360])
        self.assertEqual(body["total_cents"], 10200)
        invalid_time = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/price-preview",
            headers=self.staff_headers,
            json={"choice_ids": [], "is_member": True, "confirmed_at": "2026-08-04T10:00:00", "store_timezone": "Asia/Shanghai"},
        )
        self.assertEqual(invalid_time.status_code, 422)
        other_group = self.client.post(
            f"/api/v1/admin/v2/projects/{self.other_project_id}/option-groups",
            headers=self.other_headers,
            json={"code": "other", "name": "其他"},
        )
        self.assertEqual(other_group.status_code, 200, other_group.text)
        other_choice = self.client.post(
            f"/api/v1/admin/v2/projects/{self.other_project_id}/price-preview",
            headers=self.other_headers,
            json={"choice_ids": [ids["free_choice_id"]], "is_member": False, "confirmed_at": "2026-08-04T10:00:00+08:00", "store_timezone": "Asia/Shanghai"},
        )
        self.assertEqual(other_choice.status_code, 404)

    def test_customer_catalog_returns_only_current_published_options_and_legacy_compatibility(self):
        ids = self._create_valid_draft()
        inactive = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}/choices",
            headers=self.admin_headers,
            json={"code": "hidden", "name": "隐藏", "choice_type": "preference", "charge_mode": "free", "status": "inactive"},
        )
        self.assertEqual(inactive.status_code, 200, inactive.text)
        published = self.client.post(f"/api/v1/admin/v2/projects/{self.main_id}/publish", headers=self.admin_headers)
        self.assertEqual(published.status_code, 200, published.text)
        self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups",
            headers=self.admin_headers,
            json={"code": "draft-only", "name": "草稿不可见"},
        )
        legacy = self._add_project_in_db("LEGACY", publication_status="published")
        detail = self.client.get(f"/api/v1/projects/{self.main_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        body = detail.json()
        self.assertEqual(body["catalog_version"], published.json()["version"])
        self.assertEqual([group["code"] for group in body["option_groups"]], ["touch"])
        choice_codes = [choice["code"] for choice in body["option_groups"][0]["choices"]]
        self.assertNotIn("hidden", choice_codes)
        self.assertEqual(body["option_groups"][0]["choices"][2]["prices"][0]["price_type"], "member")
        self.assertEqual(body["diy_options"][0]["label"], "旧选项")
        legacy_detail = self.client.get(f"/api/v1/projects/{legacy.id}")
        self.assertEqual(legacy_detail.status_code, 200, legacy_detail.text)
        self.assertIsNone(legacy_detail.json()["catalog_version"])
        self.assertEqual(legacy_detail.json()["option_groups"], [])
        listing = self.client.get("/api/v1/projects", params={"store_id": self.store_id})
        items_by_code = {item["code"]: item for item in listing.json()["items"]}
        self.assertEqual(items_by_code["MAIN"]["catalog_version"], published.json()["version"])
        self.assertEqual(items_by_code["LEGACY"]["catalog_version"], None)

    def test_archived_project_publish_is_rejected(self):
        response = self.client.post(f"/api/v1/admin/v2/projects/{self.archived_id}/publish", headers=self.admin_headers)
        self.assertEqual(response.status_code, 409)

    def _add_project_in_db(self, code, *, publication_status="published"):
        with self.SessionLocal() as db:
            store = db.get(Store, self.store_id)
            project = self._add_project(db, store, code, publication_status=publication_status)
            db.add(PriceBook(project_id=project.id, price_type="store", amount_cents=1000))
            db.commit()
            return project


if __name__ == "__main__":
    unittest.main()
