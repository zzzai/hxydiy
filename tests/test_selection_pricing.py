import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.domain.selection_pricing import calculate_selection_pricing
from app.models import PriceBook, Project, Store


class SelectionPricingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            store = Store(store_code="price-store", name="报价测试门店", address="测试地址")
            db.add(store)
            db.flush()
            foot_bath = Project(
                store_id=store.id,
                code="hxy-qiqing-30",
                category="bath",
                name="草本泡脚",
                publication_status="published",
            )
            local = Project(
                store_id=store.id,
                code="hxy-jubu-30",
                category="local-strength",
                name="局部调理",
                publication_status="published",
            )
            db.add_all([foot_bath, local])
            db.flush()
            for project, prices in (
                (foot_bath, {"store": 3990, "group": 2990, "member": 2990}),
                (local, {"store": 6900, "group": 5900, "member": 4900}),
            ):
                db.add_all([
                    PriceBook(project_id=project.id, price_type=price_type, amount_cents=amount)
                    for price_type, amount in prices.items()
                ])
            db.commit()
            self.foot_bath_id = foot_bath.id
            self.local_id = local.id

    def tearDown(self):
        self.engine.dispose()

    def test_member_pricing_uses_member_total_and_preserves_all_price_bands(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {"project_id": self.foot_bath_id, "quantity": 1},
                {"project_id": self.local_id, "quantity": 1, "diy_preferences": ["肩颈"]},
                {"project_id": self.local_id, "quantity": 1, "diy_preferences": ["腰臀"]},
            ], price_type="member")

        # 两项局部调理：泡脚费按各价格带全额减免。
        self.assertEqual(pricing["store_total_cents"], 13800)
        self.assertEqual(pricing["group_total_cents"], 11800)
        self.assertEqual(pricing["member_total_cents"], 9800)
        self.assertEqual(pricing["applied_price_type"], "member")
        self.assertEqual(pricing["payable_total_cents"], 9800)
        self.assertEqual(pricing["lines"][1]["unit_group_price_cents"], 5900)
        self.assertEqual(pricing["lines"][1]["unit_payable_price_cents"], 4900)
        self.assertEqual(pricing["promotion_code"], "FOOT_BATH_TWO_LOCAL")
        self.assertEqual(pricing["promotion_adjustment_cents"], -2990)

    def test_foot_bath_promotion_waives_full_store_price_for_non_member(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {"project_id": self.foot_bath_id, "quantity": 1},
                {"project_id": self.local_id, "quantity": 1, "diy_preferences": ["肩颈"]},
                {"project_id": self.local_id, "quantity": 1, "diy_preferences": ["足部"]},
            ])

        self.assertEqual(pricing["applied_price_type"], "store")
        # 门店价：泡脚 3990 全免，两部位 6900×2。
        self.assertEqual(pricing["payable_total_cents"], 13800)
        self.assertEqual(pricing["store_total_cents"], 13800)

    def test_single_local_part_does_not_waive_foot_bath(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {"project_id": self.foot_bath_id, "quantity": 1},
                {"project_id": self.local_id, "quantity": 1, "diy_preferences": ["肩颈"]},
            ])

        self.assertEqual(pricing["promotion_code"], "")
        self.assertEqual(pricing["payable_total_cents"], 3990 + 6900)

    def test_store_pricing_is_the_default_for_non_member(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {"project_id": self.local_id, "quantity": 1, "diy_preferences": ["肩颈"]},
            ])

        self.assertEqual(pricing["applied_price_type"], "store")
        self.assertEqual(pricing["payable_total_cents"], 6900)

    def test_member_price_falls_back_to_group_then_store(self):
        # 只有 store+group 价的项目：会员价应回退到团购价（与顾客端预览一致）。
        with self.SessionLocal() as db:
            project = Project(
                store_id=1, code="hxy-no-member-price", category="bath",
                name="缺会员价项目", publication_status="published",
            )
            db.add(project)
            db.flush()
            db.add_all([
                PriceBook(project_id=project.id, price_type="store", amount_cents=3990),
                PriceBook(project_id=project.id, price_type="group", amount_cents=2990),
            ])
            db.commit()
            pricing = calculate_selection_pricing(db, [
                {"project_id": project.id, "quantity": 1},
            ], price_type="member")

        self.assertEqual(pricing["member_total_cents"], 2990)
        self.assertEqual(pricing["payable_total_cents"], 2990)

    def test_foot_bath_promotion_waives_only_base_price_not_addons(self):
        from app.models import Addon
        with self.SessionLocal() as db:
            addon = Addon(
                store_id=1, code="hxy-addon-test", name="加选小项",
                price_cents=2000, chargeable=True, publication_status="published",
                parent_project_id=self.foot_bath_id, can_attach_to_parent=True,
            )
            db.add(addon)
            db.commit()
            # 泡脚(3990) + 加选小项(2000) + 两个局部(6900×2)：减免只免泡脚基础价 3990。
            pricing = calculate_selection_pricing(db, [
                {"project_id": self.foot_bath_id, "quantity": 1, "addon_ids": [addon.id]},
                {"project_id": self.local_id, "quantity": 1, "diy_preferences": ["肩颈"]},
                {"project_id": self.local_id, "quantity": 1, "diy_preferences": ["腿部"]},
            ])

        self.assertEqual(pricing["promotion_code"], "FOOT_BATH_TWO_LOCAL")
        self.assertEqual(pricing["payable_total_cents"], 2000 + 6900 + 6900)

    def test_foot_bath_bundle_matches_every_two_qualified_local_units(self):
        cases = [
            (0, 0),
            (1, 0),
            (2, -3990),
            (3, -3990),
            (4, -7980),
        ]
        for local_count, adjustment in cases:
            with self.subTest(local_count=local_count):
                items = [
                    {
                        "project_id": self.foot_bath_id,
                        "code": "hxy-qiqing-30",
                        "quantity": 2,
                        "chargeable": True,
                    },
                ]
                items.extend(
                    {
                        "project_id": self.local_id,
                        "code": "hxy-jubu-30",
                        "quantity": 1,
                        "diy_preferences": [f"部位{index}"],
                        "chargeable": True,
                        "qualifies_for_foot_bath_bundle": True,
                    }
                    for index in range(local_count)
                )

                with self.SessionLocal() as db:
                    pricing = calculate_selection_pricing(db, items)

                self.assertEqual(pricing["promotion_adjustment_cents"], adjustment)

    def test_foot_bath_bundle_counts_repeated_part_when_snapshot_is_explicitly_qualified(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {"project_id": self.foot_bath_id, "quantity": 1, "chargeable": True},
                {
                    "project_id": self.local_id,
                    "quantity": 1,
                    "diy_preferences": ["肩颈"],
                    "chargeable": True,
                    "qualifies_for_foot_bath_bundle": True,
                },
                {
                    "project_id": self.local_id,
                    "quantity": 1,
                    "diy_preferences": ["肩颈"],
                    "chargeable": True,
                    "qualifies_for_foot_bath_bundle": True,
                },
            ])

        self.assertEqual(pricing["promotion_adjustment_cents"], -3990)

    def test_foot_bath_bundle_excludes_unconfirmed_free_and_annual_gift_lines(self):
        items = [
            {"project_id": self.foot_bath_id, "quantity": 1, "chargeable": True},
            {
                "project_id": self.local_id,
                "quantity": 1,
                "state": "pending",
                "diy_preferences": ["肩颈"],
                "chargeable": True,
                "qualifies_for_foot_bath_bundle": True,
            },
            {
                "project_id": self.local_id,
                "quantity": 1,
                "item_type": "preference",
                "diy_preferences": ["腰背"],
                "chargeable": True,
                "qualifies_for_foot_bath_bundle": True,
            },
            {
                "project_id": self.local_id,
                "quantity": 1,
                "diy_preferences": ["腿部"],
                "chargeable": False,
                "qualifies_for_foot_bath_bundle": True,
            },
            {
                "project_id": self.local_id,
                "quantity": 1,
                "diy_preferences": ["腹部"],
                "chargeable": True,
                "price_basis": "annual_gift",
                "qualifies_for_foot_bath_bundle": True,
            },
            {
                "project_id": self.local_id,
                "quantity": 1,
                "diy_preferences": ["足部"],
                "chargeable": True,
                "qualifies_for_foot_bath_bundle": True,
            },
        ]
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, items)

        self.assertEqual(pricing["promotion_adjustment_cents"], 0)

    def test_foot_bath_bundle_keeps_legacy_missing_state_preview_compatible(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {"project_id": self.foot_bath_id, "quantity": 1, "chargeable": True},
                {
                    "project_id": self.local_id,
                    "quantity": 1,
                    "diy_preferences": ["肩颈"],
                    "chargeable": True,
                },
                {
                    "project_id": self.local_id,
                    "quantity": 1,
                    "diy_preferences": ["腰背"],
                    "chargeable": True,
                },
            ])

        self.assertEqual(pricing["promotion_adjustment_cents"], -3990)


if __name__ == "__main__":
    unittest.main()
