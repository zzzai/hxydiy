"""Fail-closed parsing of observed source finance UI, without inferred savings."""
from decimal import Decimal
import re

from contracts import SHOP, require


def amount(value, prefix=""):
    require(type(value) is str, "finance_amount_missing")
    match = re.fullmatch(re.escape(prefix) + r"[￥¥](\d+(?:\.\d{1,2})?)", value.strip())
    require(match is not None, "finance_amount_invalid")
    cents = Decimal(match[1]) * 100
    require(cents <= 2**63 - 1, "finance_amount_overflow")
    return int(cents)


def line_fact(item):
    require(type(item.get("name")) is str and 0 < len(item["name"]) <= 255,
            "finance_line_name_invalid")
    quantity = None
    if item.get("quantity") is not None:
        require(type(item["quantity"]) is str, "finance_quantity_invalid")
        match = re.fullmatch(r"×(\d+(?:\.\d{1,3})?)", item["quantity"])
        require(match is not None and 0 < Decimal(match[1]) <= Decimal("999999999.999"),
                "finance_quantity_invalid")
        quantity = match[1]
    return {"description": item["name"], "source_type": item.get("type"),
            "quantity": quantity,
            "original_display_cents": amount(item["original"], "原价") if item.get("original") not in (None, "", "原价¥") else None,
            "selling_display_cents": amount(item["settled"]) if item.get("settled") else None,
            "settled_line_total_cents": None}


def bill_fact(row, detail):
    require(row.get("shop") == SHOP, "finance_bill_store_conflict")
    require(type(row.get("bill_no")) is str and 0 < len(row["bill_no"]) <= 128,
            "finance_bill_number_invalid")
    payments = row.get("payment", "").splitlines()
    require(bool(payments), "finance_payment_missing")
    guests = [re.fullmatch(r"客流：\s*(\d+)", value)
              for value in detail.get("scope_and_time", [])]
    guests = [int(value[1]) for value in guests if value]
    require(len(guests) <= 1, "finance_guest_count_ambiguous")
    count = guests[0] if guests else None
    return {"source_bill_no": row["bill_no"], "source_time_text": row.get("time"),
            "settled_total_cents": amount(payments[0]), "guest_count": count,
            "attribution_status": "shared" if count is not None and count > 1 else "unresolved",
            "bill_status": "unknown", "refund_status": "unknown",
            "payment_evidence_complete": False, "card_principal_debit_cents": None,
            "savings_cents": None, "lines": [line_fact(item) for item in row.get("items", [])]}


def check_pages(pages, total, size):
    require(type(total) is int and 0 <= total <= 100000 and type(size) is int and size > 0,
            "finance_pagination_invalid")
    require(len(pages) == max(1, (total + size - 1) // size), "finance_page_count_mismatch")
    result = []
    for number, page in enumerate(pages, 1):
        last = number == len(pages)
        require(page["number"] == number and page["last"] is last, "finance_last_page_unproven")
        require(len(page["rows"]) == (total - (number - 1) * size if last else size),
                "finance_row_count_mismatch")
        result.extend(page["rows"])
    require(len(result) == total, "finance_total_mismatch")
    return result
