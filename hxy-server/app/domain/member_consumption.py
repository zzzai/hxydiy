"""Pure rules for source consumption history; no database or I/O.

This module validates the amount/dedupe/conflict rules with synthetic data
before any table migration or real source import is approved. Unknown evidence
is ``None`` and blocked, never defaulted to 0.

``source_row_sha256`` is evidence-row provenance, not "same fact" identity:
two rows may carry the same evidence SHA but different semantic content. The
normalized semantic key (``bill_semantic_key``) decides duplicate vs conflict,
and ``bill_content_sha256`` is its stable digest for persistence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
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


def bill_semantic_key(bill: ConsumptionBill) -> tuple:
    """Normalized semantic identity; deliberately excludes evidence-row SHA."""
    lines = tuple(
        (
            line.description,
            line.quantity,
            line.store_price_cents,
            line.settled_cents,
            line.source_line_key,
            line.line_order,
        )
        for line in bill.lines
    )
    return (
        bill.store_id,
        bill.source_bill_no,
        bill.user_id,
        bill.bill_type,
        bill.bill_status,
        bill.attribution_status,
        bill.refund_status,
        bill.payment_evidence_complete,
        bill.source_bill_version,
        bill.store_price_total_cents,
        bill.settled_total_cents,
        bill.coupon_payment_cents,
        bill.card_principal_debit_cents,
        bill.card_bonus_debit_cents,
        bill.cash_payment_cents,
        bill.other_payment_cents,
        lines,
        bill.linked_card_ids,
    )


def _jsonable(value):
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def bill_content_sha256(bill: ConsumptionBill) -> str:
    """Stable digest of normalized semantic content (persistence idempotency)."""
    payload = json.dumps(
        _jsonable(bill_semantic_key(bill)),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def ingest_bills(existing: dict, bills: Iterable[ConsumptionBill]) -> dict:
    """Idempotency model with whole-group precheck and zero partial writes.

    ``existing`` maps ``(store_id, source_bill_no)`` to a semantic digest
    (``bill_content_sha256``). A same-batch same-bill conflict rejects the whole
    group without writing, so the result is order-independent.
    """
    groups: dict[tuple[int, str], list[ConsumptionBill]] = {}
    for bill in bills:
        groups.setdefault((bill.store_id, bill.source_bill_no), []).append(bill)

    inserted: list[str] = []
    duplicates: list[str] = []
    conflicts: list[str] = []
    for key, group in groups.items():
        digests = {bill_content_sha256(bill) for bill in group}
        if len(digests) > 1:
            conflicts.append(key[1])
            continue
        digest = next(iter(digests))
        previous = existing.get(key)
        if previous is None:
            existing[key] = digest
            inserted.append(key[1])
        elif previous == digest:
            duplicates.append(key[1])
        else:
            conflicts.append(key[1])
    return {"inserted": inserted, "duplicates": duplicates, "conflicts": conflicts}


def aggregate_verified(bills: Iterable[ConsumptionBill]) -> dict:
    """Count each source bill once; semantic conflicts exclude the whole group.

    Two rows with the same evidence SHA but different semantic content are a
    conflict, never first-win, regardless of input order.
    """
    groups: dict[tuple[int, str], list[ConsumptionBill]] = {}
    for bill in bills:
        groups.setdefault((bill.store_id, bill.source_bill_no), []).append(bill)
    total = 0
    verified = 0
    blocked = 0
    conflicts = 0
    for group in groups.values():
        digests = {bill_content_sha256(item) for item in group}
        if len(digests) > 1:
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
