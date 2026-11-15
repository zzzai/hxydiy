"""Append-only normalized finance facts; callers must verify source/backup evidence.

No HTTP route or production CLI calls this service. Source collection, exact
manifest approval and backup/recovery are separate gates. Never mutate legacy
membership, users, orders, wallets or prior finance facts.
"""
from dataclasses import asdict, dataclass, replace
from datetime import datetime, UTC
from decimal import Decimal
from hashlib import sha256
import json
import re

from sqlalchemy import select, text

from app.domain.member_consumption import ConsumptionBill, bill_content_sha256, compute_bill_savings
from app.models import (MembershipCard, User, Store, MembershipBalanceSnapshot,
                        MembershipConsumptionBatch, MembershipConsumptionBill, MembershipConsumptionLine)
from app.services.customer_consumption import to_domain_bill

SOURCE = "meiguanjia_export"
STORE_ID = 1
STORE_CODE = "hxy-anyang-ziwei-001"
NEW_MODELS = (MembershipConsumptionBatch, MembershipConsumptionBill,
              MembershipConsumptionLine, MembershipBalanceSnapshot)


class ImportBlocked(ValueError):
    """Static diagnostic only, never customer values."""


def require(condition, code):
    if not condition:
        raise ImportBlocked(code)


@dataclass(frozen=True)
class SourceBill:
    card_number: str
    phone: str
    bill: ConsumptionBill
    evidence_ref: str


@dataclass(frozen=True)
class SourceBalance:
    card_number: str
    phone: str
    observed_at: datetime
    total_cents: int | None
    principal_cents: int | None
    bonus_cents: int | None
    evidence_ref: str


@dataclass(frozen=True)
class FinancialBatch:
    batch_key: str
    source_snapshot_sha256: str
    manifest_sha256: str
    query_range_start: datetime
    query_range_end: datetime
    observed_at: datetime
    page_count: int
    last_page_complete: bool
    coverage_gaps: dict
    evidence_ref: str
    bills: tuple[SourceBill, ...] = ()
    balances: tuple[SourceBalance, ...] = ()


def timestamp(value):
    require(isinstance(value, datetime) and value.tzinfo is not None, "timezone_required")
    return value.astimezone(UTC)


def db_time(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def reference(value):
    require(type(value) is str and 0 < len(value) <= 255 and not value.startswith(("/", "\\"))
            and ".." not in value.split("/") and ":" not in value and "\\" not in value, "evidence_reference_invalid")


def cents(value):
    require(value is None or (type(value) is int and 0 <= value <= 2**63 - 1), "invalid_amount")


def owner(db, raw, phone):
    require(type(raw) is str and bool(raw.strip()), "invalid_card_number")
    require(type(phone) is str and re.fullmatch(r"1[3-9]\d{9}", phone), "complete_phone_required")
    key = sha256((STORE_CODE + "\0" + raw).encode()).hexdigest()
    cards = db.scalars(select(MembershipCard).where(MembershipCard.source == SOURCE,
                        MembershipCard.store_id == STORE_ID, MembershipCard.source_card_key == key)
                        .with_for_update(read=True)).all()
    require(len(cards) == 1, "card_identity_not_unique")
    users = db.scalars(select(User).where(User.phone == phone).with_for_update(read=True)).all()
    require(len(users) == 1 and cards[0].user_id == users[0].id, "phone_owner_conflict")
    return cards[0], users[0]


def packet_sha256(packet):
    data = asdict(packet)
    data.pop("manifest_sha256")
    def normalize(value):
        if isinstance(value, datetime):
            return timestamp(value).isoformat()
        if isinstance(value, Decimal):
            return int(value) if value == int(value) else format(value, "f")
        raise TypeError("unsupported_packet_value")
    return sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(",", ":"),default=normalize).encode()).hexdigest()


