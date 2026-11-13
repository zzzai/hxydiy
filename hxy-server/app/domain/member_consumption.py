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
    bill_type: str = "unknown"  # service/open_card/package/recharge/unknown
    bill_status: str = "unknown"  # normal_settled/voided/reversed/unknown
    attribution_status: str = "unresolved"  # owned/shared/unresolved
    refund_status: str = "unknown"  # none/partial/refunded/void/unknown
    payment_evidence_complete: bool = False
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
    if bill.bill_status != "normal_settled":
        return SavingsResult("blocked", None, f"bill_status={bill.bill_status}_not_current_normal")
    if bill.attribution_status != "owned":
        return SavingsResult("blocked", None, f"attribution={bill.attribution_status}_not_personal")
    if bill.refund_status != "none":
        return SavingsResult("blocked", None, f"refund_status={bill.refund_status}_needs_evidence")
    if bill.settled_total_cents is None:
        return SavingsResult("unknown", None, "settled_total_missing")
    if bill.settled_total_cents < 0:
        return SavingsResult("anomaly", None, "settled_total_negative")
    if not bill.lines:
        return SavingsResult("unknown", None, "lines_missing")
    if any(line.quantity is None or line.quantity <= 0 or line.store_price_cents is None
           or line.settled_cents is None or line.store_price_cents < 0 or line.settled_cents < 0
           for line in bill.lines):
        return SavingsResult("unknown", None, "line_price_quantity_invalid_or_missing")
    line_store_total = sum(line.store_price_cents * line.quantity for line in bill.lines)
    store_total = bill.store_price_total_cents if bill.store_price_total_cents is not None else line_store_total
    if store_total < 0:
        return SavingsResult("anomaly", None, "store_price_total_negative")
    if store_total != line_store_total:
        return SavingsResult("anomaly", None, "header_and_line_store_price_mismatch")
    line_settled_total = sum(line.settled_cents for line in bill.lines)
    if line_settled_total != bill.settled_total_cents:
        return SavingsResult("anomaly", None, "header_and_line_settled_mismatch")

    # A savings number is only trustworthy when the source's payment breakdown
    # is explicitly complete and every component reconciles to the final amount.
    components = (
        bill.card_principal_debit_cents,
        bill.card_bonus_debit_cents,
        bill.coupon_payment_cents,
        bill.cash_payment_cents,
        bill.other_payment_cents,
    )
    if not bill.payment_evidence_complete or any(value is None for value in components):
        return SavingsResult("unknown", None, "payment_breakdown_unknown_or_incomplete")
    if any(value < 0 for value in components):
        return SavingsResult("anomaly", None, "payment_component_negative")
    if sum(components) != bill.settled_total_cents:
        return SavingsResult("anomaly", None, "payment_breakdown_does_not_reconcile")

    savings = store_total - bill.settled_total_cents
    if savings < 0:
        return SavingsResult("anomaly", None, "negative_savings")
    card_payment = bill.card_principal_debit_cents + bill.card_bonus_debit_cents
    return SavingsResult("verified", savings, "verified_historical_price_settlement_and_payment",
                         bill.coupon_payment_cents, card_payment)


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
    """Count each source bill once; conflicting versions exclude the whole group.

    Version order is not trusted until the source supplies a stable revision
    rule. Therefore two different contents for one bill number are a conflict,
    regardless of input order, and never first-win.
    """
    groups: dict[tuple[int, str], list[ConsumptionBill]] = {}
    for bill in bills:
        groups.setdefault((bill.store_id, bill.source_bill_no), []).append(bill)
    total = 0
    verified = 0
    blocked = 0
    conflicts = 0
    for group in groups.values():
        hashes = {item.source_row_sha256 for item in group}
        if len(hashes) > 1:
            conflicts += 1
            blocked += 1
            continue
        result = compute_bill_savings(group[0])
        if result.status == "verified":
            verified += 1
            total += result.savings_cents or 0
        elif result.status in {"blocked", "anomaly", "unknown"}:
            blocked += 1
    return {
        "savings_cents": total if verified else None,
        "verified_bills": verified,
        "blocked_bills": blocked,
        "conflict_bills": conflicts,
        "unique_bills": len(groups),
    }


def visible_to(bill: ConsumptionBill, user_id: int, store_id: int) -> bool:
    return (bill.attribution_status == "owned"
            and bill.user_id is not None
            and bill.user_id == user_id
            and bill.store_id == store_id)
