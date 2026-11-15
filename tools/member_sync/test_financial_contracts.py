"""Synthetic source facts only; unknown money must remain unknown."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contracts import SCOPE, Stop
import financial_contracts as fc


class FinancialContractTests(unittest.TestCase):
    def test_source_amount_uses_exact_cents(self):
        self.assertEqual(fc.amount("余额:￥173.01", "余额:"), 17301)
        self.assertEqual(fc.amount("原价¥129", "原价"), 12900)
        self.assertEqual(fc.amount("￥0"), 0)
        for value in ("", "未知", "￥1.001", "￥-1", "￥NaN", "￥1,000", None):
            with self.assertRaises(Stop):
                fc.amount(value)

    def test_line_preserves_original_price_and_quantity(self):
        item = {"type":"项", "name":"合成服务", "quantity":"×2", "settled":"¥79", "original":"原价¥119"}
        result = fc.line_fact(item)
        self.assertEqual(result["quantity"], "2")
        self.assertEqual(result["original_display_cents"], 11900)
        self.assertEqual(result["selling_display_cents"], 7900)
        # The UI price basis is not assumed to be a unit or a line total.
        self.assertIsNone(result["settled_line_total_cents"])
        for quantity in ("×0", "×-1", "×1.0001", "2"):
            with self.assertRaises(Stop):
                fc.line_fact(dict(item, quantity=quantity))

    def test_summary_does_not_invent_refund_or_payment_evidence(self):
        row = {"bill_no":"SYN-001", "time":"2026-11-14 18:00", "payment":"￥89.00\n微信:￥89.00\n卡金:￥0.00", "shop":"紫薇壹号店", "items":[]}
        result=fc.bill_fact(row, {"scope_and_time":["客流：\n1"], "financial_summary":["消费总额： ￥89", "优惠： ￥40（价格方案优惠 ￥40）"]})
        self.assertEqual(result["settled_total_cents"], 8900)
        self.assertEqual(result["guest_count"], 1)
        self.assertEqual(result["refund_status"], "unknown")
        self.assertFalse(result["payment_evidence_complete"])
        self.assertIsNone(result["savings_cents"])
        self.assertIsNone(result["card_principal_debit_cents"])

    def test_shared_bill_is_explicitly_blocked(self):
        row={"bill_no":"SYN-2", "time":"2026-11-14 18:00", "payment":"￥406.00\n卡金:￥327.00\n优惠券:￥79.00", "shop":"紫薇壹号店", "items":[]}
        result=fc.bill_fact(row, {"scope_and_time":["客流：\n4"], "financial_summary":[]})
        self.assertEqual(result["attribution_status"], "shared")
        self.assertIsNone(result["savings_cents"])
        with self.assertRaises(Stop):
            fc.bill_fact(dict(row,shop="其他门店"),{})

    def test_card_and_gift_rows_keep_absent_quantity_and_price_unknown(self):
        result=fc.line_fact({"type":"卡","name":"Synthetic card","quantity":None,"settled":"¥0","original":"原价¥0"})
        self.assertIsNone(result["quantity"])
        gift=fc.line_fact({"type":"","name":"Synthetic coupon","quantity":None,"settled":"¥0","original":"原价¥"})
        self.assertIsNone(gift["original_display_cents"])
        self.assertEqual(gift["selling_display_cents"],0)

    def test_pagination_requires_count_and_last_page(self):
        self.assertEqual(fc.check_pages([{"number":1,"rows":[1,2],"last":True}],2,10),[1,2])
        for pages,total in [([{ "number":1,"rows":[1],"last":True}],2), ([{"number":2,"rows":[1],"last":True}],1), ([{"number":1,"rows":[1],"last":False}],1)]:
            with self.assertRaises(Stop):
                fc.check_pages(pages,total,10)


if __name__ == "__main__":
    unittest.main()
