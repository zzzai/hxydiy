from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    MembershipCard,
    MembershipConsumptionBatch,
    MembershipConsumptionBill,
    MembershipConsumptionLine,
    Store,
    User,
)
from app.services.customer_consumption import content_sha256_for


@pytest.fixture
def consumption_env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with factory() as db:
        store = Store(store_code="consumption-1", name="紫薇壹号店", address="Synthetic")
        other_store = Store(store_code="consumption-2", name="Other", address="Synthetic")
        db.add_all([store, other_store]); db.flush()
        owner = User(openid="consumption-owner", nickname="阿悦", phone="13800138001")
        other = User(openid="consumption-other", nickname="另一位", phone="13800138002")
        db.add_all([owner, other]); db.flush()
        db.add(MembershipCard(user_id=owner.id, store_id=store.id, source="meiguanjia_export",
                              source_card_key="stored-owner", card_type="stored",
                              started_at=now - timedelta(days=20), expires_at=None,
                              balance_cents=15000, status="active", observed_at=now))
        db.flush()
        batch = MembershipConsumptionBatch(
            source="meiguanjia_export", store_id=store.id, batch_key="SYN-BATCH",
            source_snapshot_sha256="s" * 64, manifest_sha256="m" * 64,
            query_range_start=now - timedelta(days=90), query_range_end=now,
            last_page_complete=True, observed_at=now, status="applied", evidence_ref="redacted-ref",
        )
        db.add(batch); db.flush()

        def add_bill(bill_no, *, user_id=None, store_id=None, bill_type="service",
                     bill_status="normal_settled", attribution="owned", refund="none",
                     currency="CNY", store_total=30000, settled=24000, coupon=9000,
                     card_principal=15000, line_price=30000, line_settled=24000,
                     quantity=1, payment_complete=True, source_row=None):
            bill = MembershipConsumptionBill(
                batch_id=batch.id, source="meiguanjia_export",
                store_id=store_id if store_id is not None else store.id,
                source_bill_no=bill_no, bill_type=bill_type, bill_status=bill_status,
                occurred_at=now - timedelta(days=1), settled_at=now - timedelta(days=1),
                currency=currency, store_price_total_cents=store_total, settled_total_cents=settled,
                payment_evidence_complete=payment_complete, coupon_payment_cents=coupon,
                card_principal_debit_cents=card_principal, card_bonus_debit_cents=0,
                cash_payment_cents=0, other_payment_cents=0,
                user_id=user_id if user_id is not None else owner.id,
                attribution_status=attribution, refund_status=refund,
                source_row_sha256=source_row or f"row-{bill_no}", content_sha256="",
                raw_evidence_ref="redacted",
            )
            db.add(bill); db.flush()
            line = MembershipConsumptionLine(
                bill_id=bill.id, line_order=1, description="合成服务",
                quantity=quantity, store_price_cents=line_price, settled_cents=line_settled,
                line_sha256=f"line-{bill_no}",
            )
            db.add(line); db.flush()
            bill.content_sha256 = content_sha256_for(bill, [line])
            return bill

        add_bill("SYN-V1")  # savings 6000
        add_bill("SYN-V2", store_total=11900, settled=7900, coupon=0, card_principal=7900,
                 line_price=11900, line_settled=7900)  # savings 4000
        # conflict group: same bill number, different semantic content, both valid hashes
        add_bill("SYN-CONFLICT")
        add_bill("SYN-CONFLICT", settled=23000, coupon=9000, card_principal=14000, line_settled=23000)
        add_bill("SYN-SHARED", attribution="shared")
        add_bill("SYN-OTHER", user_id=other.id)
        add_bill("SYN-OTHER-STORE", store_id=other_store.id)
        db.commit()
        owner_token = create_access_token(str(owner.id), owner.openid, owner.customer_login_version)
        other_token = create_access_token(str(other.id), other.openid, other.customer_login_version)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, factory, owner_token, other_token, owner.id, other.id
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _get(client, token):
    return client.get("/api/v1/auth/h5/membership-consumption", headers=_headers(token))


