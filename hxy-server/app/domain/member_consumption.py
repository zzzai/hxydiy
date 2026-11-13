"""Pure rules for source consumption history; no database or I/O.

This module exists only to validate the proposed amount/dedupe rules with
synthetic data before any table migration or real source import is approved.
Unknown evidence is represented by ``None`` and blocked, never defaulted to 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class BillLine:
    description: str
    quantity: int | None
    store_price_cents: int | None
    settled_cents: int | None
    source_line_key: str | None = None
    line_order: int = 0


@dataclass(frozen=True)
class ConsumptionBill:
    source_bill_no: str
    source_row_sha256: str
    store_id: int
    user_id: int | None
    bill_type: str = "service"  # service/open_card/package/recharge/unknown
    attribution_status: str = "owned"  # owned/shared/unresolved
    refund_status: str = "none"  # none/partial/refunded/void/unknown
    source_bill_version: str | None = None
    store_price_total_cents: int | None = None
    settled_total_cents: int | None = None
    coupon_payment_cents: int | None = None
    card_principal_debit_cents: int | None = None
    card_bonus_debit_cents: int | None = None
    cash_payment_cents: int | None = None
    other_payment_cents: int | None = None
    lines: tuple[BillLine, ...] = ()
    linked_card_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class SavingsResult:
    status: str  # verified/excluded/unknown/blocked/anomaly
    savings_cents: int | None
    reason: str
    coupon_payment_cents: int | None = None
    card_payment_cents: int | None = None


def compute_bill_savings(bill: ConsumptionBill) -> SavingsResult:
    if bill.bill_type != "service":
        return SavingsResult("excluded", None, f"bill_type={bill.bill_type}_not_consumption")
    if bill.attribution_status != "owned":
        return SavingsResult("blocked", None, f"attribution={bill.attribution_status}_not_personal")
    if bill.refund_status != "none":
        return SavingsResult("blocked", None, f"refund_status={bill.refund_status}_needs_evidence")
    if not bill.lines:
        return SavingsResult("unknown", None, "lines_missing")
    if any(line.quantity is None or line.store_price_cents is None or line.settled_cents is None for line in bill.lines):
        return SavingsResult("unknown", None, "line_price_or_quantity_missing")
    if bill.settled_total_cents is None:
        return SavingsResult("unknown", None, "settled_total_missing")
    line_store_total = sum((line.store_price_cents or 0) * (line.quantity or 0) for line in bill.lines)
    store_total = bill.store_price_total_cents if bill.store_price_total_cents is not None else line_store_total
    if store_total != line_store_total:
        return SavingsResult("anomaly", None, "header_and_line_store_price_mismatch")
    line_settled_total = sum((line.settled_cents or 0) for line in bill.lines)
    if line_settled_total != bill.settled_total_cents:
        return SavingsResult("anomaly", None, "header_and_line_settled_mismatch")
    savings = store_total - bill.settled_total_cents
    if savings < 0:
        return SavingsResult("anomaly", None, "negative_savings")
    card_payment = None
    if bill.card_principal_debit_cents is not None or bill.card_bonus_debit_cents is not None:
        card_payment = (bill.card_principal_debit_cents or 0) + (bill.card_bonus_debit_cents or 0)
    return SavingsResult("verified", savings, "verified_historical_price_and_settlement", bill.coupon_payment_cents, card_payment)


def ingest_bills(existing: dict[tuple[int, str], str], bills: Iterable[ConsumptionBill]) -> dict:
    """Synthetic idempotency model: same bill content is duplicate, changed content conflicts."""
    inserted: list[str] = []
    duplicates: list[str] = []
    conflicts: list[str] = []
    for bill in bills:
        key = (bill.store_id, bill.source_bill_no)
        previous = existing.get(key)
        if previous is None:
            existing[key] = bill.source_row_sha256
            inserted.append(bill.source_bill_no)
        elif previous == bill.source_row_sha256:
            duplicates.append(bill.source_bill_no)
        else:
            conflicts.append(bill.source_bill_no)
    return {"inserted": inserted, "duplicates": duplicates, "conflicts": conflicts}


def aggregate_verified(bills: Iterable[ConsumptionBill]) -> dict:
    """Count each bill once, even when multiple cards or people are linked."""
    seen: set[tuple[int, str]] = set()
    total = 0
    verified = 0
    blocked = 0
    for bill in bills:
        key = (bill.store_id, bill.source_bill_no)
        if key in seen:
            continue
        seen.add(key)
        result = compute_bill_savings(bill)
        if result.status == "verified":
            verified += 1
            total += result.savings_cents or 0
        elif result.status in {"blocked", "anomaly", "unknown"}:
            blocked += 1
    return {"savings_cents": total, "verified_bills": verified, "blocked_bills": blocked, "unique_bills": len(seen)}


def visible_to(bill: ConsumptionBill, user_id: int, store_id: int) -> bool:
    return bill.user_id == user_id and bill.store_id == store_id
