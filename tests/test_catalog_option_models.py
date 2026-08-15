import unittest
from datetime import UTC, datetime

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import (
    CHARGE_MODES,
    CHOICE_TYPES,
    OptionChoicePrice,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    Store,
)
from catalog_option_fixtures import make_catalog_version, make_option_group, make_two_linked_projects


class CatalogOptionModelTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def tearDown(self):
        self.engine.dispose()

    def test_catalog_option_choice_requires_valid_charge_mode(self):
        with self.SessionLocal() as db:
            version = make_catalog_version(db, project_code="catalog-option-project")
            group = make_option_group(db, version.id, code="strength")
            db.add(ProjectOptionChoice(
                option_group_id=group.id,
                code="medium",
                name="适中",
                choice_type="preference",
                charge_mode="free",
            ))
            db.commit()

            self.assertEqual(
                db.scalar(select(func.count()).select_from(ProjectOptionChoice)),
                1,
            )

    def test_catalog_option_models_persist_complete_fields_and_defaults(self):
        effective_from = datetime(2026, 8, 15, tzinfo=UTC)
        with self.SessionLocal() as db:
            version = make_catalog_version(db, project_code="complete-fields")
            group = make_option_group(db, version.id, code="area")
            linked_project, _ = make_two_linked_projects(db, prefix="complete-linked")
            choice = ProjectOptionChoice(
                option_group_id=group.id,
                code="shoulder",
                name="肩颈",
                description="肩颈区域",
                choice_type="linked_project",
                linked_project_id=linked_project.id,
                charge_mode="inherit_linked_price",
                independently_visible=False,
                coupon_eligible=True,
                annual_gift_eligible=True,
                qualifies_for_foot_bath_bundle=True,
                display_order=3,
                status="active",
            )
            db.add(choice)
            db.flush()
            price = OptionChoicePrice(
                option_choice_id=choice.id,
                price_type="member",
                amount_cents=4900,
                effective_from=effective_from,
            )
            db.add(price)
            db.commit()

            self.assertEqual(version.snapshot_hash, "")
            self.assertIsNone(version.published_at)
            self.assertIsNone(version.published_by)
            self.assertEqual(group.description, "")
            self.assertEqual(group.selection_mode, "single")
            self.assertFalse(group.required)
            self.assertEqual(group.min_select, 0)
            self.assertEqual(group.max_select, 1)
            self.assertEqual(group.display_order, 0)
            self.assertEqual(choice.linked_project_id, linked_project.id)
            self.assertTrue(choice.coupon_eligible)
            self.assertTrue(choice.annual_gift_eligible)
            self.assertTrue(choice.qualifies_for_foot_bath_bundle)
            self.assertEqual(price.amount_cents, 4900)
            self.assertIsNone(price.effective_to)

    def test_choice_type_and_charge_mode_constants_are_complete(self):
        self.assertEqual(
            CHOICE_TYPES,
            {"preference", "linked_project", "dedicated_charge"},
        )
        self.assertEqual(
            CHARGE_MODES,
            {"free", "inherit_linked_price", "custom_price"},
        )

    def test_invalid_choice_type_and_charge_mode_are_rejected(self):
        for field, value in (("choice_type", "unknown"), ("charge_mode", "unknown")):
            with self.subTest(field=field):
                with self.SessionLocal() as db:
                    version = make_catalog_version(db, project_code=f"invalid-{field}")
                    group = make_option_group(db, version.id, code="strength")
                    values = {
                        "option_group_id": group.id,
                        "code": "medium",
                        "name": "适中",
                        "choice_type": "preference",
                        "charge_mode": "free",
                    }
                    values[field] = value
                    db.add(ProjectOptionChoice(**values))

                    with self.assertRaises(IntegrityError):
                        db.commit()

    def test_catalog_version_is_unique_per_project_and_version_number(self):
        with self.SessionLocal() as db:
            version = make_catalog_version(db, project_code="version-unique")
            db.commit()
            db.add(ProjectCatalogVersion(project_id=version.project_id, version=1))

            with self.assertRaises(IntegrityError):
                db.commit()

    def test_catalog_version_rejects_invalid_status(self):
        with self.SessionLocal() as db:
            version = make_catalog_version(db, project_code="invalid-version-status")
            db.commit()
            db.add(ProjectCatalogVersion(
                project_id=version.project_id,
                version=2,
                status="retired",
            ))

            with self.assertRaises(IntegrityError):
                db.commit()

    def test_catalog_version_allows_only_one_active_draft_and_published_version_per_project(self):
        with self.SessionLocal() as db:
            draft = make_catalog_version(db, project_code="one-active-draft")
            db.commit()
            db.add(ProjectCatalogVersion(
                project_id=draft.project_id,
                version=2,
                status="draft",
            ))

            with self.assertRaises(IntegrityError):
                db.commit()

    def test_current_published_pointer_must_belong_to_its_project(self):
        with self.SessionLocal() as db:
            db.execute(text("PRAGMA foreign_keys = ON"))
            store = Store(store_code="pointer-store", name="指针门店", address="测试地址")
            db.add(store)
            db.flush()
            first = Project(
                store_id=store.id,
                code="pointer-first",
                category="test",
                name="项目一",
            )
            second = Project(
                store_id=store.id,
                code="pointer-second",
                category="test",
                name="项目二",
            )
            db.add_all([first, second])
            db.flush()
            first_version = ProjectCatalogVersion(project_id=first.id, version=1, status="published")
            second_version = ProjectCatalogVersion(project_id=second.id, version=1, status="published")
            db.add_all([first_version, second_version])
            db.flush()
            first.current_published_version_id = second_version.id

            with self.assertRaises(IntegrityError):
                db.commit()

        with self.SessionLocal() as db:
            first = make_catalog_version(db, project_code="one-active-published")
            first.status = "published"
            db.commit()
            db.add(ProjectCatalogVersion(
                project_id=first.project_id,
                version=2,
                status="published",
            ))

            with self.assertRaises(IntegrityError):
                db.commit()

    def test_option_choice_price_rejects_negative_amount_and_invalid_interval(self):
        effective_from = datetime(2026, 8, 15, tzinfo=UTC)
        with self.SessionLocal() as db:
            version = make_catalog_version(db, project_code="price-checks")
            group = make_option_group(db, version.id, code="upgrade")
            choice = ProjectOptionChoice(
                option_group_id=group.id,
                code="hot-pack",
                name="热敷包",
                choice_type="dedicated_charge",
                charge_mode="custom_price",
            )
            db.add(choice)
            db.flush()
            db.add(OptionChoicePrice(
                option_choice_id=choice.id,
                price_type="store",
                amount_cents=-1,
                effective_from=effective_from,
            ))

            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

            db.add(OptionChoicePrice(
                option_choice_id=choice.id,
                price_type="store",
                amount_cents=100,
                effective_from=effective_from,
                effective_to=effective_from,
            ))
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_option_group_code_is_unique_within_catalog_version(self):
        with self.SessionLocal() as db:
            version = make_catalog_version(db, project_code="group-unique")
            make_option_group(db, version.id, code="strength")
            db.commit()
            db.add(ProjectOptionGroup(catalog_version_id=version.id, code="strength", name="力度"))

            with self.assertRaises(IntegrityError):
                db.commit()

    def test_option_choice_code_is_unique_within_group(self):
        with self.SessionLocal() as db:
            version = make_catalog_version(db, project_code="choice-unique")
            group = make_option_group(db, version.id, code="strength")
            db.add(ProjectOptionChoice(
                option_group_id=group.id,
                code="medium",
                name="适中",
                choice_type="preference",
                charge_mode="free",
            ))
            db.commit()
            db.add(ProjectOptionChoice(
                option_group_id=group.id,
                code="medium",
                name="另一个适中",
                choice_type="preference",
                charge_mode="free",
            ))

            with self.assertRaises(IntegrityError):
                db.commit()

    def test_option_choice_price_is_unique_per_type_and_effective_start(self):
        effective_from = datetime(2026, 8, 15, tzinfo=UTC)
        with self.SessionLocal() as db:
            version = make_catalog_version(db, project_code="price-unique")
            group = make_option_group(db, version.id, code="strength")
            choice = ProjectOptionChoice(
                option_group_id=group.id,
                code="medium",
                name="适中",
                choice_type="dedicated_charge",
                charge_mode="custom_price",
            )
            db.add(choice)
            db.flush()
            db.add(OptionChoicePrice(
                option_choice_id=choice.id,
                price_type="store",
                amount_cents=1000,
                effective_from=effective_from,
            ))
            db.commit()
            db.add(OptionChoicePrice(
                option_choice_id=choice.id,
                price_type="store",
                amount_cents=1200,
                effective_from=effective_from,
            ))

            with self.assertRaises(IntegrityError):
                db.commit()


if __name__ == "__main__":
    unittest.main()
