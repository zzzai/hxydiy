import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
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


if __name__ == "__main__":
    unittest.main()