def _bill(body, bill_no):
    return next((b for b in body["bills"] if b["source_bill_no"] == bill_no), None)


def test_positive_baseline_verified_savings(consumption_env):
    client, factory, owner_token, other_token, owner_id, other_id = consumption_env
    body = _get(client, owner_token).json()
    assert body["coverage"]["history"] == "returned"
    assert body["coverage"]["applied_batch_count"] == 1
    assert body["coverage"]["complete"] is True
    assert body["coverage"]["query_range_start"] and body["coverage"]["query_range_end"]
    assert body["coverage"]["conflict_bill_groups"] == 1
    assert {b["source_bill_no"] for b in body["bills"]} == {"SYN-V1", "SYN-V2"}
    assert _bill(body, "SYN-V1")["savings"] == {"status": "verified", "amount_cents": 6000, "reason": None}
    assert _bill(body, "SYN-V2")["savings"]["amount_cents"] == 4000
    assert body["savings"]["amount_cents"] == 10000
    assert body["savings"]["bill_count"] == 2


def test_preview_batch_does_not_become_customer_facts(consumption_env):
    client, factory, owner_token, other_token, owner_id, other_id = consumption_env
    with factory() as db:
        for batch in db.scalars(select(MembershipConsumptionBatch)):
            batch.status = "preview"
        db.commit()
    body = _get(client, owner_token).json()
    assert body["bills"] == []
    assert body["savings"]["amount_cents"] is None
    assert body["coverage"]["history"] == "no_source_data"
    assert body["coverage"]["applied_batch_count"] == 0


def test_cross_owner_conflicting_version_excluded(consumption_env):
    client, factory, owner_token, other_token, owner_id, other_id = consumption_env
    with factory() as db:
        row = db.scalar(select(MembershipConsumptionBill).where(MembershipConsumptionBill.source_bill_no == "SYN-V1"))
        line = db.scalar(select(MembershipConsumptionLine).where(MembershipConsumptionLine.bill_id == row.id))
        copy = MembershipConsumptionBill(
            batch_id=row.batch_id, source=row.source, store_id=row.store_id,
            source_bill_no=row.source_bill_no, bill_type=row.bill_type, bill_status=row.bill_status,
            occurred_at=row.occurred_at, settled_at=row.settled_at, currency=row.currency,
            store_price_total_cents=row.store_price_total_cents, settled_total_cents=row.settled_total_cents,
            payment_evidence_complete=row.payment_evidence_complete,
            coupon_payment_cents=row.coupon_payment_cents, card_principal_debit_cents=row.card_principal_debit_cents,
            card_bonus_debit_cents=0, cash_payment_cents=0, other_payment_cents=0,
            user_id=other_id, attribution_status="owned", refund_status="none",
            source_row_sha256=row.source_row_sha256, content_sha256="", raw_evidence_ref="redacted",
        )
        db.add(copy); db.flush()
        copy_line = MembershipConsumptionLine(
            bill_id=copy.id, line_order=1, description=line.description, quantity=line.quantity,
            store_price_cents=line.store_price_cents, settled_cents=line.settled_cents, line_sha256="line-copy",
        )
        db.add(copy_line); db.flush()
        copy.content_sha256 = content_sha256_for(copy, [copy_line])
        db.commit()
    body = _get(client, owner_token).json()
    assert _bill(body, "SYN-V1") is None  # alternate-owner conflict excludes the whole group
    assert body["savings"]["amount_cents"] == 4000  # only SYN-V2 remains verified


