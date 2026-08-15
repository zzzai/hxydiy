from datetime import datetime, timezone
import unittest
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.domain.membership_pricing import (
    PriceContext,
    confirmed_price_for_line,
    resolve_option_charge,
)
from app.models import (
    OptionChoicePrice,
    PriceBook,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    Store,
)


class ConfirmedPriceTests(unittest.TestCase):
    def test_non_member_uses_store_price(self):
        price = confirmed_price_for_line(
            prices={"store": 3990, "group": 2990, "member": 2590},
            is_member=False,
            confirmed_at=datetime(2026, 8, 18, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
            store_timezone="Asia/Shanghai",
        )

        self.assertEqual(price.amount_cents, 3990)
        self.assertEqual(price.basis, "store")

    def test_member_price_falls_back_to_group_then_store(self):
        price = confirmed_price_for_line(
            prices={"store": 3990, "group": 2990},
            is_member=True,
            confirmed_at=datetime(2026, 8, 19, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
            store_timezone="Asia/Shanghai",
        )

        self.assertEqual(price.amount_cents, 2990)
        self.assertEqual(price.basis, "member")

    def test_tuesday_member_uses_lower_of_member_and_store_68_percent(self):
        price = confirmed_price_for_line(
            prices={"store": 3990, "member": 2990},
            is_member=True,
            confirmed_at=datetime(2026, 8, 18, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
            store_timezone="Asia/Shanghai",
        )

        self.assertEqual(price.amount_cents, 2713)
        self.assertEqual(price.basis, "tuesday_68")

    def test_tuesday_keeps_member_price_when_it_is_lower_or_equal(self):
        lower = confirmed_price_for_line(
            prices={"store": 3990, "member": 2500},
            is_member=True,
            confirmed_at=datetime(2026, 8, 18, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
            store_timezone="Asia/Shanghai",
        )
        equal = confirmed_price_for_line(
            prices={"store": 4000, "member": 2720},
            is_member=True,
            confirmed_at=datetime(2026, 8, 18, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
            store_timezone="Asia/Shanghai",
        )

        self.assertEqual(lower.amount_cents, 2500)
        self.assertEqual(lower.basis, "member")
        self.assertEqual(equal.amount_cents, 2720)
        self.assertEqual(equal.basis, "member")

    def test_tuesday_is_determined_by_store_timezone_not_system_timezone(self):
        price = confirmed_price_for_line(
            prices={"store": 3990, "member": 2990},
            is_member=True,
            confirmed_at=datetime(2026, 8, 17, 16, 30, tzinfo=timezone.utc),
            store_timezone="Asia/Shanghai",
        )

        self.assertEqual(price.amount_cents, 2713)
        self.assertEqual(price.basis, "tuesday_68")


class OptionChargeTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            store = Store(store_code="option-price-store", name="选项计价门店", address="测试地址")
            root = Project(
                store_id=1,
                code="hxy-root",
                category="bath",
                name="主项目",
                publication_status="published",
            )
            linked = Project(
                store_id=1,
                code="hxy-linked-local",
                category="local-strength",
                name="引用局部",
                publication_status="published",
            )
            db.add_all([store, root, linked])
            db.flush()
            version = ProjectCatalogVersion(project_id=root.id, version=1, status="published")
            db.add(version)
            db.flush()
            group = ProjectOptionGroup(
                catalog_version_id=version.id,
                code="service",
                name="服务选项",
                selection_mode="multiple",
                max_select=3,
            )
            db.add(group)
            db.flush()
            preference = ProjectOptionChoice(
                option_group_id=group.id,
                code="tea",
                name="茶饮",
                choice_type="preference",
                charge_mode="free",
            )
            linked_choice = ProjectOptionChoice(
                option_group_id=group.id,
                code="linked-local",
                name="引用局部",
                choice_type="linked_project",
                linked_project_id=linked.id,
                charge_mode="inherit_linked_price",
                annual_gift_eligible=True,
                qualifies_for_foot_bath_bundle=True,
            )
            dedicated = ProjectOptionChoice(
                option_group_id=group.id,
                code="custom-charge",
                name="自定义收费",
                choice_type="dedicated_charge",
                charge_mode="custom_price",
                annual_gift_eligible=True,
            )
            db.add_all([preference, linked_choice, dedicated])
            db.flush()
            db.add_all([
                PriceBook(project_id=linked.id, price_type="store", amount_cents=6900),
                PriceBook(project_id=linked.id, price_type="group", amount_cents=5900),
                PriceBook(project_id=linked.id, price_type="member", amount_cents=4900),
                OptionChoicePrice(
                    option_choice_id=dedicated.id,
                    price_type="store",
                    amount_cents=3000,
                    effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    effective_to=datetime(2026, 8, 1, tzinfo=timezone.utc),
                ),
                OptionChoicePrice(
                    option_choice_id=dedicated.id,
                    price_type="store",
                    amount_cents=3600,
                    effective_from=datetime(2026, 8, 1, tzinfo=timezone.utc),
                ),
                OptionChoicePrice(
                    option_choice_id=dedicated.id,
                    price_type="group",
                    amount_cents=3200,
                    effective_from=datetime(2026, 8, 1, tzinfo=timezone.utc),
                ),
            ])
            db.commit()
            self.preference_id = preference.id
            self.linked_choice_id = linked_choice.id
            self.dedicated_id = dedicated.id

    def tearDown(self):
        self.engine.dispose()

    def test_preference_choice_is_free_and_not_chargeable(self):
        with self.SessionLocal() as db:
            charge = resolve_option_charge(
                db,
                self.preference_id,
                PriceContext(
                    is_member=True,
                    confirmed_at=datetime(2026, 8, 18, 10, tzinfo=timezone.utc),
                    store_timezone="Asia/Shanghai",
                ),
            )

        self.assertEqual(charge.amount_cents, 0)
        self.assertFalse(charge.chargeable)
        self.assertEqual(charge.price_source, "free")
        self.assertEqual(charge.choice_snapshot["choice_type"], "preference")

    def test_linked_project_inherits_project_price_and_choice_eligibility_snapshot(self):
        with self.SessionLocal() as db:
            charge = resolve_option_charge(
                db,
                self.linked_choice_id,
                PriceContext(
                    is_member=True,
                    confirmed_at=datetime(2026, 8, 18, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
                    store_timezone="Asia/Shanghai",
                ),
            )

        self.assertEqual(charge.amount_cents, 4692)
        self.assertEqual(charge.basis, "tuesday_68")
        self.assertEqual(charge.price_source, "linked_project")
        self.assertEqual(charge.source_ref["price_book_project_id"], charge.choice_snapshot["linked_project_id"])
        self.assertTrue(charge.choice_snapshot["annual_gift_eligible"])
        self.assertTrue(charge.choice_snapshot["qualifies_for_foot_bath_bundle"])

    def test_dedicated_charge_uses_current_effective_choice_price_with_member_fallback(self):
        with self.SessionLocal() as db:
            charge = resolve_option_charge(
                db,
                self.dedicated_id,
                PriceContext(
                    is_member=True,
                    confirmed_at=datetime(2026, 8, 19, 10, tzinfo=timezone.utc),
                    store_timezone="Asia/Shanghai",
                ),
            )

        self.assertEqual(charge.amount_cents, 3200)
        self.assertEqual(charge.basis, "member")
        self.assertEqual(charge.price_source, "option_choice_price")
        self.assertEqual(charge.source_ref["option_choice_id"], self.dedicated_id)

    def test_resolving_option_charge_does_not_consume_annual_gift(self):
        with self.SessionLocal() as db:
            charge = resolve_option_charge(
                db,
                self.dedicated_id,
                PriceContext(
                    is_member=True,
                    confirmed_at=datetime(2026, 8, 19, 10, tzinfo=timezone.utc),
                    store_timezone="Asia/Shanghai",
                ),
            )
            price_rows = db.scalars(select(OptionChoicePrice).where(
                OptionChoicePrice.option_choice_id == self.dedicated_id
            )).all()

        self.assertTrue(charge.choice_snapshot["annual_gift_eligible"])
        self.assertEqual(len(price_rows), 3)


if __name__ == "__main__":
    unittest.main()
