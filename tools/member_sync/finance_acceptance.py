"""Verify incremental append counts and customer ownership, retaining prior history."""
from collections import defaultdict
from datetime import datetime, UTC
from sqlalchemy import select
from app.models import (User, MembershipConsumptionBill, MembershipConsumptionLine,
                        MembershipBalanceSnapshot)
from app.services.member_financial_import import SOURCE, STORE_ID, owner
from app.services.customer_consumption import build_customer_consumption_history
from app.services.customer_membership import build_customer_membership_overview


def expected_counts(preview):
    if preview.get("status") != "preview" or preview.get("business_writes") != 0:
        raise ValueError("preview_not_readonly")
    if preview.get("conflicting_bill_groups") != 0:
        raise ValueError("source_revision_conflict")
    result = {"membership_consumption_batches": 1}
    for field, table in (("insert_bills", "membership_consumption_bills"),
                         ("insert_lines", "membership_consumption_lines"),
                         ("insert_balances", "membership_balance_snapshots")):
        value = preview.get(field)
        if type(value) is not int or value < 0:
            raise ValueError("preview_count_invalid")
        result[table] = value
    return result


def verify_projection(db, packet, batch, preview):
    expected = expected_counts(preview)
    if batch.source != SOURCE or batch.store_id != STORE_ID or batch.status != "applied" or batch.manifest_sha256 != packet.manifest_sha256:
        raise ValueError("batch_identity_mismatch")
    bills = list(db.scalars(select(MembershipConsumptionBill).where(MembershipConsumptionBill.batch_id == batch.id)))
    balances = list(db.scalars(select(MembershipBalanceSnapshot).where(MembershipBalanceSnapshot.source_batch_id == batch.id)))
    lines = list(db.scalars(select(MembershipConsumptionLine).where(MembershipConsumptionLine.bill_id.in_([b.id for b in bills]))))
    if (len(bills), len(lines), len(balances)) != (expected["membership_consumption_bills"], expected["membership_consumption_lines"], expected["membership_balance_snapshots"]):
        raise ValueError("actual_count_mismatch")
    expected_bills, user_ids = defaultdict(set), set()
    for item in packet.bills:
        _, user = owner(db, item.card_number, item.phone)
        expected_bills[user.id].add(item.bill.source_bill_no)
        user_ids.add(user.id)
    for item in packet.balances:
        _, user = owner(db, item.card_number, item.phone)
        user_ids.add(user.id)
    visible = 0
    checked_balances = set()
    for user_id in user_ids:
        user = db.get(User, user_id)
        history = build_customer_consumption_history(db, user, limit=5000)
        actual = {bill["source_bill_no"] for bill in history["bills"]}
        if not expected_bills[user_id].issubset(actual):
            raise ValueError("customer_history_projection_mismatch")
        # Existing rows outside this input remain legitimate history. Every visible
        # row must still belong to this customer and the exact approved source/store.
        for item in history["bills"]:
            row = db.get(MembershipConsumptionBill, item["id"])
            if row is None or row.user_id != user_id or row.store_id != STORE_ID or row.source != SOURCE:
                raise ValueError("customer_history_owner_leak")
        if history["savings"]["amount_cents"] is not None:
            raise ValueError("unverified_savings_became_verified")
        visible += len(actual)
        overview = build_customer_membership_overview(db, user)
        by_card = {card["id"]: card for card in overview["cards"]}
        for balance in balances:
            if balance.card_id in by_card:
                display = by_card[balance.card_id]["balance"]
                if display["amount_cents"] != balance.total_cents or display["evidence"] != "balance_snapshot" or display["observed_at"] is None:
                    raise ValueError("customer_balance_projection_mismatch")
                observed = balance.observed_at.replace(tzinfo=UTC) if balance.observed_at.tzinfo is None else balance.observed_at
                if datetime.fromisoformat(display["observed_at"]) != observed:
                    raise ValueError("customer_balance_timestamp_mismatch")
                checked_balances.add(balance.id)
    if checked_balances != {balance.id for balance in balances}:
        raise ValueError("customer_balance_owner_missing")
    return {"insert_bills":len(bills), "insert_balances":len(balances), "insert_lines":len(lines),
            "visible_owned_bills":visible, "savings_status":"unverified"}
