"""Read-only projection of a customer's own source consumption history.

Only owned, store-scoped, non-conflicting source bills are projected. A bill
group with the same number but different semantic content is a conflict and is
excluded, never first-win. No row is written here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.member_consumption import BillLine, ConsumptionBill, compute_bill_savings
from app.models import MembershipConsumptionBill, MembershipConsumptionLine, User


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    current = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return current.isoformat()


def _to_domain(bill: MembershipConsumptionBill, lines: list[MembershipConsumptionLine]) -> ConsumptionBill:
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
                quantity=int(line.quantity) if line.quantity is not None else None,
                store_price_cents=line.store_price_cents,
                settled_cents=line.settled_cents,
                source_line_key=line.source_line_key,
                line_order=line.line_order,
            )
            for line in lines
        ),
        linked_card_ids=(bill.card_id,) if bill.card_id is not None else (),
    )


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


def build_customer_consumption_history(
    db: Session, user: User, offset: int = 0, limit: int = 20
) -> dict:
    base = select(MembershipConsumptionBill).where(
        MembershipConsumptionBill.user_id == user.id,
        MembershipConsumptionBill.source == settings.member_source,
        MembershipConsumptionBill.store_id == settings.member_source_store_id,
    )
    rows = list(db.scalars(
        base.order_by(
            MembershipConsumptionBill.occurred_at.desc(),
            MembershipConsumptionBill.id.desc(),
        )
    ))

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

    verified_bills: list[dict] = []
    verified_savings = 0
    conflict_groups = 0
    for group in groups.values():
        contents = {row.content_sha256 for row in group}
        if len(contents) > 1:
            conflict_groups += 1
            continue
        row = group[0]
        lines = lines_by_bill.get(row.id, [])
        result = compute_bill_savings(_to_domain(row, lines))
        if result.status == "verified":
            verified_bills.append(_bill_payload(
                row, lines,
                {"status": result.status, "amount_cents": result.savings_cents},
            ))
            verified_savings += result.savings_cents or 0

    total = len(verified_bills)
    page = verified_bills[offset:offset + limit]
    return {
        "coverage": {
            "source": settings.member_source,
            "store_ids": [settings.member_source_store_id],
            "history": "returned" if rows else "no_source_data",
            "conflict_bill_groups": conflict_groups,
            "note": "来源消费历史为独立来源记录，不含 DIY 订单/钱包；覆盖期与缺失以来源批次声明为准。",
        },
        "bills": page,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + limit < total,
        },
        "savings": {
            "status": "verified" if verified_bills else "unverified",
            "amount_cents": verified_savings if verified_bills else None,
            "bill_count": total if verified_bills else None,
            "note": "累计消费优惠只计入来源可核实、归属本人、支付完整的服务账单；券支付单列，独立于既有 DIY 会员节省。",
        },
        "generated_at": datetime.now(UTC).isoformat(),
        "read_only": True,
    }
