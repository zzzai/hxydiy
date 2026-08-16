import unittest
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.domain.membership_pricing import PriceContext
from app.domain.selection_pricing import calculate_selection_pricing, price_type_for_member
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
            standard = Project(
                store_id=store.id,
                code="hxy-xiangxiang-60",
                category="bath",
                name="草本沐足",
                publication_status="published",
            )
            signature = Project(
                store_id=store.id,
                code="hxy-xiaoqi-90",
                category="bath",
                name="招牌草本沐足",
                publication_status="published",
            )
            db.add_all([foot_bath, local, standard, signature])
            db.flush()
            for project, prices in (
                (foot_bath, {"store": 3990, "group": 2990, "member": 2990}),
                (local, {"store": 6900, "group": 5900, "member": 4900}),
                (standard, {"store": 7990, "group": 6990, "member": 5990}),
                (signature, {"store": 9990, "group": 8990, "member": 7990}),
            ):
                db.add_all([
                    PriceBook(project_id=project.id, price_type=price_type, amount_cents=amount)
                    for price_type, amount in prices.items()
                ])
            version = ProjectCatalogVersion(project_id=foot_bath.id, version=1, status="published")
            db.add(version)
            db.flush()
            group = ProjectOptionGroup(
                catalog_version_id=version.id,
                code="upgrade",
                name="升级选项",
                selection_mode="multiple",
                max_select=2,
            )
            db.add(group)
            db.flush()
            preference = ProjectOptionChoice(
                option_group_id=group.id,
                code="free-preference",
                name="免费偏好",
                choice_type="preference",
                charge_mode="free",
            )
            dedicated = ProjectOptionChoice(
                option_group_id=group.id,
                code="dedicated-upgrade",
                name="专属升级",
                choice_type="dedicated_charge",
                charge_mode="custom_price",
                coupon_eligible=True,
            )
            db.add_all([preference, dedicated])
            db.flush()
            db.add_all([
                OptionChoicePrice(
                    option_choice_id=dedicated.id,
                    price_type="store",
                    amount_cents=3000,
                    effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                ),
                OptionChoicePrice(
                    option_choice_id=dedicated.id,
                    price_type="group",
                    amount_cents=2700,
                    effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                ),
                OptionChoicePrice(
                    option_choice_id=dedicated.id,
                    price_type="member",
                    amount_cents=2400,
                    effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                ),
            ])
            db.commit()
            self.foot_bath_id = foot_bath.id
            self.local_id = local.id
            self.standard_id = standard.id
            self.signature_id = signature.id
            self.preference_id = preference.id
            self.dedicated_id = dedicated.id

    def tearDown(self):
        self.engine.dispose()

    def test_legacy_annual_member_without_expiry_uses_store_price_type(self):
        self.assertEqual(
            price_type_for_member(
                True,
                confirmed_at=datetime(2027, 8, 1, tzinfo=UTC),
                member_type="annual",
            ),
            "store",
        )

    def test_member_pricing_uses_member_total_and_preserves_all_price_bands(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {"project_id": self.foot_bath_id, "quantity": 1, "state": "confirmed"},
                {"project_id": self.local_id, "quantity": 1, "state": "confirmed", "diy_preferences": ["肩颈"]},
                {"project_id": self.local_id, "quantity": 1, "state": "confirmed", "diy_preferences": ["腰臀"]},
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

    def test_two_local_choices_only_waive_entry_foot_bath(self):
        def price(project_id: int) -> dict:
            with self.SessionLocal() as db:
                return calculate_selection_pricing(db, [
                    {"project_id": project_id, "state": "confirmed"},
                    {
                        "project_id": self.local_id,
                        "state": "confirmed",
                        "body_part": "肩颈",
                        "qualifies_for_foot_bath_bundle": True,
                    },
                    {
                        "project_id": self.local_id,
                        "state": "confirmed",
                        "body_part": "腰臀",
                        "qualifies_for_foot_bath_bundle": True,
                    },
                ], "store")

        entry = price(self.foot_bath_id)
        standard = price(self.standard_id)
        signature = price(self.signature_id)

        self.assertEqual(entry["promotion_adjustment_cents"], -3990)
        self.assertEqual(standard["promotion_adjustment_cents"], 0)
        self.assertEqual(signature["promotion_adjustment_cents"], 0)

    def test_non_entry_projects_cannot_spoof_entry_promotion_code(self):
        for project_id in (self.standard_id, self.signature_id):
            with self.subTest(project_id=project_id), self.SessionLocal() as db:
                pricing = calculate_selection_pricing(db, [
                    {
                        "project_id": project_id,
                        "code": "hxy-qiqing-30",
                        "state": "confirmed",
                    },
                    {
                        "project_id": self.local_id,
                        "state": "confirmed",
                        "body_part": "肩颈",
                        "qualifies_for_foot_bath_bundle": True,
                    },
                    {
                        "project_id": self.local_id,
                        "state": "confirmed",
                        "body_part": "腰臀",
                        "qualifies_for_foot_bath_bundle": True,
                    },
                ], "store")

                self.assertEqual(pricing["promotion_adjustment_cents"], 0)
                self.assertEqual(pricing["matched_foot_bath_count"], 0)

    def test_dedicated_choice_uses_database_price_bands_and_freezes_member_confirmation(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(
                db,
                [{
                    "project_id": None,
                    "option_choice_id": self.dedicated_id,
                    "item_kind": "dedicated_option",
                    "chargeable": True,
                    "unit_store_price_cents": 1,
                    "unit_member_price_cents": 1,
                }],
                "member",
                price_context=PriceContext(
                    is_member=True,
                    member_type="annual",
                    member_expire_at=datetime(2027, 8, 19, tzinfo=UTC),
                    confirmed_at=datetime(2026, 8, 19, 2, tzinfo=UTC),
                    store_timezone="Asia/Shanghai",
                    store_id=1,
                ),
            )

        line = pricing["lines"][0]
        self.assertEqual(line["unit_store_price_cents"], 3000)
        self.assertEqual(line["unit_group_price_cents"], 2700)
        self.assertEqual(line["unit_member_price_cents"], 2400)
        self.assertEqual(line["unit_payable_price_cents"], 2400)
        self.assertEqual(line["price_basis"], "member")
        self.assertEqual(line["resolved_charge"]["amount_cents"], 2400)
        self.assertEqual(line["resolved_charge"]["source_ref"]["option_choice_id"], self.dedicated_id)

    def test_dedicated_choice_tuesday_price_is_only_for_active_annual_member(self):
        contexts = [
            ("annual", 2040, "tuesday_68"),
            ("stored", 2400, "member"),
        ]
        for member_type, expected_amount, expected_basis in contexts:
            with self.subTest(member_type=member_type), self.SessionLocal() as db:
                pricing = calculate_selection_pricing(
                    db,
                    [{
                        "project_id": None,
                        "option_choice_id": self.dedicated_id,
                        "item_kind": "dedicated_option",
                        "chargeable": True,
                    }],
                    "member",
                    price_context=PriceContext(
                        is_member=True,
                        member_type=member_type,
                        member_expire_at=datetime(2027, 8, 18, tzinfo=UTC),
                        confirmed_at=datetime(2026, 8, 18, 2, tzinfo=UTC),
                        store_timezone="Asia/Shanghai",
                        store_id=1,
                    ),
                )

                self.assertEqual(pricing["lines"][0]["unit_payable_price_cents"], expected_amount)
                self.assertEqual(pricing["lines"][0]["price_basis"], expected_basis)

    def test_dedicated_choice_ignores_client_free_flags_before_database_resolution(self):
        variants = [
            {"chargeable": False},
            {"item_type": "preference"},
        ]
        for client_fields in variants:
            with self.subTest(client_fields=client_fields), self.SessionLocal() as db:
                pricing = calculate_selection_pricing(
                    db,
                    [{
                        "project_id": None,
                        "option_choice_id": self.dedicated_id,
                        "item_kind": "dedicated_option",
                        **client_fields,
                    }],
                    "member",
                    price_context=PriceContext(
                        is_member=True,
                        member_type="stored",
                        member_expire_at=datetime(2027, 8, 19, tzinfo=UTC),
                        confirmed_at=datetime(2026, 8, 19, 2, tzinfo=UTC),
                        store_timezone="Asia/Shanghai",
                        store_id=1,
                    ),
                )

                self.assertEqual(len(pricing["lines"]), 1)
                self.assertEqual(pricing["lines"][0]["unit_payable_price_cents"], 2400)
                self.assertEqual(pricing["payable_total_cents"], 2400)

    def test_preference_option_choice_never_creates_a_charge_line(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(
                db,
                [{
                    "project_id": None,
                    "option_choice_id": self.preference_id,
                    "item_kind": "dedicated_option",
                    "chargeable": True,
                }],
                "store",
                price_context=PriceContext(
                    is_member=False,
                    confirmed_at=datetime(2026, 8, 19, 2, tzinfo=UTC),
                    store_timezone="Asia/Shanghai",
                    store_id=1,
                ),
            )

        self.assertEqual(pricing["lines"], [])
        self.assertEqual(pricing["payable_total_cents"], 0)

    def test_tuesday_confirmation_uses_68_percent_store_price_for_active_annual_member(self):
        with self.SessionLocal() as db:
            project = Project(
                store_id=1,
                code="hxy-tuesday-price",
                category="care",
                name="周二会员价项目",
                publication_status="published",
            )
            db.add(project)
            db.flush()
            db.add_all([
                PriceBook(project_id=project.id, price_type="store", amount_cents=10000),
                PriceBook(project_id=project.id, price_type="group", amount_cents=9000),
                PriceBook(project_id=project.id, price_type="member", amount_cents=8000),
            ])
            db.commit()

            pricing = calculate_selection_pricing(
                db,
                [{"project_id": project.id, "quantity": 1, "state": "confirmed"}],
                "member",
                price_context=PriceContext(
                    is_member=True,
                    member_type="annual",
                    member_expire_at=datetime(2027, 8, 18, tzinfo=UTC),
                    confirmed_at=datetime(2026, 8, 18, 2, 0, tzinfo=UTC),
                    store_timezone="Asia/Shanghai",
                ),
            )

        self.assertEqual(pricing["lines"][0]["price_basis"], "tuesday_68")
        self.assertEqual(pricing["lines"][0]["unit_payable_price_cents"], 6800)
        self.assertEqual(pricing["lines"][0]["payable_line_total_cents"], 6800)
        self.assertEqual(pricing["payable_total_cents"], 6800)

    def test_tuesday_foot_bath_promotion_waives_confirmed_base_but_not_addon(self):
        with self.SessionLocal() as db:
            addon = Addon(
                store_id=1,
                code="hxy-addon-tuesday",
                name="周二泡脚加项",
                price_cents=2000,
                chargeable=True,
                publication_status="published",
                parent_project_id=self.foot_bath_id,
                can_attach_to_parent=True,
            )
            db.add(addon)
            db.commit()
            pricing = calculate_selection_pricing(
                db,
                [
                    {
                        "project_id": self.foot_bath_id,
                        "quantity": 1,
                        "state": "confirmed",
                        "addon_ids": [addon.id],
                    },
                    {
                        "project_id": self.local_id,
                        "quantity": 1,
                        "state": "confirmed",
                        "diy_preferences": ["肩颈"],
                    },
                    {
                        "project_id": self.local_id,
                        "quantity": 1,
                        "state": "confirmed",
                        "diy_preferences": ["腿部"],
                    },
                ],
                "member",
                price_context=PriceContext(
                    is_member=True,
                    member_type="annual",
                    member_expire_at=datetime(2027, 8, 18, tzinfo=UTC),
                    confirmed_at=datetime(2026, 8, 18, 2, 0, tzinfo=UTC),
                    store_timezone="Asia/Shanghai",
                ),
            )

        # 泡脚+addon 周二确认价 4073；两个局部各 4692；只免泡脚基础周二确认价 2713。
        self.assertEqual(pricing["lines"][0]["price_basis"], "tuesday_68")
        self.assertEqual(pricing["lines"][0]["unit_payable_price_cents"], 4073)
        self.assertEqual(pricing["promotion_adjustment_cents"], -2713)
        self.assertEqual(pricing["payable_total_cents"], 10744)

    def test_foot_bath_promotion_waives_full_store_price_for_non_member(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {"project_id": self.foot_bath_id, "quantity": 1, "state": "confirmed"},
                {"project_id": self.local_id, "quantity": 1, "state": "confirmed", "diy_preferences": ["肩颈"]},
                {"project_id": self.local_id, "quantity": 1, "state": "confirmed", "diy_preferences": ["足部"]},
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
                {"project_id": self.foot_bath_id, "quantity": 1, "state": "confirmed", "addon_ids": [addon.id]},
                {"project_id": self.local_id, "quantity": 1, "state": "confirmed", "diy_preferences": ["肩颈"]},
                {"project_id": self.local_id, "quantity": 1, "state": "confirmed", "diy_preferences": ["腿部"]},
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
                        "service_line_id": f"foot-{unit}",
                        "state": "confirmed",
                        "chargeable": True,
                    }
                    for unit in range(2)
                ]
                items.extend(
                    {
                        "project_id": self.local_id,
                        "code": "hxy-jubu-30",
                        "quantity": 1,
                        "state": "confirmed",
                        "diy_preferences": [f"部位{index}"],
                        "chargeable": True,
                        "qualifies_for_foot_bath_bundle": True,
                    }
                    for index in range(local_count)
                )

                with self.SessionLocal() as db:
                    pricing = calculate_selection_pricing(db, items)

                self.assertEqual(pricing["promotion_adjustment_cents"], adjustment)

    def test_foot_bath_bundle_does_not_count_repeated_same_part_even_when_explicitly_qualified(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {"project_id": self.foot_bath_id, "quantity": 1, "state": "confirmed", "chargeable": True},
                {
                    "project_id": self.local_id,
                    "quantity": 1,
                    "state": "confirmed",
                    "diy_preferences": ["肩颈"],
                    "chargeable": True,
                    "qualifies_for_foot_bath_bundle": True,
                },
                {
                    "project_id": self.local_id,
                    "quantity": 1,
                    "state": "confirmed",
                    "diy_preferences": ["肩颈"],
                    "chargeable": True,
                    "qualifies_for_foot_bath_bundle": True,
                },
            ])

        self.assertEqual(pricing["promotion_adjustment_cents"], 0)

    def test_foot_bath_bundle_excludes_unconfirmed_free_and_annual_gift_lines(self):
        items = [
            {"project_id": self.foot_bath_id, "quantity": 1, "state": "confirmed", "chargeable": True},
            {
                "project_id": self.local_id,
                "quantity": 1,
                "state": "awaiting_staff_confirmation",
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

    def test_invalid_state_foot_bath_does_not_receive_bundle_discount(self):
        items = [
            {
                "project_id": self.foot_bath_id,
                "quantity": 1,
                "state": "cancelled",
                "chargeable": True,
            },
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
                "state": "completed",
                "diy_preferences": ["腰背"],
                "chargeable": True,
                "qualifies_for_foot_bath_bundle": True,
            },
        ]
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, items)

        self.assertEqual(pricing["promotion_adjustment_cents"], 0)
        self.assertEqual(pricing["qualified_local_unit_count"], 0)
        self.assertEqual(pricing["matched_foot_bath_count"], 0)

    def test_pending_or_completed_service_lines_do_not_count_for_foot_bath_bundle(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {"project_id": self.foot_bath_id, "quantity": 1, "state": "confirmed", "chargeable": True},
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
                    "state": "completed",
                    "diy_preferences": ["腰背"],
                    "chargeable": True,
                    "qualifies_for_foot_bath_bundle": True,
                },
            ])

        self.assertEqual(pricing["promotion_adjustment_cents"], 0)

    def test_foot_bath_bundle_reads_nested_snapshots_and_confirmed_base_price(self):
        from app.models import Addon
        with self.SessionLocal() as db:
            addon = Addon(
                store_id=1,
                code="hxy-addon-nested",
                name="加选小项",
                price_cents=2000,
                chargeable=True,
                publication_status="published",
                parent_project_id=self.foot_bath_id,
                can_attach_to_parent=True,
            )
            db.add(addon)
            db.commit()
            pricing = calculate_selection_pricing(db, [
                {
                    "project_id": self.foot_bath_id,
                    "quantity": 1,
                    "state": "confirmed",
                    "addon_ids": [addon.id],
                    "snapshot": {
                        "code": "hxy-qiqing-30",
                        "resolved_charge": {"confirmed_base_price_cents": 2713},
                    },
                },
                {
                    "project_id": self.local_id,
                    "quantity": 1,
                    "snapshot": {
                        "state": "confirmed",
                        "diy_preferences": ["肩颈"],
                        "resolved_charge": {
                            "choice_snapshot": {
                                "code": "hxy-jubu-30",
                                "qualifies_for_foot_bath_bundle": True,
                            }
                        },
                    },
                },
                {
                    "project_id": self.local_id,
                    "quantity": 1,
                    "snapshot": {
                        "state": "confirmed",
                        "choice_snapshot": {
                            "code": "hxy-jubu-30",
                            "qualifies_for_foot_bath_bundle": True,
                        },
                        "diy_preferences": ["腰背"],
                    },
                },
            ])

        self.assertEqual(pricing["promotion_adjustment_cents"], -2713)
        self.assertEqual(pricing["payable_total_cents"], 3990 + 2000 + 6900 + 6900 - 2713)

    def test_foot_bath_bundle_uses_confirmed_base_price_per_matched_foot_bath(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {
                    "project_id": self.foot_bath_id,
                    "quantity": 1,
                    "state": "confirmed",
                    "confirmed_base_price_cents": 2713,
                    "chargeable": True,
                },
                {"project_id": self.foot_bath_id, "quantity": 1, "state": "confirmed", "chargeable": True},
                *[
                    {
                        "project_id": self.local_id,
                        "quantity": 1,
                        "state": "confirmed",
                        "diy_preferences": [f"部位{index}"],
                        "chargeable": True,
                        "qualifies_for_foot_bath_bundle": True,
                    }
                    for index in range(4)
                ],
            ])

        self.assertEqual(pricing["promotion_adjustment_cents"], -(2713 + 3990))

    def test_foot_bath_bundle_requires_confirmed_state_for_legacy_preview_rows(self):
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

        self.assertEqual(pricing["promotion_adjustment_cents"], 0)

    def test_foot_bath_bundle_uses_one_unit_per_service_line_not_quantity_or_duplicate_id(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {
                    "project_id": self.foot_bath_id,
                    "code": "hxy-qiqing-30",
                    "quantity": 2,
                    "service_line_id": "foot-1",
                    "state": "confirmed",
                    "chargeable": True,
                },
                {
                    "project_id": self.local_id,
                    "code": "hxy-jubu-30",
                    "quantity": 3,
                    "service_line_id": "local-shoulder",
                    "state": "confirmed",
                    "qualifies_for_foot_bath_bundle": True,
                    "body_part": "肩颈",
                    "chargeable": True,
                },
                {
                    "project_id": self.local_id,
                    "code": "hxy-jubu-30",
                    "quantity": 1,
                    "service_line_id": "local-waist",
                    "state": "confirmed",
                    "qualifies_for_foot_bath_bundle": True,
                    "body_part": "腰背",
                    "chargeable": True,
                },
                {
                    "project_id": self.local_id,
                    "code": "hxy-jubu-30",
                    "quantity": 1,
                    "service_line_id": "local-waist",
                    "state": "confirmed",
                    "qualifies_for_foot_bath_bundle": True,
                    "body_part": "腿部",
                    "chargeable": True,
                },
            ])

        self.assertEqual(pricing["qualified_local_unit_count"], 2)
        self.assertEqual(pricing["matched_foot_bath_count"], 1)
        self.assertEqual(pricing["promotion_adjustment_cents"], -3990)

    def test_same_local_project_requires_distinct_normalized_non_empty_parts(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {
                    "project_id": self.foot_bath_id,
                    "code": "hxy-qiqing-30",
                    "service_line_id": "foot-1",
                    "state": "confirmed",
                    "chargeable": True,
                },
                {
                    "project_id": self.local_id,
                    "code": "hxy-jubu-30",
                    "service_line_id": "local-a",
                    "state": "confirmed",
                    "qualifies_for_foot_bath_bundle": True,
                    "body_part": " 肩颈 ",
                    "chargeable": True,
                },
                {
                    "project_id": self.local_id,
                    "code": "hxy-jubu-30",
                    "service_line_id": "local-b",
                    "state": "confirmed",
                    "qualifies_for_foot_bath_bundle": True,
                    "body_part": "肩颈",
                    "chargeable": True,
                },
                {
                    "project_id": self.local_id,
                    "code": "hxy-jubu-30",
                    "service_line_id": "local-c",
                    "state": "confirmed",
                    "qualifies_for_foot_bath_bundle": True,
                    "body_part": "腰背",
                    "chargeable": True,
                },
            ])

        self.assertEqual(pricing["qualified_local_unit_count"], 2)
        self.assertEqual(pricing["matched_foot_bath_count"], 1)

    def test_pending_or_state_less_lines_do_not_count_as_confirmed_bundle_units(self):
        with self.SessionLocal() as db:
            pricing = calculate_selection_pricing(db, [
                {"project_id": self.foot_bath_id, "code": "hxy-qiqing-30", "state": "pending", "chargeable": True},
                {"project_id": self.local_id, "code": "hxy-jubu-30", "state": "confirmed", "qualifies_for_foot_bath_bundle": True, "body_part": "肩颈", "chargeable": True},
                {"project_id": self.local_id, "code": "hxy-jubu-30", "state": "confirmed", "qualifies_for_foot_bath_bundle": True, "body_part": "腰背", "chargeable": True},
            ])

        self.assertEqual(pricing["matched_foot_bath_count"], 0)
        self.assertEqual(pricing["promotion_adjustment_cents"], 0)


if __name__ == "__main__":
    unittest.main()