def execute(sessions, packet: FinancialBatch, *, apply=False, protection=None):
    require(type(apply) is bool, "invalid_apply_mode")
    require(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", packet.batch_key) is not None, "invalid_batch_key")
    for value in (packet.source_snapshot_sha256, packet.manifest_sha256):
        require(re.fullmatch(r"[a-f0-9]{64}", value) is not None, "invalid_evidence_sha")
    require(packet_sha256(packet) == packet.manifest_sha256, "manifest_content_mismatch")
    reference(packet.evidence_ref)
    start, end, observed = map(timestamp, (packet.query_range_start, packet.query_range_end, packet.observed_at))
    require(start <= end and type(packet.page_count) is int and packet.page_count > 0,
            "query_coverage_invalid")
    require(packet.last_page_complete is True and type(packet.coverage_gaps) is dict, "pagination_incomplete")
    require(bool(packet.bills or packet.balances), "empty_batch")
    require(bool(packet.coverage_gaps), "full_history_coverage_not_certified")
    with sessions() as db, db.begin():
        if db.bind.dialect.name == "postgresql":
            # Serialize this new importer only; never change schema or permissions.
            db.execute(text("SELECT pg_advisory_xact_lock(1581453, 20261115)"))
        if protection is not None:
            protection.before(db)
        store = db.get(Store, STORE_ID)
        require(store is not None and store.store_code == STORE_CODE, "target_store_conflict")
        previous = db.scalar(select(MembershipConsumptionBatch).where(
            MembershipConsumptionBatch.source == SOURCE, MembershipConsumptionBatch.store_id == STORE_ID,
            MembershipConsumptionBatch.batch_key == packet.batch_key))
        if previous:
            require(previous.status == "applied" and previous.manifest_sha256 == packet.manifest_sha256
                    and previous.source_snapshot_sha256 == packet.source_snapshot_sha256, "batch_identity_conflict")
            return {"status": "already_applied", "insert_bills": 0, "insert_balances": 0, "business_writes": 0}
        bill_rows, balance_rows, seen, conflicts = [], [], set(), set()
        for item in packet.bills:
            reference(item.evidence_ref)
            card, user = owner(db, item.card_number, item.phone)
            source = item.bill
            require(source.store_id == STORE_ID and source.user_id is None and not source.linked_card_ids,
                    "caller_must_not_supply_target_identity")
            require(type(source.source_bill_no) is str and 0 < len(source.source_bill_no) <= 128,
                    "invalid_bill_number")
            require(re.fullmatch(r"[a-f0-9]{64}", source.source_row_sha256) is not None, "invalid_row_sha")
            timestamp(source.occurred_at)
            if source.settled_at is not None:
                timestamp(source.settled_at)
            require(source.attribution_status in ("owned", "shared", "unresolved"), "invalid_attribution")
            require(source.bill_type in ("service", "open_card", "package", "recharge", "unknown")
                    and source.bill_status in ("normal_settled", "voided", "reversed", "unknown")
                    and source.refund_status in ("none", "partial", "refunded", "void", "unknown"), "invalid_bill_state")
            require(source.currency == "CNY" and type(source.payment_evidence_complete) is bool, "invalid_currency_or_payment_flag")
            for name, maximum in (("source_bill_version",64),("source_current_marker",32)):
                value = getattr(source,name)
                require(value is None or (type(value) is str and 0 < len(value) <= maximum), "invalid_source_version")
            require(source.source_version_no is None or (type(source.source_version_no) is int and 0 <= source.source_version_no <= 2**31-1), "invalid_source_version")
            for field in ("store_price_total_cents", "settled_total_cents", "coupon_payment_cents",
                          "card_principal_debit_cents", "card_bonus_debit_cents", "cash_payment_cents", "other_payment_cents"):
                cents(getattr(source, field))
            for position, line in enumerate(source.lines, 1):
                require(type(line.line_order) is int and line.line_order == position, "line_order_must_be_contiguous")
                require(type(line.description) is str and 0 < len(line.description) <= 255, "invalid_line_description")
                require(line.source_line_key is None or (type(line.source_line_key) is str and 0 < len(line.source_line_key) <= 128), "invalid_source_line_key")
                cents(line.store_price_cents)
                cents(line.settled_cents)
                require(line.quantity is None or (type(line.quantity) in (int, Decimal) and line.quantity > 0 and line.quantity <= Decimal("999999999.999") and line.quantity * 1000 == int(line.quantity * 1000)),
                        "invalid_line_quantity")
            normalized_lines = tuple(replace(line, quantity=int(line.quantity)
                if line.quantity is not None and line.quantity == int(line.quantity) else line.quantity) for line in source.lines)
            bill = replace(source, user_id=user.id if source.attribution_status == "owned" else None,
                           linked_card_ids=(card.id,), lines=normalized_lines)
            require(compute_bill_savings(bill).status != "anomaly", "bill_amount_reconciliation_failed")
            digest = bill_content_sha256(bill)
            identity = (bill.source_bill_no, digest)
            if identity in seen:
                continue
            seen.add(identity)
            existing = db.scalars(select(MembershipConsumptionBill).where(
                MembershipConsumptionBill.source == SOURCE, MembershipConsumptionBill.store_id == STORE_ID,
                MembershipConsumptionBill.source_bill_no == bill.source_bill_no)).all()
            for old in existing:
                old_lines = db.scalars(select(MembershipConsumptionLine).where(
                    MembershipConsumptionLine.bill_id == old.id).order_by(MembershipConsumptionLine.line_order, MembershipConsumptionLine.id)).all()
                require(bill_content_sha256(to_domain_bill(old, old_lines)) == old.content_sha256,
                        "existing_bill_integrity_failed")
            if any(old.content_sha256 == digest for old in existing):
                continue
            if existing or any(old[0].source_bill_no == bill.source_bill_no for old in bill_rows):
                conflicts.add(bill.source_bill_no)
            bill_rows.append((bill, digest, item.evidence_ref, card.id))
        seen_balances = {}
        for item in packet.balances:
            reference(item.evidence_ref)
            card, _ = owner(db, item.card_number, item.phone)
            at = timestamp(item.observed_at)
            require(at <= observed, "observation_after_batch")
            values = (item.total_cents, item.principal_cents, item.bonus_cents)
            for value in values:
                cents(value)
            require(any(value is not None for value in values), "balance_evidence_missing")
            if all(value is not None for value in values):
                require(values[0] == values[1] + values[2], "balance_split_conflict")
            identity = (card.id, at)
            if identity in seen_balances:
                require(seen_balances[identity] == values, "balance_observation_conflict")
                continue
            seen_balances[identity] = values
            old = db.scalars(select(MembershipBalanceSnapshot).where(MembershipBalanceSnapshot.card_id == card.id,
                    MembershipBalanceSnapshot.source == SOURCE, MembershipBalanceSnapshot.store_id == STORE_ID,
                    MembershipBalanceSnapshot.observed_at == at)).all()
            require(all((row.total_cents,row.principal_cents,row.bonus_cents) == values for row in old),
                    "balance_observation_conflict")
            if not old:
                balance_rows.append((card.id, item))
        report = {"status": "preview", "insert_bills": len(bill_rows), "insert_balances": len(balance_rows),
                  "insert_lines": sum(len(item[0].lines) for item in bill_rows),
                  "conflicting_bill_groups": len(conflicts), "business_writes": 0}
        if not bill_rows and not balance_rows:
            return dict(report, status="no_new")
        if not apply:
            return report
        batch = MembershipConsumptionBatch(source=SOURCE, store_id=STORE_ID, batch_key=packet.batch_key,
                source_snapshot_sha256=packet.source_snapshot_sha256, manifest_sha256=packet.manifest_sha256,
                query_range_start=start, query_range_end=end, observed_at=observed, page_count=packet.page_count,
                last_page_complete=True, coverage_gaps=packet.coverage_gaps, status="applied", evidence_ref=packet.evidence_ref)
        db.add(batch)
        db.flush()
        for bill, digest, ref, card_id in bill_rows:
            fields = {name: getattr(bill,name) for name in ("source_bill_no", "source_row_sha256", "bill_type", "bill_status",
                "source_bill_version", "source_version_no", "source_current_marker", "currency", "occurred_at", "settled_at",
                "store_price_total_cents", "settled_total_cents", "payment_evidence_complete", "coupon_payment_cents",
                "card_principal_debit_cents", "card_bonus_debit_cents", "cash_payment_cents", "other_payment_cents",
                "user_id", "attribution_status", "refund_status")}
            row = MembershipConsumptionBill(batch_id=batch.id, source=SOURCE, store_id=STORE_ID,
                    card_id=card_id, content_sha256=digest, raw_evidence_ref=ref, **fields)
            db.add(row)
            db.flush()
            for position, line in enumerate(bill.lines):
                require(line.line_order == position + 1, "line_order_must_be_contiguous")
                line_fields = {name:getattr(line,name) for name in ("description", "quantity", "store_price_cents", "settled_cents", "source_line_key", "line_order")}
                line_sha = sha256(json.dumps(line_fields,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()
                db.add(MembershipConsumptionLine(bill_id=row.id, line_sha256=line_sha, **line_fields))
        for card_id, item in balance_rows:
            db.add(MembershipBalanceSnapshot(card_id=card_id, source=SOURCE, store_id=STORE_ID,
                observed_at=item.observed_at, total_cents=item.total_cents, principal_cents=item.principal_cents,
                bonus_cents=item.bonus_cents, source_batch_id=batch.id, evidence_ref=item.evidence_ref))
        require(not db.dirty and not db.deleted and all(isinstance(row, NEW_MODELS) for row in db.new),
                "append_only_guard_failed")
        db.flush()
        if protection is not None:
            protection.after(db)
        return dict(report, status="applied", business_writes=len(bill_rows)+len(balance_rows)+report["insert_lines"]+1)
