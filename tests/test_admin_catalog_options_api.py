import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.domain.catalog_options import _snapshot_hash, lock_catalog_projects
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
            linked_version.snapshot_hash = _snapshot_hash(db, linked_version.id)
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
        unrelated_patch = self.client.patch(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}/choices/{ids['linked_choice_id']}",
            headers=self.admin_headers,
            json={"name": "只改名称也应拒绝"},
        )
        self.assertEqual(unrelated_patch.status_code, 404)
        self.assertNotIn("OTHER", unrelated_patch.text)

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

    def test_copy_from_prefers_source_latest_draft_and_keeps_source_isolated(self):
        with self.SessionLocal() as db:
            source = db.get(Project, self.linked_id)
            published = db.get(ProjectCatalogVersion, source.current_published_version_id)
            published_group = ProjectOptionGroup(
                catalog_version_id=published.id,
                code="published-source",
                name="来源已发布组",
                selection_mode="multiple",
                max_select=1,
            )
            db.add(published_group)
            db.flush()
            published_choice = ProjectOptionChoice(
                option_group_id=published_group.id,
                code="published-choice",
                name="已发布选择",
                choice_type="dedicated_charge",
                charge_mode="custom_price",
            )
            db.add(published_choice)
            db.flush()
            db.add(OptionChoicePrice(
                option_choice_id=published_choice.id,
                price_type="store",
                amount_cents=321,
                effective_from=datetime(2026, 8, 1, tzinfo=UTC),
            ))
            db.flush()
            published.snapshot_hash = _snapshot_hash(db, published.id)

            source_draft = ProjectCatalogVersion(project_id=source.id, version=2, status="draft")
            db.add(source_draft)
            db.flush()
            draft_group = ProjectOptionGroup(
                catalog_version_id=source_draft.id,
                code="draft-source",
                name="来源最新草稿组",
                selection_mode="multiple",
                max_select=1,
            )
            db.add(draft_group)
            db.flush()
            db.add(ProjectOptionChoice(
                option_group_id=draft_group.id,
                code="draft-choice",
                name="草稿选择",
                choice_type="preference",
                charge_mode="free",
            ))
            db.commit()
            source_version_ids = list(
                db.scalars(
                    select(ProjectCatalogVersion.id)
                    .where(ProjectCatalogVersion.project_id == source.id)
                    .order_by(ProjectCatalogVersion.id)
                )
            )

        response = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/copy-from/{self.linked_id}",
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["project_id"], self.main_id)
        self.assertEqual(response.json()["source_project_id"], self.linked_id)
        self.assertEqual(response.json()["source_catalog_version"]["id"], source_draft.id)
        self.assertEqual(response.json()["catalog_version"]["status"], "draft")
        with self.SessionLocal() as db:
            target_draft = db.get(ProjectCatalogVersion, response.json()["catalog_version"]["id"])
            self.assertEqual(target_draft.project_id, self.main_id)
            target_groups = list(
                db.scalars(
                    select(ProjectOptionGroup).where(
                        ProjectOptionGroup.catalog_version_id == target_draft.id
                    )
                )
            )
            self.assertEqual([group.code for group in target_groups], ["draft-source"])
            self.assertEqual(
                list(
                    db.scalars(
                        select(ProjectCatalogVersion.id)
                        .where(ProjectCatalogVersion.project_id == self.linked_id)
                        .order_by(ProjectCatalogVersion.id)
                    )
                ),
                source_version_ids,
            )
            self.assertEqual(
                list(
                    db.scalars(
                        select(ProjectOptionGroup.code)
                        .where(ProjectOptionGroup.catalog_version_id == source_draft.id)
                    )
                ),
                ["draft-source"],
            )

    def test_copy_from_uses_published_source_with_prices_and_rejects_existing_target_draft(self):
        with self.SessionLocal() as db:
            source = db.get(Project, self.linked_id)
            published = db.get(ProjectCatalogVersion, source.current_published_version_id)
            group = ProjectOptionGroup(
                catalog_version_id=published.id,
                code="published-only",
                name="仅发布来源",
                selection_mode="multiple",
                max_select=1,
            )
            db.add(group)
            db.flush()
            choice = ProjectOptionChoice(
                option_group_id=group.id,
                code="paid",
                name="收费选择",
                choice_type="dedicated_charge",
                charge_mode="custom_price",
            )
            db.add(choice)
            db.flush()
            db.add(OptionChoicePrice(
                option_choice_id=choice.id,
                price_type="store",
                amount_cents=654,
                effective_from=datetime(2026, 8, 1, tzinfo=UTC),
            ))
            db.flush()
            published.snapshot_hash = _snapshot_hash(db, published.id)
            db.commit()

        copied = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/copy-from/{self.linked_id}",
            headers=self.admin_headers,
        )

        self.assertEqual(copied.status_code, 200, copied.text)
        self.assertEqual(copied.json()["source_catalog_version"]["id"], published.id)
        with self.SessionLocal() as db:
            target_group = db.scalar(
                select(ProjectOptionGroup).where(
                    ProjectOptionGroup.catalog_version_id == copied.json()["catalog_version"]["id"]
                )
            )
            target_choice = db.scalar(
                select(ProjectOptionChoice).where(ProjectOptionChoice.option_group_id == target_group.id)
            )
            target_price = db.scalar(
                select(OptionChoicePrice).where(OptionChoicePrice.option_choice_id == target_choice.id)
            )
            self.assertNotEqual(target_group.id, group.id)
            self.assertNotEqual(target_choice.id, choice.id)
            self.assertEqual(target_price.amount_cents, 654)

        duplicate = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/copy-from/{self.linked_id}",
            headers=self.admin_headers,
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)

        cross_store = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/copy-from/{self.other_project_id}",
            headers=self.admin_headers,
        )
        self.assertEqual(cross_store.status_code, 404, cross_store.text)

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

    def test_existing_draft_writes_use_the_shared_catalog_lock_protocol(self):
        ids = self._create_valid_draft()
        with patch(
            "app.api.admin_catalog.lock_catalog_projects",
            wraps=lock_catalog_projects,
        ) as acquire_lock:
            extra_choice = self.client.post(
                f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}/choices",
                headers=self.admin_headers,
                json={
                    "code": "locked-extra",
                    "name": "锁定追加",
                    "choice_type": "preference",
                    "charge_mode": "free",
                },
            )
            group_patch = self.client.patch(
                f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}",
                headers=self.admin_headers,
                json={"name": "锁定更新组"},
            )
            choice_patch = self.client.patch(
                f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}/choices/{ids['custom_choice_id']}",
                headers=self.admin_headers,
                json={"name": "锁定更新选项"},
            )
            choice_delete = self.client.delete(
                f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}/choices/{extra_choice.json()['id']}",
                headers=self.admin_headers,
            )
            group_delete = self.client.delete(
                f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{ids['group_id']}",
                headers=self.admin_headers,
            )

        for response in (extra_choice, group_patch, choice_patch, choice_delete, group_delete):
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(acquire_lock.call_count, 5)

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

    def test_price_preview_uses_member_prices_when_membership_type_is_unknown(self):
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
        self.assertEqual([line["basis"] for line in body["lines"]], ["member", "free", "member", "member"])
        self.assertEqual([line["amount_cents"] for line in body["lines"]], [8000, 0, 2500, 1500])
        self.assertEqual(body["total_cents"], 12000)
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

    def test_customer_catalog_uses_authoritative_price_bands_and_price_source(self):
        ids = self._create_valid_draft()
        with self.SessionLocal() as db:
            linked = db.get(Project, self.linked_id)
            db.add(PriceBook(
                project_id=linked.id,
                price_type="store",
                amount_cents=3300,
                publisher="new-price",
            ))
            db.commit()

        published = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/publish",
            headers=self.admin_headers,
        )
        self.assertEqual(published.status_code, 200, published.text)
        response = self.client.get(f"/api/v1/projects/{self.main_id}")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        choice_by_code = {
            choice["code"]: choice
            for choice in body["option_groups"][0]["choices"]
        }
        self.assertEqual(choice_by_code["soft"]["price_source"], "free")
        self.assertEqual(choice_by_code["soft"]["prices"], [])
        self.assertEqual(choice_by_code["neck"]["price_source"], "linked_project")
        self.assertEqual(
            {price["price_type"]: price["amount_cents"] for price in choice_by_code["neck"]["prices"]}["store"],
            3300,
        )
        self.assertEqual(choice_by_code["hot-pack"]["price_source"], "option_choice_price")
        self.assertEqual(
            {price["price_type"] for price in choice_by_code["hot-pack"]["prices"]},
            {"store", "member"},
        )
        self.assertEqual(
            len([price for price in body["prices"] if price["price_type"] == "store"]),
            1,
        )

    def _publish_parent_with_pinned_linked_catalog(self):
        with self.SessionLocal() as db:
            linked = db.get(Project, self.linked_id)
            linked_version = db.get(ProjectCatalogVersion, linked.current_published_version_id)
            group = ProjectOptionGroup(
                catalog_version_id=linked_version.id,
                code="linked-v1",
                name="引用项目第一版",
                selection_mode="single",
                max_select=1,
            )
            db.add(group)
            db.flush()
            choice = ProjectOptionChoice(
                option_group_id=group.id,
                code="linked-v1-choice",
                name="第一版偏好",
                choice_type="preference",
                charge_mode="free",
            )
            db.add(choice)
            db.flush()
            linked_version.snapshot_hash = _snapshot_hash(db, linked_version.id)
            db.commit()
            linked_version_id = linked_version.id
            linked_choice_id = choice.id

        self._create_valid_draft()
        published = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/publish",
            headers=self.admin_headers,
        )
        self.assertEqual(published.status_code, 200, published.text)
        return linked_version_id, linked_choice_id

    def test_customer_parent_returns_the_pinned_linked_catalog_snapshot(self):
        pinned_version_id, _ = self._publish_parent_with_pinned_linked_catalog()
        with self.SessionLocal() as db:
            linked = db.get(Project, self.linked_id)
            old = db.get(ProjectCatalogVersion, pinned_version_id)
            old.status = "superseded"
            db.flush()
            current = ProjectCatalogVersion(project_id=linked.id, version=2, status="published")
            db.add(current)
            db.flush()
            linked.current_published_version_id = current.id
            group = ProjectOptionGroup(
                catalog_version_id=current.id,
                code="linked-v2",
                name="引用项目第二版",
                selection_mode="single",
                max_select=1,
            )
            db.add(group)
            db.flush()
            db.add(ProjectOptionChoice(
                option_group_id=group.id,
                code="linked-v2-choice",
                name="第二版偏好",
                choice_type="preference",
                charge_mode="free",
            ))
            db.flush()
            current.snapshot_hash = _snapshot_hash(db, current.id)
            db.commit()

        response = self.client.get(f"/api/v1/projects/{self.main_id}")
        self.assertEqual(response.status_code, 200, response.text)
        linked_choice = next(
            choice
            for choice in response.json()["option_groups"][0]["choices"]
            if choice["code"] == "neck"
        )
        self.assertEqual(linked_choice["linked_catalog_version_id"], pinned_version_id)
        snapshot = linked_choice["linked_catalog_snapshot"]
        self.assertEqual(snapshot["id"], pinned_version_id)
        self.assertEqual([group["code"] for group in snapshot["option_groups"]], ["linked-v1"])

    def test_customer_parent_rejects_drift_in_its_pinned_linked_catalog(self):
        _, linked_choice_id = self._publish_parent_with_pinned_linked_catalog()
        with self.SessionLocal() as db:
            db.get(ProjectOptionChoice, linked_choice_id).name = "被篡改的引用偏好"
            db.commit()

        response = self.client.get(f"/api/v1/projects/{self.main_id}")
        self.assertEqual(response.status_code, 409, response.text)

    def test_customer_catalog_and_copy_on_write_reject_published_hash_drift(self):
        ids = self._create_valid_draft()
        published = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/publish",
            headers=self.admin_headers,
        )
        self.assertEqual(published.status_code, 200, published.text)
        with self.SessionLocal() as db:
            choice = db.get(ProjectOptionChoice, ids["free_choice_id"])
            choice.name = "被直接篡改"
            db.commit()

        customer_read = self.client.get(f"/api/v1/projects/{self.main_id}")
        self.assertEqual(customer_read.status_code, 409)
        copy_on_write = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups",
            headers=self.admin_headers,
            json={"code": "after-drift", "name": "篡改后草稿"},
        )
        self.assertEqual(copy_on_write.status_code, 409)

    def test_project_crud_is_strict_and_protects_published_link_references(self):
        ids = self._create_valid_draft()
        published = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/publish",
            headers=self.admin_headers,
        )
        self.assertEqual(published.status_code, 200, published.text)

        for payload in (
            {"unexpected": True},
            {"diy_options": []},
            {"current_published_version_id": 999999},
            {"prices": {"store": "100"}},
        ):
            response = self.client.patch(
                f"/api/v1/admin/v2/projects/{self.linked_id}",
                headers=self.admin_headers,
                json=payload,
            )
            self.assertEqual(response.status_code, 422, response.text)

        code_change = self.client.patch(
            f"/api/v1/admin/v2/projects/{self.linked_id}",
            headers=self.admin_headers,
            json={"code": "LINKED-RENAMED"},
        )
        self.assertEqual(code_change.status_code, 409, code_change.text)
        archive = self.client.patch(
            f"/api/v1/admin/v2/projects/{self.linked_id}",
            headers=self.admin_headers,
            json={"publication_status": "archived"},
        )
        self.assertEqual(archive.status_code, 409, archive.text)

        create = self.client.post(
            "/api/v1/admin/v2/projects",
            headers=self.admin_headers,
            json={
                "store_id": self.store_id,
                "code": "STRICT-CREATE",
                "category": "catalog-test",
                "name": "严格项目",
                "prices": {"store": 1000, "member": 800},
                "diy_options": [],
            },
        )
        self.assertEqual(create.status_code, 422, create.text)

    def test_project_create_rejects_a_published_project_without_store_price(self):
        response = self.client.post(
            "/api/v1/admin/v2/projects",
            headers=self.admin_headers,
            json={
                "store_id": self.store_id,
                "code": "UNPRICED-PUBLISHED",
                "category": "catalog-test",
                "name": "无价正式项目",
                "publication_status": "published",
            },
        )
        self.assertEqual(response.status_code, 422, response.text)

    def test_linked_choice_rejects_a_published_leaf_without_store_price(self):
        with self.SessionLocal() as db:
            unpriced = Project(
                store_id=self.store_id,
                code="UNPRICED-LEAF",
                category="catalog-test",
                name="无价叶子项目",
                publication_status="published",
            )
            db.add(unpriced)
            db.commit()
            unpriced_id = unpriced.id

        group = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups",
            headers=self.admin_headers,
            json={"code": "unpriced-link", "name": "无价引用"},
        )
        self.assertEqual(group.status_code, 200, group.text)
        response = self.client.post(
            f"/api/v1/admin/v2/projects/{self.main_id}/option-groups/{group.json()['id']}/choices",
            headers=self.admin_headers,
            json={
                "code": "unpriced-leaf",
                "name": "无价叶子",
                "choice_type": "linked_project",
                "charge_mode": "inherit_linked_price",
                "linked_project_id": unpriced_id,
            },
        )
        self.assertEqual(response.status_code, 422, response.text)

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
