"""Read-only projection of a customer's own source consumption history.

Only bills from eligible (applied, in-scope) batches contribute. Conflicts are
resolved across the whole scoped bill group before projecting the current
user, so an alternate owner's conflicting version can never first-win or leak.
Persisted ``content_sha256`` is re-derived from actual facts and validated.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.member_consumption import (
    BillLine,
    ConsumptionBill,
    bill_content_sha256,
    compute_bill_savings,
)
from app.models import (
    MembershipConsumptionBatch,
    MembershipConsumptionBill,
    MembershipConsumptionLine,
    User,
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    current = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return current.isoformat()


def _quantity(value):
    """Preserve exact quantity for the semantic digest; never truncate.

    Whole quantities collapse to ``int``. Fractional ``Decimal`` values stay
    exact (1.5 and 2.5 hash differently) while savings treat them as unknown.
    """
    if value is None:
        return None
    if value == int(value):
        return int(value)
    return value


def to_domain_bill(bill: MembershipConsumptionBill, lines: list[MembershipConsumptionLine]) -> ConsumptionBill:
    return ConsumptionBill(
        source_bill_no=bill.source_bill_no,
        source_row_sha256=bill.source_row_sha256,
        store_id=bill.store_id,
        user_id=bill.user_id,
        bill_type=bill.bill_type,
        bill_status=bill.bill_status,
        attribution_status=bill.attribution_status,
        refund_status=bill.refund_status,
        payment_evidence_complete=bill.payment_evidence_complete,
        source_bill_version=bill.source_bill_version,
        source_version_no=bill.source_version_no,
        source_current_marker=bill.source_current_marker,
        currency=bill.currency,
        occurred_at=bill.occurred_at,
        settled_at=bill.settled_at,
        store_price_total_cents=bill.store_price_total_cents,
        settled_total_cents=bill.settled_total_cents,
        coupon_payment_cents=bill.coupon_payment_cents,
        card_principal_debit_cents=bill.card_principal_debit_cents,
        card_bonus_debit_cents=bill.card_bonus_debit_cents,
        cash_payment_cents=bill.cash_payment_cents,
        other_payment_cents=bill.other_payment_cents,
        lines=tuple(
            BillLine(
                description=line.description,
                quantity=_quantity(line.quantity),
                store_price_cents=line.store_price_cents,
                settled_cents=line.settled_cents,
                source_line_key=line.source_line_key,
                line_order=line.line_order,
            )
            for line in lines
        ),
        linked_card_ids=(bill.card_id,) if bill.card_id is not None else (),
    )


def content_sha256_for(bill: MembershipConsumptionBill, lines: list[MembershipConsumptionLine]) -> str:
    return bill_content_sha256(to_domain_bill(bill, lines))


def _line_payload(line: MembershipConsumptionLine) -> dict:
    return {
        "description": line.description,
        "quantity": float(line.quantity) if line.quantity is not None else None,
        "store_price_cents": line.store_price_cents,
        "settled_cents": line.settled_cents,
    }


def _bill_payload(bill: MembershipConsumptionBill, lines: list[MembershipConsumptionLine], savings: dict) -> dict:
    return {
        "id": bill.id,
        "source_bill_no": bill.source_bill_no,
        "bill_type": bill.bill_type,
        "bill_status": bill.bill_status,
        "store_id": bill.store_id,
        "currency": bill.currency,
        "occurred_at": _iso(bill.occurred_at),
        "settled_at": _iso(bill.settled_at),
        "store_price_total_cents": bill.store_price_total_cents,
        "settled_total_cents": bill.settled_total_cents,
        "coupon_payment_cents": bill.coupon_payment_cents,
        "card_principal_debit_cents": bill.card_principal_debit_cents,
        "card_bonus_debit_cents": bill.card_bonus_debit_cents,
        "cash_payment_cents": bill.cash_payment_cents,
        "other_payment_cents": bill.other_payment_cents,
        "savings": savings,
        "lines": [_line_payload(line) for line in lines],
    }


def _coverage(applied_batches: list[MembershipConsumptionBatch], has_bills: bool, conflict_groups: int) -> dict:
    if not applied_batches:
        return {
            "source": settings.member_source,
            "store_ids": [settings.member_source_store_id],
            "history": "no_source_data",
            "applied_batch_count": 0,
            "complete": None,
            "query_range_start": None,
            "query_range_end": None,
            "observed_at": None,
            "coverage_gaps": None,
            "conflict_bill_groups": conflict_groups,
            "note": "没有已生效的来源批次，覆盖无法确认。",
        }

    has_declared_gaps = False
    intervals: list[tuple[datetime, datetime]] = []
    all_pages_complete = True
    valid_ranges = True
    for batch in applied_batches:
        if batch.coverage_gaps:
            has_declared_gaps = True
        if batch.last_page_complete is not True:
            all_pages_complete = False
        if batch.query_range_start is None or batch.query_range_end is None or batch.query_range_start > batch.query_range_end:
            valid_ranges = False
        elif batch.page_count is not None and batch.page_count <= 0:
            valid_ranges = False
        else:
            intervals.append((batch.query_range_start, batch.query_range_end))

    contiguous = False
    if valid_ranges and intervals:
        merged: list[tuple[datetime, datetime]] = []
        for start, end in sorted(intervals, key=lambda pair: (pair[0], pair[1])):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        contiguous = len(merged) == 1

    complete = all_pages_complete and valid_ranges and contiguous and not has_declared_gaps
    return {
        "source": settings.member_source,
        "store_ids": [settings.member_source_store_id],
        "history": "returned" if has_bills else "no_source_data",
        "applied_batch_count": len(applied_batches),
        "complete": complete,
        "query_range_start": _iso(min(batch.query_range_start for batch in applied_batches)),
        "query_range_end": _iso(max(batch.query_range_end for batch in applied_batches)),
        "observed_at": _iso(max(batch.observed_at for batch in applied_batches)),
        "coverage_gaps": has_declared_gaps,
        "conflict_bill_groups": conflict_groups,
        "note": "覆盖完整性按已生效批次声明的分页、日期区间与缺失声明保守判定；存在缺失、区间不连续或未知修订时不视为完整。",
    }


def build_customer_consumption_history(
    db: Session, user: User, offset: int = 0, limit: int = 20
) -> dict:
    applied_batches = list(db.scalars(
        select(MembershipConsumptionBatch)
        .where(
            MembershipConsumptionBatch.source == settings.member_source,
            MembershipConsumptionBatch.store_id == settings.member_source_store_id,
            MembershipConsumptionBatch.status == "applied",
        )
        .order_by(MembershipConsumptionBatch.observed_at.desc())
    ))

    if not applied_batches:
        return {
            "coverage": _coverage([], False, 0),
            "bills": [],
            "pagination": {"offset": offset, "limit": limit, "total": 0, "has_more": False},
            "savings": {
                "status": "unverified",
                "amount_cents": None,
                "bill_count": None,
                "note": "累计消费优惠只计入已生效批次、归属本人、支付完整、币种一致的已核实服务账单；券支付单列，独立于既有 DIY 会员节省。",
            },
            "generated_at": datetime.now(UTC).isoformat(),
            "read_only": True,
        }

    batch_ids = [batch.id for batch in applied_batches]
    all_rows = list(db.scalars(
        select(MembershipConsumptionBill)
        .where(
            MembershipConsumptionBill.batch_id.in_(batch_ids),
            MembershipConsumptionBill.source == settings.member_source,
            MembershipConsumptionBill.store_id == settings.member_source_store_id,
        )
        .order_by(
            MembershipConsumptionBill.occurred_at.desc(),
            MembershipConsumptionBill.id.desc(),
        )
    ))

    # Own-candidate keys first: only bill groups where this customer owns a row
    # are in scope, so an empty account cannot learn other customers' groups.
    # Alternate owners' rows for those keys are loaded below for conflict checks.
    candidate_keys = {
        (row.store_id, row.source_bill_no)
        for row in all_rows
        if row.user_id == user.id and row.attribution_status == "owned"
    }
    rows = [row for row in all_rows if (row.store_id, row.source_bill_no) in candidate_keys]

    lines_by_bill: dict[int, list[MembershipConsumptionLine]] = {}
    if rows:
        line_query = (
            select(MembershipConsumptionLine)
            .where(MembershipConsumptionLine.bill_id.in_([row.id for row in rows]))
            .order_by(
                MembershipConsumptionLine.bill_id,
                MembershipConsumptionLine.line_order,
                MembershipConsumptionLine.id,
            )
        )
        for line in db.scalars(line_query):
            lines_by_bill.setdefault(line.bill_id, []).append(line)

    groups: dict[tuple[int, str], list[MembershipConsumptionBill]] = {}
    for row in rows:
        groups.setdefault((row.store_id, row.source_bill_no), []).append(row)

    visible_bills: list[dict] = []
    verified_savings = 0
    verified_count = 0
    conflict_groups = 0
    for group in groups.values():
        domains = {row.id: to_domain_bill(row, lines_by_bill.get(row.id, [])) for row in group}
        recomputed = {row_id: bill_content_sha256(dom) for row_id, dom in domains.items()}
        # Persisted digest must match actual semantic facts; a stale digest means
        # tampered/diverged facts and quarantines the whole group (honest unknown).
        if any(recomputed[row.id] != row.content_sha256 for row in group):
            conflict_groups += 1
            continue
        if len(set(recomputed.values())) > 1:
            conflict_groups += 1
            continue
        owned = [row for row in group if row.user_id == user.id and row.attribution_status == "owned"]
        if not owned:
            continue
        row = owned[0]
        lines = lines_by_bill.get(row.id, [])
        result = compute_bill_savings(domains[row.id])
        if result.status == "excluded":
            continue
        savings = {
            "status": result.status,
            "amount_cents": result.savings_cents if result.status == "verified" else None,
            "reason": None if result.status == "verified" else result.reason,
        }
        visible_bills.append(_bill_payload(row, lines, savings))
        if result.status == "verified":
            verified_savings += result.savings_cents or 0
            verified_count += 1

    total = len(visible_bills)
    page = visible_bills[offset:offset + limit]
    return {
        "coverage": _coverage(applied_batches, bool(candidate_keys), conflict_groups),
        "bills": page,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + limit < total,
        },
        "savings": {
            "status": "verified" if verified_count else "unverified",
            "amount_cents": verified_savings if verified_count else None,
            "bill_count": verified_count if verified_count else None,
            "note": "累计消费优惠只计入已生效批次、归属本人、支付完整、币种一致的已核实服务账单；券支付单列，独立于既有 DIY 会员节省。",
        },
        "generated_at": datetime.now(UTC).isoformat(),
        "read_only": True,
    }

