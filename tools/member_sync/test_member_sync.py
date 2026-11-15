"""Behavior tests use synthetic cards only; no browser credentials or production data."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as c
import runner

NOW = datetime.now(timezone.utc)
OLD = "000100"
NEW = "000200"


def fixture():
    row = {"card_number": OLD, "store_name": c.SHOP, "allow_cross_store_text": "否",
           "state_text": "", "card_name": "荷小悦年度权益会员卡", "source_card_type": "储值消费卡",
           "masked_phone": "139****0000", "opened_at_date": "2026-11-01",
           "expires_at_date": "2027-11-01", "balance_yuan": "0.00"}
    new = dict(row, card_number=NEW)
    detail = {"card_number": NEW, "card_name": new["card_name"], "store_name": c.SHOP,
              "phone": "13900000000", "opened_at_date": "2026-11-01",
              "expiry_text": "2027-11-01", "balance_yuan": "0", "state_text": ""}
    scan = {"scope": c.SCOPE, "search_text": "", "shop_name": c.SHOP, "total": 2,
            "pages": [{"number": 1, "total": 2, "rows": [row, new]}],
            "details": {c.source_key(NEW): detail}}
    index = {"scope": c.SCOPE, "business_writes": 0, "source_keys": [c.source_key(OLD)],
             "source_cards": 1, "observed_at_utc": NOW.isoformat()}
    return index, [copy.deepcopy(scan), copy.deepcopy(scan)]


class ContractTests(unittest.TestCase):
    def test_new_only_and_standing_confirmation(self):
        index, scans = fixture()
        result = c.verify(index, scans, NOW)
        self.assertEqual([x["card_number"] for x in result["candidates"]], [NEW])
        self.assertEqual(result["standing_confirmation_date"], "2026-10-25")
        self.assertEqual(result["business_writes"], 0)
        self.assertFalse(result["apply_enabled"])

    def test_raw_identity_not_trimmed_or_zero_padded(self):
        self.assertNotEqual(c.source_key("001"), c.source_key("1"))
        self.assertNotEqual(c.source_key(" 001"), c.source_key("001"))
        with self.assertRaises(c.Stop):
            c.source_key(1)

    def test_existing_balance_and_same_day_precision_ignored(self):
        index, scans = fixture()
        old = scans[1]["pages"][0]["rows"][0]
        old.update(balance_yuan="99999.99", opened_at_date="2026-11-01T12:12:12")
        self.assertEqual(c.verify(index, scans, NOW)["new_cards"], 1)

    def test_missing_old_card_does_not_trigger_deletion(self):
        index, scans = fixture()
        index["source_keys"].append(c.source_key("previously-present"))
        index["source_cards"] += 1
        self.assertEqual(c.verify(index, scans, NOW)["existing_source_cards_missing"], 1)

    def test_no_new_no_details_or_writes(self):
        index, scans = fixture()
        index["source_keys"].append(c.source_key(NEW))
        index["source_cards"] = 2
        for scan in scans:
            scan["details"] = {}
        result = c.verify(index, scans, NOW)
        self.assertEqual((result["status"], result["new_cards"], result["business_writes"]),
                         ("no_new", 0, 0))

    def test_same_phone_multiple_cards_remains_two_cards(self):
        index, scans = fixture()
        for scan in scans:
            third = dict(scan["pages"][0]["rows"][1], card_number="000201")
            scan["pages"][0]["rows"].append(third)
            scan["pages"][0]["total"] = scan["total"] = 3
            scan["details"][c.source_key("000201")] = dict(scan["details"][c.source_key(NEW)],
                                                         card_number="000201")
        result = c.verify(index, scans, NOW)
        self.assertEqual((result["new_cards"], result["candidate_people"]), (2, 1))

    def test_stored_value_requires_explicit_unlimited_evidence(self):
        index, scans = fixture()
        for scan in scans:
            scan["pages"][0]["rows"][1].update(card_name="荷小悦会员卡", expires_at_date="")
            scan["details"][c.source_key(NEW)].update(card_name="荷小悦会员卡", expiry_text="")
        with self.assertRaisesRegex(c.Stop, "unlimited_not_proven"):
            c.verify(index, scans, NOW)
        for scan in scans:
            scan["details"][c.source_key(NEW)]["expiry_text"] = "不限期"
        self.assertTrue(c.verify(index, scans, NOW)["candidates"][0]["source_expiry_unlimited"])

    def test_bad_state_overrides_standing_confirmation_even_old_card(self):
        for state in ("停用", "退卡", "挂失", "冻结"):
            index, scans = fixture()
            scans[0]["pages"][0]["rows"][0]["state_text"] = state
            with self.subTest(state=state), self.assertRaisesRegex(c.Stop, "adverse"):
                c.verify(index, scans, NOW)

    def test_scope_and_partial_pages_fail(self):
        mutators = [
            lambda p: p.update(scope=dict(c.SCOPE, shop_id=1582031)),
            lambda p: p.update(search_text="123"),
            lambda p: p.update(shop_name="其他门店"),
            lambda p: p.update(total=16),
            lambda p: p["pages"][0].update(number=2),
            lambda p: p["pages"][0].update(total=3),
            lambda p: p["pages"][0]["rows"].pop(),
            lambda p: p["pages"][0]["rows"][1].update(card_number=OLD),
            lambda p: p["pages"][0]["rows"][1].update(store_name="其他门店"),
            lambda p: p["pages"][0]["rows"][1].update(allow_cross_store_text="是"),
        ]
        for mutate in mutators:
            index, scans = fixture()
            mutate(scans[0])
            with self.subTest(mutate=mutate), self.assertRaises(c.Stop):
                c.verify(index, scans, NOW)

    def test_detail_conflicts_fail(self):
        mutators = [
            lambda d: d.update(phone="13800000000"),
            lambda d: d.update(phone="139****0000"),
            lambda d: d.update(card_number="wrong"),
            lambda d: d.update(card_name="other"),
            lambda d: d.update(store_name="other"),
            lambda d: d.update(opened_at_date="2026-11-02"),
            lambda d: d.update(expiry_text="2027-11-02"),
            lambda d: d.update(balance_yuan="1"),
            lambda d: d.update(state_text="挂失"),
        ]
        for mutate in mutators:
            index, scans = fixture()
            mutate(scans[0]["details"][c.source_key(NEW)])
            with self.subTest(mutate=mutate), self.assertRaises(c.Stop):
                c.verify(index, scans, NOW)

    def test_change_during_scan_fails_even_if_each_candidate_is_valid(self):
        index, scans = fixture()
        scans[1]["pages"][0]["rows"][1]["balance_yuan"] = "1"
        scans[1]["details"][c.source_key(NEW)]["balance_yuan"] = "1.00"
        with self.assertRaisesRegex(c.Stop, "changed_between"):
            c.verify(index, scans, NOW)

    def test_full_second_pass_required(self):
        index, scans = fixture()
        with self.assertRaises(c.Stop):
            c.verify(index, scans[:1], NOW)
        scans[1]["pages"][0]["rows"][1]["card_number"] = "other"
        with self.assertRaisesRegex(c.Stop, "keyset_changed"):
            c.verify(index, scans, NOW)

    def test_money_and_dates_exact(self):
        for invalid in ("NaN", "Infinity", "-1", "0.001", "1e3", "1,000", "21474836.48"):
            with self.subTest(invalid=invalid), self.assertRaises(c.Stop):
                c.money(invalid)
        self.assertEqual(c.money("44.50"), 4450)
        with self.assertRaises(c.Stop):
            c.date_only("2026-02-30")

    def test_old_detail_data_must_not_be_exported(self):
        index, scans = fixture()
        scans[0]["details"][c.source_key(OLD)] = {"phone": "13900000000"}
        with self.assertRaisesRegex(c.Stop, "details_scope"):
            c.verify(index, scans, NOW)

    def test_missing_details_fail(self):
        index, scans = fixture()
        scans[1]["details"] = {}
        with self.assertRaises(c.Stop):
            c.verify(index, scans, NOW)

    def test_stale_and_empty_index_fail(self):
        index, scans = fixture()
        for age in (1801, -1):
            index["observed_at_utc"] = (NOW - timedelta(seconds=age)).isoformat()
            with self.assertRaisesRegex(c.Stop, "stale"):
                c.verify(index, scans, NOW)
        index["observed_at_utc"] = NOW.isoformat()
        index.update(source_cards=0, source_keys=[])
        with self.assertRaisesRegex(c.Stop, "empty"):
            c.verify(index, scans, NOW)


class RunnerTests(unittest.TestCase):
    def test_failure_latch_no_repeat_collection_or_notification(self):
        calls = []
        index, _ = fixture()
        def fail(known):
            calls.append("collect")
            raise c.Stop("source_login_required")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            notify = lambda _: calls.append("notify") or "test_only"
            first = runner.run(root, fail, lambda: index, notify)
            second = runner.run(root, fail, lambda: calls.append("probe"), notify)
            self.assertEqual(first["status"], "blocked")
            self.assertEqual(second["status"], "blocked_latched")
            self.assertEqual(calls, ["collect", "notify"])
            self.assertEqual(first["business_writes"], 0)

    def test_runtime_exception_does_not_leak_customer_data(self):
        index, _ = fixture()
        def fail(_):
            raise RuntimeError("private phone=13900000000")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runner.run(root, fail, lambda: index, lambda _: "test_only")
            all_json = "".join(p.read_text(encoding="utf-8") for p in root.rglob("*.json"))
            self.assertNotIn("13900000000", all_json)
            self.assertNotIn("private phone", all_json)

    def test_success_report_is_redacted_and_old_amounts_not_retained(self):
        index, scans = fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = runner.run(root, lambda _: scans, lambda: index,
                                lambda _: self.fail("success must not notify"))
            self.assertEqual(result["status"], "readonly_passed")
            public = (root / "report.json").read_text(encoding="utf-8")
            self.assertNotIn("13900000000", public)
            self.assertNotIn(NEW, public)
            evidence = json.loads(next(root.rglob("source-private.json")).read_text(encoding="utf-8"))
            self.assertNotIn("balance_yuan", evidence[0]["pages"][0]["rows"][0])
            self.assertEqual(result["source_evidence_sha256"], c.digest(evidence))
            self.assertEqual(c.verify(index, evidence)["new_cards"], 1)

    def test_corrupt_state_stops_before_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "state.json").write_text("broken", encoding="utf-8")
            result = runner.run(root, lambda _: self.fail("collector must not run"),
                                lambda: self.fail("probe must not run"), lambda _: "test_only")
            self.assertEqual(result["code"], "state_unreadable")
            self.assertTrue(json.loads((root / "state.json").read_text())["blocked"])

    def test_single_owner_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            with runner.single_instance(Path(folder)) as first:
                with runner.single_instance(Path(folder)) as second:
                    self.assertTrue(first)
                    self.assertFalse(second)


if __name__ == "__main__":
    unittest.main()
