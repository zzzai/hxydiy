import os
import subprocess
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import create_engine, delete, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.db.session import Base
from app.domain.catalog_options import _snapshot_hash
from app.models import (
    Addon,
    OptionChoicePrice,
    PriceBook,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    Store,
)
from scripts.migrate_catalog_options import main, migrate_store_catalog


class CatalogOptionMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        Base.metadata.create_all(self.engine)

        with self.SessionLocal() as db:
            store = Store(store_code="migration-store", name="迁移门店", address="测试地址")
            other_store = Store(store_code="other-migration-store", name="其他门店", address="测试地址")
            db.add_all([store, other_store])
            db.flush()

            project = Project(
                store_id=store.id,
                code="hxy-jubu-30",
                category="local-strength",
                name="局部调理",
                publication_status="published",
                diy_options=[
                    {"label": "肩颈", "price_cents": 600},
                    {"label": "肩颈", "price_cents": 0},
                ],
            )
            other_project = Project(
                store_id=other_store.id,
                code="other-legacy-project",
                category="test",
                name="其他门店旧项目",
                publication_status="published",
                diy_options=[{"label": "不得迁移", "price_cents": 100}],
            )
            db.add_all([project, other_project])
            db.flush()
            db.add_all([
                PriceBook(project_id=project.id, price_type="store", amount_cents=8900),
                PriceBook(project_id=project.id, price_type="member", amount_cents=6900),
            ])

            published = ProjectCatalogVersion(project_id=project.id, version=1, status="published")
            db.add(published)
            db.flush()
            project.current_published_version_id = published.id
            published.snapshot_hash = _snapshot_hash(db, published.id)

            db.add_all([
                Addon(
                    store_id=store.id,
                    code="charged-addon",
                    name="收费加项",
                    parent_project_id=project.id,
                    chargeable=True,
                    store_price_cents=1500,
                    member_price_cents=1000,
                    member_price_enabled=True,
                    price_cents=1900,
                    publication_status="published",
                ),
                Addon(
                    store_id=store.id,
                    code="free-addon",
                    name="免费偏好",
                    parent_project_id=project.id,
                    chargeable=False,
                    price_cents=0,
                    publication_status="published",
                ),
                Addon(
                    store_id=store.id,
                    code="fallback-addon",
                    name="回退价加项",
                    parent_project_id=project.id,
                    chargeable=True,
                    store_price_cents=None,
                    member_price_cents=800,
                    member_price_enabled=False,
                    price_cents=1200,
                    publication_status="published",
                ),
                Addon(
                    store_id=store.id,
                    code="independent-addon",
                    name="独立加项",
                    parent_project_id=None,
                    chargeable=True,
                    price_cents=2900,
                    publication_status="published",
                ),
                Addon(
                    store_id=store.id,
                    code="cross-store-addon",
                    name="跨店错误关联",
                    parent_project_id=other_project.id,
                    chargeable=True,
                    price_cents=3900,
                    publication_status="published",
                ),
                Addon(
                    store_id=store.id,
                    code="missing-parent-addon",
                    name="父项丢失",
                    parent_project_id=999999,
                    chargeable=True,
                    price_cents=4900,
                    publication_status="published",
                ),
            ])
            db.commit()
            self.store_id = store.id
            self.other_store_id = other_store.id
            self.project_id = project.id
            self.other_project_id = other_project.id

    def tearDown(self):
        self.engine.dispose()

    def _count(self, db, model):
        return db.scalar(select(func.count()).select_from(model))

    def test_dry_run_is_completely_read_only(self):
        with self.SessionLocal() as db:
            before = {
                model: self._count(db, model)
                for model in (ProjectCatalogVersion, ProjectOptionGroup, ProjectOptionChoice, OptionChoicePrice)
            }

            report = migrate_store_catalog(db, store_id=self.store_id, dry_run=True)

            after = {model: self._count(db, model) for model in before}
            self.assertEqual(after, before)
            self.assertFalse(db.new)
            self.assertGreater(report.created_choices, 0)

    def test_dry_run_does_not_autoflush_or_change_caller_session_state(self):
        DefaultSession = sessionmaker(bind=self.engine, expire_on_commit=False)
        with DefaultSession() as db:
            project = db.get(Project, self.project_id)
            deleted_price = db.scalar(select(PriceBook).where(
                PriceBook.project_id == self.project_id,
                PriceBook.price_type == "store",
            ))
            pending_store = Store(store_code="caller-pending", name="调用方待写门店", address="测试地址")
            db.add(pending_store)
            project.summary = "调用方尚未提交的修改"
            db.delete(deleted_price)
            before = {
                "new": {id(item) for item in db.new},
                "dirty": {id(item) for item in db.dirty},
                "deleted": {id(item) for item in db.deleted},
            }
            flushes = []

            def record_flush(*_args):
                flushes.append(True)

            event.listen(db, "before_flush", record_flush)
            try:
                migrate_store_catalog(db, store_id=self.store_id, dry_run=True)
            finally:
                event.remove(db, "before_flush", record_flush)

            after = {
                "new": {id(item) for item in db.new},
                "dirty": {id(item) for item in db.dirty},
                "deleted": {id(item) for item in db.deleted},
            }
            self.assertEqual(flushes, [])
            self.assertEqual(after, before)
            self.assertEqual(project.summary, "调用方尚未提交的修改")

    def test_new_draft_copies_the_complete_published_catalog_before_adding_legacy_groups(self):
        effective_from = datetime(2026, 8, 1, tzinfo=UTC)
        effective_to = effective_from + timedelta(days=30)
        with self.SessionLocal() as db:
            project = db.get(Project, self.project_id)
            published_id = project.current_published_version_id
            source_group = ProjectOptionGroup(
                catalog_version_id=published_id,
                code="published-group",
                name="已发布选项组",
                description="必须完整复制的组",
                selection_mode="single",
                required=True,
                min_select=1,
                max_select=1,
                display_order=7,
            )
            db.add(source_group)
            db.flush()
            source_choice = ProjectOptionChoice(
                option_group_id=source_group.id,
                code="published-choice",
                name="已发布选项",
                description="必须完整复制的选项",
                choice_type="dedicated_charge",
                linked_project_id=None,
                charge_mode="custom_price",
                independently_visible=False,
                coupon_eligible=True,
                annual_gift_eligible=True,
                qualifies_for_foot_bath_bundle=True,
                display_order=9,
                status="inactive",
            )
            db.add(source_choice)
            db.flush()
            source_price = OptionChoicePrice(
                option_choice_id=source_choice.id,
                price_type="store",
                amount_cents=2300,
                effective_from=effective_from,
                effective_to=effective_to,
            )
            db.add(source_price)
            db.flush()
            db.get(ProjectCatalogVersion, published_id).snapshot_hash = _snapshot_hash(db, published_id)
            db.commit()
            source_ids = (source_group.id, source_choice.id, source_price.id)

            migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.flush()

            project = db.get(Project, self.project_id)
            self.assertEqual(project.current_published_version_id, published_id)
            draft = db.scalar(select(ProjectCatalogVersion).where(
                ProjectCatalogVersion.project_id == self.project_id,
                ProjectCatalogVersion.status == "draft",
            ))
            copied_group = db.scalar(select(ProjectOptionGroup).where(
                ProjectOptionGroup.catalog_version_id == draft.id,
                ProjectOptionGroup.code == "published-group",
            ))
            self.assertIsNotNone(copied_group)
            self.assertNotEqual(copied_group.id, source_ids[0])
            self.assertEqual(
                (
                    copied_group.name,
                    copied_group.description,
                    copied_group.selection_mode,
                    copied_group.required,
                    copied_group.min_select,
                    copied_group.max_select,
                    copied_group.display_order,
                ),
                ("已发布选项组", "必须完整复制的组", "single", True, 1, 1, 7),
            )
            copied_choice = db.scalar(select(ProjectOptionChoice).where(
                ProjectOptionChoice.option_group_id == copied_group.id,
                ProjectOptionChoice.code == "published-choice",
            ))
            self.assertNotEqual(copied_choice.id, source_ids[1])
            self.assertEqual(
                (
                    copied_choice.name,
                    copied_choice.description,
                    copied_choice.choice_type,
                    copied_choice.linked_project_id,
                    copied_choice.charge_mode,
                    copied_choice.independently_visible,
                    copied_choice.coupon_eligible,
                    copied_choice.annual_gift_eligible,
                    copied_choice.qualifies_for_foot_bath_bundle,
                    copied_choice.display_order,
                    copied_choice.status,
                ),
                ("已发布选项", "必须完整复制的选项", "dedicated_charge", None, "custom_price", False, True, True, True, 9, "inactive"),
            )
            copied_price = db.scalar(select(OptionChoicePrice).where(
                OptionChoicePrice.option_choice_id == copied_choice.id
            ))
            self.assertNotEqual(copied_price.id, source_ids[2])
            self.assertEqual(
                (copied_price.price_type, copied_price.amount_cents, copied_price.effective_from, copied_price.effective_to),
                ("store", 2300, effective_from.replace(tzinfo=None), effective_to.replace(tzinfo=None)),
            )
            self.assertEqual(db.get(ProjectOptionGroup, source_ids[0]).name, "已发布选项组")
            self.assertEqual(db.get(ProjectOptionChoice, source_ids[1]).name, "已发布选项")
            self.assertEqual(db.get(OptionChoicePrice, source_ids[2]).amount_cents, 2300)

    def test_apply_is_idempotent_preserves_project_prices_and_maps_legacy_sources(self):
        with self.SessionLocal() as db:
            first = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            second = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.commit()

            self.assertEqual((first.created_versions, first.created_groups, first.created_choices), (1, 2, 5))
            self.assertEqual((second.created_versions, second.created_groups, second.created_choices), (0, 0, 0))

            project = db.scalar(select(Project).where(Project.code == "hxy-jubu-30"))
            member_price = db.scalar(select(PriceBook.amount_cents).where(
                PriceBook.project_id == project.id,
                PriceBook.price_type == "member",
            ))
            self.assertEqual(member_price, 6900)

            versions = list(db.scalars(
                select(ProjectCatalogVersion)
                .where(ProjectCatalogVersion.project_id == project.id)
                .order_by(ProjectCatalogVersion.version)
            ))
            self.assertEqual([(row.version, row.status) for row in versions], [(1, "published"), (2, "draft")])
            self.assertEqual(project.current_published_version_id, versions[0].id)

            groups = list(db.scalars(select(ProjectOptionGroup).where(
                ProjectOptionGroup.catalog_version_id == versions[1].id
            )))
            self.assertEqual(len(groups), 2)
            self.assertTrue(all(group.selection_mode == "multiple" and not group.required for group in groups))

            choices = list(db.scalars(
                select(ProjectOptionChoice)
                .join(ProjectOptionGroup)
                .where(ProjectOptionGroup.catalog_version_id == versions[1].id)
            ))
            by_name = {}
            for choice in choices:
                by_name.setdefault(choice.name, []).append(choice)
            self.assertEqual(len(by_name["肩颈"]), 2)
            self.assertEqual(len({choice.code for choice in by_name["肩颈"]}), 2)
            self.assertTrue(all(
                choice.choice_type == "preference" and choice.charge_mode == "free"
                for choice in by_name["肩颈"]
            ))
            self.assertEqual(
                (by_name["收费加项"][0].choice_type, by_name["收费加项"][0].charge_mode),
                ("dedicated_charge", "custom_price"),
            )
            self.assertEqual(
                (by_name["免费偏好"][0].choice_type, by_name["免费偏好"][0].charge_mode),
                ("preference", "free"),
            )
            self.assertNotIn("独立加项", by_name)
            self.assertNotIn("跨店错误关联", by_name)
            self.assertNotIn("父项丢失", by_name)

            charged_prices = list(db.scalars(select(OptionChoicePrice).where(
                OptionChoicePrice.option_choice_id == by_name["收费加项"][0].id
            )))
            self.assertEqual(
                {(price.price_type, price.amount_cents) for price in charged_prices},
                {("store", 1500), ("member", 1000)},
            )
            fallback_prices = list(db.scalars(select(OptionChoicePrice).where(
                OptionChoicePrice.option_choice_id == by_name["回退价加项"][0].id
            )))
            self.assertEqual(
                {(price.price_type, price.amount_cents) for price in fallback_prices},
                {("store", 1200)},
            )
            free_price_count = db.scalar(select(func.count()).select_from(OptionChoicePrice).where(
                OptionChoicePrice.option_choice_id == by_name["免费偏好"][0].id
            ))
            self.assertEqual(free_price_count, 0)
            self.assertTrue(any("肩颈" in warning and "price_cents" in warning for warning in first.warnings))
            self.assertTrue(any("cross-store-addon" in warning for warning in first.warnings))
            self.assertTrue(any("missing-parent-addon" in warning for warning in first.warnings))

    def test_apply_reconciles_current_addon_prices_without_destroying_price_history(self):
        now = datetime.now(UTC)
        with self.SessionLocal() as db:
            migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.commit()
            draft = db.scalar(select(ProjectCatalogVersion).where(
                ProjectCatalogVersion.project_id == self.project_id,
                ProjectCatalogVersion.status == "draft",
            ))
            choices = list(db.scalars(
                select(ProjectOptionChoice)
                .join(ProjectOptionGroup)
                .where(ProjectOptionGroup.catalog_version_id == draft.id)
            ))
            by_name = {choice.name: choice for choice in choices}
            charged = by_name["收费加项"]
            fallback = by_name["回退价加项"]
            db.execute(delete(OptionChoicePrice).where(
                OptionChoicePrice.option_choice_id.in_([charged.id, fallback.id])
            ))
            db.add_all([
                OptionChoicePrice(
                    option_choice_id=charged.id,
                    price_type="store",
                    amount_cents=900,
                    effective_from=now - timedelta(days=10),
                    effective_to=now - timedelta(days=5),
                ),
                OptionChoicePrice(
                    option_choice_id=charged.id,
                    price_type="store",
                    amount_cents=1700,
                    effective_from=now + timedelta(days=5),
                ),
                OptionChoicePrice(
                    option_choice_id=charged.id,
                    price_type="member",
                    amount_cents=700,
                    effective_from=now - timedelta(days=10),
                    effective_to=now - timedelta(days=5),
                ),
                OptionChoicePrice(
                    option_choice_id=charged.id,
                    price_type="member",
                    amount_cents=1100,
                    effective_from=now + timedelta(days=5),
                ),
                OptionChoicePrice(
                    option_choice_id=fallback.id,
                    price_type="store",
                    amount_cents=999,
                    effective_from=now - timedelta(days=2),
                ),
            ])
            db.flush()
            db.commit()

            first = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.flush()
            counts_after_first = {
                choice.id: db.scalar(select(func.count()).select_from(OptionChoicePrice).where(
                    OptionChoicePrice.option_choice_id == choice.id
                ))
                for choice in (charged, fallback)
            }
            second = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.flush()
            counts_after_second = {
                choice.id: db.scalar(select(func.count()).select_from(OptionChoicePrice).where(
                    OptionChoicePrice.option_choice_id == choice.id
                ))
                for choice in (charged, fallback)
            }

            rows = list(db.scalars(select(OptionChoicePrice).where(
                OptionChoicePrice.option_choice_id.in_([charged.id, fallback.id])
            )))
            current = [row for row in rows if row.effective_from <= datetime.now(UTC).replace(tzinfo=None) and (
                row.effective_to is None or row.effective_to > datetime.now(UTC).replace(tzinfo=None)
            )]
            current_by_key = {(row.option_choice_id, row.price_type): row for row in current}
            self.assertEqual(current_by_key[(charged.id, "store")].amount_cents, 1500)
            self.assertEqual(current_by_key[(charged.id, "member")].amount_cents, 1000)
            self.assertEqual(current_by_key[(fallback.id, "store")].amount_cents, 1200)
            switch_times = {
                current_by_key[(charged.id, "store")].effective_from,
                current_by_key[(charged.id, "member")].effective_from,
                current_by_key[(fallback.id, "store")].effective_from,
            }
            self.assertEqual(len(switch_times), 1)
            conflicting_history = next(row for row in rows if (
                row.option_choice_id == fallback.id
                and row.price_type == "store"
                and row.amount_cents == 999
            ))
            self.assertEqual(conflicting_history.effective_to, next(iter(switch_times)))
            self.assertTrue(any("回退价加项" in warning and "999" in warning and "1200" in warning for warning in first.warnings))
            self.assertEqual(counts_after_second, counts_after_first)
            self.assertFalse(any("回退价加项" in warning and "999" in warning for warning in second.warnings))

    def test_copy_on_write_prices_are_visible_to_same_migration_reconciliation(self):
        now = datetime.now(UTC)
        with self.SessionLocal() as db:
            project = db.get(Project, self.project_id)
            project.diy_options = []
            source_group = ProjectOptionGroup(
                catalog_version_id=project.current_published_version_id,
                code="legacy-addons",
                name="旧加项（待审核）",
                selection_mode="multiple",
                required=False,
                min_select=0,
                max_select=1,
            )
            db.add(source_group)
            db.flush()
            source_choice = ProjectOptionChoice(
                option_group_id=source_group.id,
                code="addon-charged-addon",
                name="收费加项",
                choice_type="dedicated_charge",
                charge_mode="custom_price",
            )
            db.add(source_choice)
            db.flush()
            db.add_all([
                OptionChoicePrice(
                    option_choice_id=source_choice.id,
                    price_type="store",
                    amount_cents=1100,
                    effective_from=now - timedelta(days=20),
                    effective_to=now - timedelta(days=15),
                ),
                OptionChoicePrice(
                    option_choice_id=source_choice.id,
                    price_type="store",
                    amount_cents=1300,
                    effective_from=now - timedelta(days=10),
                ),
                OptionChoicePrice(
                    option_choice_id=source_choice.id,
                    price_type="store",
                    amount_cents=1700,
                    effective_from=now + timedelta(days=10),
                ),
                OptionChoicePrice(
                    option_choice_id=source_choice.id,
                    price_type="member",
                    amount_cents=900,
                    effective_from=now - timedelta(days=10),
                ),
            ])
            db.flush()
            db.get(ProjectCatalogVersion, project.current_published_version_id).snapshot_hash = _snapshot_hash(
                db,
                project.current_published_version_id,
            )
            db.commit()

            first = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.flush()
            draft = db.scalar(select(ProjectCatalogVersion).where(
                ProjectCatalogVersion.project_id == self.project_id,
                ProjectCatalogVersion.status == "draft",
            ))
            copied_group = db.scalar(select(ProjectOptionGroup).where(
                ProjectOptionGroup.catalog_version_id == draft.id,
                ProjectOptionGroup.code == "legacy-addons",
            ))
            copied_choice = db.scalar(select(ProjectOptionChoice).where(
                ProjectOptionChoice.option_group_id == copied_group.id,
                ProjectOptionChoice.code == "addon-charged-addon",
            ))
            rows_after_first = list(db.scalars(select(OptionChoicePrice).where(
                OptionChoicePrice.option_choice_id == copied_choice.id
            )))
            check_at = datetime.now(UTC).replace(tzinfo=None)
            current_after_first = [row for row in rows_after_first if (
                row.effective_from.replace(tzinfo=None) <= check_at
                and (row.effective_to is None or row.effective_to.replace(tzinfo=None) > check_at)
            )]
            self.assertEqual(
                {(row.price_type, row.amount_cents) for row in current_after_first},
                {("store", 1500), ("member", 1000)},
            )
            self.assertEqual(len(current_after_first), 2)
            replaced = {(row.price_type, row.amount_cents): row for row in rows_after_first}
            switch_time = replaced[("store", 1500)].effective_from
            self.assertEqual(replaced[("member", 1000)].effective_from, switch_time)
            self.assertEqual(replaced[("store", 1300)].effective_to, switch_time)
            self.assertEqual(replaced[("member", 900)].effective_to, switch_time)
            self.assertIsNotNone(replaced[("store", 1100)].effective_to)
            self.assertIsNone(replaced[("store", 1700)].effective_to)
            self.assertTrue(any("收费加项" in warning and "1300" in warning and "1500" in warning for warning in first.warnings))
            self.assertTrue(any("收费加项" in warning and "900" in warning and "1000" in warning for warning in first.warnings))

            count_after_first = len(rows_after_first)
            second = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.flush()
            count_after_second = db.scalar(select(func.count()).select_from(OptionChoicePrice).where(
                OptionChoicePrice.option_choice_id == copied_choice.id
            ))
            self.assertEqual(count_after_second, count_after_first)
            self.assertFalse(any("收费加项" in warning and "replaced" in warning for warning in second.warnings))

    def test_copy_on_write_does_not_duplicate_matching_current_prices(self):
        now = datetime.now(UTC)
        with self.SessionLocal() as db:
            project = db.get(Project, self.project_id)
            project.diy_options = []
            source_group = ProjectOptionGroup(
                catalog_version_id=project.current_published_version_id,
                code="legacy-addons",
                name="旧加项（待审核）",
                selection_mode="multiple",
                required=False,
                min_select=0,
                max_select=1,
            )
            db.add(source_group)
            db.flush()
            source_choice = ProjectOptionChoice(
                option_group_id=source_group.id,
                code="addon-charged-addon",
                name="收费加项",
                choice_type="dedicated_charge",
                charge_mode="custom_price",
            )
            db.add(source_choice)
            db.flush()
            db.add_all([
                OptionChoicePrice(
                    option_choice_id=source_choice.id,
                    price_type="store",
                    amount_cents=1500,
                    effective_from=now - timedelta(days=5),
                ),
                OptionChoicePrice(
                    option_choice_id=source_choice.id,
                    price_type="member",
                    amount_cents=1000,
                    effective_from=now - timedelta(days=5),
                ),
            ])
            db.flush()
            db.get(ProjectCatalogVersion, project.current_published_version_id).snapshot_hash = _snapshot_hash(
                db,
                project.current_published_version_id,
            )
            db.commit()

            migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.flush()
            draft = db.scalar(select(ProjectCatalogVersion).where(
                ProjectCatalogVersion.project_id == self.project_id,
                ProjectCatalogVersion.status == "draft",
            ))
            copied_choice = db.scalar(
                select(ProjectOptionChoice)
                .join(ProjectOptionGroup)
                .where(
                    ProjectOptionGroup.catalog_version_id == draft.id,
                    ProjectOptionChoice.code == "addon-charged-addon",
                )
            )
            rows_after_first = list(db.scalars(select(OptionChoicePrice).where(
                OptionChoicePrice.option_choice_id == copied_choice.id
            )))
            self.assertEqual(len(rows_after_first), 2)
            self.assertEqual(
                {(row.price_type, row.amount_cents) for row in rows_after_first},
                {("store", 1500), ("member", 1000)},
            )

            migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.flush()
            self.assertEqual(db.scalar(select(func.count()).select_from(OptionChoicePrice).where(
                OptionChoicePrice.option_choice_id == copied_choice.id
            )), 2)

    def test_only_the_requested_store_is_migrated(self):
        with self.SessionLocal() as db:
            migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.commit()

            other_versions = self._count(
                db,
                ProjectCatalogVersion,
            )
            self.assertEqual(other_versions, 2)
            self.assertIsNone(db.get(Project, self.other_project_id).current_published_version_id)
            self.assertIsNone(db.scalar(select(ProjectCatalogVersion).where(
                ProjectCatalogVersion.project_id == self.other_project_id
            )))

    def test_legacy_choice_identity_survives_reordering_prepend_and_duplicate_labels(self):
        with self.SessionLocal() as db:
            project = db.get(Project, self.project_id)
            project.diy_options = [
                {"label": "肩颈", "price_cents": 0},
                {"label": "腿部", "price_cents": 0},
                {"label": "肩颈", "price_cents": 0},
            ]
            db.commit()
            migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.flush()
            draft = db.scalar(select(ProjectCatalogVersion).where(
                ProjectCatalogVersion.project_id == self.project_id,
                ProjectCatalogVersion.status == "draft",
            ))
            legacy_group = db.scalar(select(ProjectOptionGroup).where(
                ProjectOptionGroup.catalog_version_id == draft.id,
                ProjectOptionGroup.code == "legacy-diy-options",
            ))
            original = list(db.scalars(
                select(ProjectOptionChoice)
                .where(ProjectOptionChoice.option_group_id == legacy_group.id)
                .order_by(ProjectOptionChoice.display_order, ProjectOptionChoice.id)
            ))
            original_codes = [choice.code for choice in original]
            self.assertEqual([choice.name for choice in original], ["肩颈", "腿部", "肩颈"])

            project.diy_options = [
                {"label": "足部", "price_cents": 0},
                {"label": "肩颈", "price_cents": 0},
                {"label": "肩颈", "price_cents": 0},
                {"label": "腿部", "price_cents": 0},
            ]
            second = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.flush()
            third = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.flush()

            migrated = list(db.scalars(
                select(ProjectOptionChoice)
                .where(ProjectOptionChoice.option_group_id == legacy_group.id)
                .order_by(ProjectOptionChoice.id)
            ))
            migrated_by_name = {}
            for choice in migrated:
                migrated_by_name.setdefault(choice.name, []).append(choice.code)
            self.assertEqual(len(migrated), 4)
            self.assertEqual(set(migrated_by_name["肩颈"]), {original_codes[0], original_codes[2]})
            self.assertEqual(migrated_by_name["腿部"], [original_codes[1]])
            self.assertEqual(len(migrated_by_name["足部"]), 1)
            self.assertEqual(second.created_choices, 1)
            self.assertEqual(third.created_choices, 0)
            self.assertTrue(all(len(choice.code) <= 32 for choice in migrated))

    def test_legacy_identity_uses_normalized_source_without_absorbing_real_code_collision(self):
        with self.SessionLocal() as db:
            project = db.get(Project, self.project_id)
            project.diy_options = [
                {"label": "Shoulder Relax", "price_cents": 0},
                {"label": "Waist", "price_cents": 0},
                {"label": "Shoulder Relax", "price_cents": 0},
            ]
            db.commit()
            migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.flush()
            draft = db.scalar(select(ProjectCatalogVersion).where(
                ProjectCatalogVersion.project_id == self.project_id,
                ProjectCatalogVersion.status == "draft",
            ))
            legacy_group = db.scalar(select(ProjectOptionGroup).where(
                ProjectOptionGroup.catalog_version_id == draft.id,
                ProjectOptionGroup.code == "legacy-diy-options",
            ))
            original = list(db.scalars(
                select(ProjectOptionChoice)
                .where(ProjectOptionChoice.option_group_id == legacy_group.id)
                .order_by(ProjectOptionChoice.display_order, ProjectOptionChoice.id)
            ))
            original_ids = [choice.id for choice in original]
            original_codes = [choice.code for choice in original]
            collision = ProjectOptionChoice(
                option_group_id=legacy_group.id,
                code="legacy-neck-relax-1",
                name="手工维护的无关选项",
                choice_type="preference",
                charge_mode="free",
                display_order=99,
            )
            db.add(collision)
            db.flush()

            project.diy_options = [
                {"label": "NECK RELAX", "price_cents": 0},
                {"label": "Waist", "price_cents": 0},
                {"label": "Ｓｈｏｕｌｄｅｒ　Ｒｅｌａｘ", "price_cents": 0},
                {"label": "shoulder   relax", "price_cents": 0},
            ]
            second = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.flush()
            third = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            db.flush()

            rows = list(db.scalars(select(ProjectOptionChoice).where(
                ProjectOptionChoice.option_group_id == legacy_group.id
            )))
            self.assertEqual(len(rows), 5)
            self.assertEqual(second.created_choices, 1)
            self.assertEqual(third.created_choices, 0)
            self.assertEqual(db.get(ProjectOptionChoice, collision.id).name, "手工维护的无关选项")
            neck = [choice for choice in rows if choice.name == "NECK RELAX"]
            self.assertEqual(len(neck), 1)
            self.assertNotEqual(neck[0].code, collision.code)
            self.assertEqual([db.get(ProjectOptionChoice, choice_id).code for choice_id in original_ids], original_codes)
            self.assertEqual(
                [db.get(ProjectOptionChoice, choice_id).name for choice_id in original_ids],
                ["Ｓｈｏｕｌｄｅｒ　Ｒｅｌａｘ", "Waist", "shoulder   relax"],
            )

    def test_cli_writes_only_with_apply_and_rejects_conflicting_modes(self):
        with patch("scripts.migrate_catalog_options.SessionLocal", self.SessionLocal):
            main(["--store-id", str(self.store_id)])
            main(["--store-id", str(self.store_id), "--dry-run"])
            with self.assertRaises(SystemExit):
                main(["--store-id", str(self.store_id), "--dry-run", "--apply"])

            with self.SessionLocal() as db:
                self.assertEqual(self._count(db, ProjectCatalogVersion), 1)

            main(["--store-id", str(self.store_id), "--apply"])

        with self.SessionLocal() as db:
            self.assertEqual(self._count(db, ProjectCatalogVersion), 2)

    def test_script_file_entrypoint_enforces_real_cli_write_gates(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "migrate_catalog_options.py"
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "catalog-migration.db"
            database_url = f"sqlite:///{database_path.as_posix()}"
            engine = create_engine(database_url, poolclass=NullPool)
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine, expire_on_commit=False)
            with Session() as db:
                store = Store(store_code="subprocess-store", name="子进程测试门店", address="测试地址")
                db.add(store)
                db.flush()
                db.add(Project(
                    store_id=store.id,
                    code="subprocess-project",
                    category="test",
                    name="子进程迁移项目",
                    diy_options=[{"label": "舒缓", "price_cents": 0}],
                ))
                db.commit()
                store_id = store.id
            environment = {**os.environ, "DATABASE_URL": database_url}

            def run(*arguments):
                return subprocess.run(
                    [sys.executable, "-B", str(script), *arguments],
                    cwd=script.parents[1],
                    env=environment,
                    capture_output=True,
                    text=True,
                )

            help_result = run("--help")
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            default_result = run("--store-id", str(store_id))
            self.assertEqual(default_result.returncode, 0, default_result.stderr)
            dry_run_result = run("--store-id", str(store_id), "--dry-run")
            self.assertEqual(dry_run_result.returncode, 0, dry_run_result.stderr)
            conflict_result = run("--store-id", str(store_id), "--dry-run", "--apply")
            self.assertNotEqual(conflict_result.returncode, 0)
            with Session() as db:
                self.assertEqual(self._count(db, ProjectCatalogVersion), 0)

            apply_result = run("--store-id", str(store_id), "--apply")
            self.assertEqual(apply_result.returncode, 0, apply_result.stderr)
            with Session() as db:
                self.assertEqual(self._count(db, ProjectCatalogVersion), 1)
            engine.dispose()

    def test_apply_refuses_nonlocal_target_without_writing_and_redacts_target(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "migrate_catalog_options.py"
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "production-target.db"
            database_url = f"sqlite:///{database_path.as_posix()}"
            engine = create_engine(database_url, poolclass=NullPool)
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine, expire_on_commit=False)
            with Session() as db:
                store = Store(store_code="blocked-apply", name="阻止写入门店", address="测试地址")
                db.add(store)
                db.flush()
                db.add(Project(
                    store_id=store.id,
                    code="blocked-apply-project",
                    category="test",
                    name="阻止写入项目",
                    diy_options=[{"label": "舒缓", "price_cents": 0}],
                ))
                db.commit()
                store_id = store.id
            result = subprocess.run(
                [sys.executable, "-B", str(script), "--store-id", str(store_id), "--apply"],
                cwd=script.parents[1],
                env={**os.environ, "DATABASE_URL": database_url, "ENVIRONMENT": "production"},
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("environment=production", result.stderr)
            self.assertIn("target=sqlite", result.stderr)
            self.assertNotIn(str(database_path), result.stderr)
            with Session() as db:
                self.assertEqual(self._count(db, ProjectCatalogVersion), 0)
            engine.dispose()

    def test_dry_run_and_apply_share_collision_price_replacement_plan(self):
        with self.SessionLocal() as db:
            project = db.get(Project, self.project_id)
            draft = ProjectCatalogVersion(project_id=project.id, version=2, status="draft")
            db.add(draft)
            db.flush()
            # 同编码不同名称迫使迁移器走稳定的替代 group code。
            db.add(ProjectOptionGroup(
                catalog_version_id=draft.id,
                code="legacy-diy-options",
                name="人工冲突组",
                selection_mode="multiple",
                max_select=1,
            ))
            addon_group = ProjectOptionGroup(
                catalog_version_id=draft.id,
                code="legacy-addons",
                name="旧加项（待审核）",
                selection_mode="multiple",
                max_select=1,
            )
            db.add(addon_group)
            db.flush()
            charged = ProjectOptionChoice(
                option_group_id=addon_group.id,
                code="addon-charged-addon",
                name="收费加项",
                choice_type="dedicated_charge",
                charge_mode="custom_price",
            )
            db.add(charged)
            db.flush()
            db.add(OptionChoicePrice(
                option_choice_id=charged.id,
                price_type="store",
                amount_cents=999,
                effective_from=datetime(2020, 1, 1, tzinfo=UTC),
            ))
            db.commit()

            dry = migrate_store_catalog(db, store_id=self.store_id, dry_run=True)
            applied = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)

        self.assertEqual(
            (dry.created_versions, dry.created_groups, dry.created_choices),
            (applied.created_versions, applied.created_groups, applied.created_choices),
        )
        self.assertEqual(len(dry.warnings), len(applied.warnings))
        self.assertTrue(any("group code legacy-diy-options conflicted" in warning for warning in dry.warnings))
        self.assertTrue(any("收费加项" in warning and "replaced" in warning for warning in dry.warnings))

    def test_dry_run_predicts_copy_on_write_contents_without_persisting_them(self):
        with self.SessionLocal() as db:
            project = db.get(Project, self.project_id)
            published = db.get(ProjectCatalogVersion, project.current_published_version_id)
            source_group = ProjectOptionGroup(
                catalog_version_id=published.id,
                code="source-group",
                name="发布源组",
                selection_mode="multiple",
                max_select=1,
            )
            db.add(source_group)
            db.flush()
            db.add(ProjectOptionChoice(
                option_group_id=source_group.id,
                code="source-choice",
                name="发布源选项",
                choice_type="preference",
                charge_mode="free",
            ))
            db.flush()
            published.snapshot_hash = _snapshot_hash(db, published.id)
            db.commit()

            dry = migrate_store_catalog(db, store_id=self.store_id, dry_run=True)
            self.assertEqual(self._count(db, ProjectCatalogVersion), 1)
            applied = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            draft = db.scalar(select(ProjectCatalogVersion).where(
                ProjectCatalogVersion.project_id == project.id,
                ProjectCatalogVersion.status == "draft",
            ))
            copied = db.scalar(select(ProjectOptionChoice)
                .join(ProjectOptionGroup)
                .where(
                    ProjectOptionGroup.catalog_version_id == draft.id,
                    ProjectOptionChoice.code == "source-choice",
                ))

        self.assertEqual(
            (dry.created_versions, dry.created_groups, dry.created_choices),
            (applied.created_versions, applied.created_groups, applied.created_choices),
        )
        self.assertIsNotNone(copied)

    def test_dry_run_predicts_copy_on_write_collision_and_price_replacement_warnings(self):
        with self.SessionLocal() as db:
            project = db.get(Project, self.project_id)
            published = db.get(ProjectCatalogVersion, project.current_published_version_id)
            db.add(ProjectOptionGroup(
                catalog_version_id=published.id,
                code="legacy-diy-options",
                name="人工冲突组",
                selection_mode="multiple",
                max_select=1,
            ))
            addon_group = ProjectOptionGroup(
                catalog_version_id=published.id,
                code="legacy-addons",
                name="旧加项（待审核）",
                selection_mode="multiple",
                max_select=1,
            )
            db.add(addon_group)
            db.flush()
            charged = ProjectOptionChoice(
                option_group_id=addon_group.id,
                code="addon-charged-addon",
                name="收费加项",
                choice_type="dedicated_charge",
                charge_mode="custom_price",
            )
            db.add(charged)
            db.flush()
            db.add(OptionChoicePrice(
                option_choice_id=charged.id,
                price_type="store",
                amount_cents=999,
                effective_from=datetime(2020, 1, 1, tzinfo=UTC),
            ))
            db.flush()
            published.snapshot_hash = _snapshot_hash(db, published.id)
            db.commit()

            dry = migrate_store_catalog(db, store_id=self.store_id, dry_run=True)
            applied = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)

        self.assertEqual(
            (dry.created_versions, dry.created_groups, dry.created_choices),
            (applied.created_versions, applied.created_groups, applied.created_choices),
        )
        self.assertEqual(len(dry.warnings), len(applied.warnings))
        self.assertTrue(any("group code legacy-diy-options conflicted" in warning for warning in dry.warnings))
        self.assertTrue(any("收费加项" in warning and "replaced" in warning for warning in dry.warnings))

    def test_dry_run_audits_malformed_legacy_and_unsafe_addon_prices(self):
        with self.SessionLocal() as db:
            project = db.get(Project, self.project_id)
            project.diy_options = [{"label": "错误金额", "price_cents": "not-a-number"}]
            unsafe = Addon(
                store_id=self.store_id,
                code="unsafe-negative-addon",
                name="负价加项",
                parent_project_id=project.id,
                chargeable=True,
                store_price_cents=-1,
                price_cents=-1,
                publication_status="published",
            )
            db.add(unsafe)
            db.commit()

            report = migrate_store_catalog(db, store_id=self.store_id, dry_run=True)

        self.assertTrue(any("错误金额" in warning and "malformed" in warning for warning in report.warnings))
        self.assertTrue(any("unsafe-negative-addon" in warning and "unsafe" in warning for warning in report.warnings))

    def test_migration_audits_and_skips_addon_with_enabled_missing_member_price(self):
        with self.SessionLocal() as db:
            db.add(Addon(
                store_id=self.store_id,
                code="enabled-missing-member-price",
                name="缺会员价加项",
                parent_project_id=self.project_id,
                chargeable=True,
                store_price_cents=1500,
                member_price_enabled=True,
                member_price_cents=None,
                price_cents=1500,
                publication_status="published",
            ))
            db.commit()

            dry = migrate_store_catalog(db, store_id=self.store_id, dry_run=True)
            applied = migrate_store_catalog(db, store_id=self.store_id, dry_run=False)
            draft = db.scalar(select(ProjectCatalogVersion).where(
                ProjectCatalogVersion.project_id == self.project_id,
                ProjectCatalogVersion.status == "draft",
            ))
            choice = db.scalar(
                select(ProjectOptionChoice)
                .join(ProjectOptionGroup)
                .where(
                    ProjectOptionGroup.catalog_version_id == draft.id,
                    ProjectOptionChoice.code == "addon-enabled-missing-member-price",
                )
            )

        self.assertTrue(any("enabled-missing-member-price" in warning and "member" in warning for warning in dry.warnings))
        self.assertEqual(len(dry.warnings), len(applied.warnings))
        self.assertIsNone(choice)


if __name__ == "__main__":
    unittest.main()