def test_fractional_quantity_is_unknown_not_verified(consumption_env):
    client, factory, owner_token, other_token, owner_id, other_id = consumption_env
    with factory() as db:
        line = db.scalar(select(MembershipConsumptionLine).join(MembershipConsumptionBill).where(MembershipConsumptionBill.source_bill_no == "SYN-V1"))
        line.quantity = Decimal("1.5")
        bill = line.bill_id and db.get(MembershipConsumptionBill, line.bill_id)
        bill.content_sha256 = content_sha256_for(bill, [line])
        db.commit()
    body = _get(client, owner_token).json()
    v1 = _bill(body, "SYN-V1")
    assert v1 is not None
    assert v1["savings"]["amount_cents"] is None
    assert v1["savings"]["status"] != "verified"


def test_known_bill_visible_when_payment_evidence_incomplete(consumption_env):
    client, factory, owner_token, other_token, owner_id, other_id = consumption_env
    with factory() as db:
        row = db.scalar(select(MembershipConsumptionBill).where(MembershipConsumptionBill.source_bill_no == "SYN-V1"))
        row.payment_evidence_complete = False
        row.content_sha256 = content_sha256_for(row, list(db.scalars(select(MembershipConsumptionLine).where(MembershipConsumptionLine.bill_id == row.id))))
        db.commit()
    body = _get(client, owner_token).json()
    v1 = _bill(body, "SYN-V1")
    assert v1 is not None  # still visible history
    assert v1["savings"]["amount_cents"] is None
    assert v1["savings"]["status"] == "unknown"
    assert body["savings"]["amount_cents"] == 4000  # SYN-V1 excluded from aggregate


def test_foreign_currency_not_mixed_into_cny_savings(consumption_env):
    client, factory, owner_token, other_token, owner_id, other_id = consumption_env
    with factory() as db:
        row = db.scalar(select(MembershipConsumptionBill).where(MembershipConsumptionBill.source_bill_no == "SYN-V1"))
        row.currency = "USD"
        row.content_sha256 = content_sha256_for(row, list(db.scalars(select(MembershipConsumptionLine).where(MembershipConsumptionLine.bill_id == row.id))))
        db.commit()
    body = _get(client, owner_token).json()
    v1 = _bill(body, "SYN-V1")
    assert v1 is not None
    assert v1["currency"] == "USD"
    assert v1["savings"]["amount_cents"] is None
    assert v1["savings"]["status"] != "verified"
    assert body["savings"]["amount_cents"] == 4000  # only CNY SYN-V2


def test_stale_content_sha256_recomputes_actual_facts(consumption_env):
    client, factory, owner_token, other_token, owner_id, other_id = consumption_env
    with factory() as db:
        row = db.scalar(select(MembershipConsumptionBill).where(MembershipConsumptionBill.source_bill_no == "SYN-V1"))
        row.payment_evidence_complete = False  # mutate fact without updating persisted digest
        db.commit()
    body = _get(client, owner_token).json()
    v1 = _bill(body, "SYN-V1")
    assert v1 is not None
    assert v1["savings"]["amount_cents"] is None
    assert v1["savings"]["status"] != "verified"
    assert body["savings"]["amount_cents"] == 4000


def test_auth_required_and_other_user_isolated(consumption_env):
    client, factory, owner_token, other_token, owner_id, other_id = consumption_env
    assert client.get("/api/v1/auth/h5/membership-consumption").status_code == 401
    body = _get(client, other_token).json()
    assert {b["source_bill_no"] for b in body["bills"]} == {"SYN-OTHER"}
    assert body["savings"]["amount_cents"] == 6000
    # spoofed params must not select another customer
    spoof = _get(client, owner_token).json()
    assert {b["source_bill_no"] for b in spoof["bills"]} == {"SYN-V1", "SYN-V2"}


def test_no_write(consumption_env):
    client, factory, owner_token, other_token, owner_id, other_id = consumption_env
    with factory() as db:
        before = [b.id for b in db.scalars(select(MembershipConsumptionBill).order_by(MembershipConsumptionBill.id))]
    _get(client, owner_token)
    with factory() as db:
        after = [b.id for b in db.scalars(select(MembershipConsumptionBill).order_by(MembershipConsumptionBill.id))]
    assert after == before
