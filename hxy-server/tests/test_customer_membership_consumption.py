from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    MembershipBalanceSnapshot,
    MembershipCard,
    MembershipConsumptionBatch,
    MembershipConsumptionBill,
    MembershipConsumptionLine,
    Store,
    User,
)


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
            observed_at=now, status="applied", evidence_ref="redacted-ref",
        )
        db.add(batch); db.flush()

        def add_bill(bill_no, content, *, user_id=None, store_id=None, bill_type="service",
                     bill_status="normal_settled", attribution="owned", refund="none",
                     store_total=30000, settled=24000, coupon=9000, card_principal=15000,
                     line_price=30000, line_settled=24000):
            bill = MembershipConsumptionBill(
                batch_id=batch.id, source="meiguanjia_export",
                store_id=store_id if store_id is not None else store.id,
                source_bill_no=bill_no, bill_type=bill_type, bill_status=bill_status,
                occurred_at=now - timedelta(days=1), settled_at=now - timedelta(days=1),
                currency="CNY", store_price_total_cents=store_total, settled_total_cents=settled,
                payment_evidence_complete=True, coupon_payment_cents=coupon,
                card_principal_debit_cents=card_principal, card_bonus_debit_cents=0,
                cash_payment_cents=0, other_payment_cents=0,
                user_id=user_id if user_id is not None else owner.id,
                attribution_status=attribution, refund_status=refund,
                source_row_sha256=f"row-{bill_no}", content_sha256=content,
                raw_evidence_ref="redacted",
            )
            db.add(bill); db.flush()
            db.add(MembershipConsumptionLine(
                bill_id=bill.id, line_order=1, description="合成服务",
                quantity=1, store_price_cents=line_price, settled_cents=line_settled,
                line_sha256=f"line-{bill_no}",
            ))
            return bill

        # two clean verified bills for the owner: savings 6000 + 4000
        add_bill("SYN-V1", "c1")
        add_bill("SYN-V2", "c2", store_total=11900, settled=7900, coupon=0, card_principal=7900,
                 line_price=11900, line_settled=7900)
        # conflict group: same bill number, different semantic content
        add_bill("SYN-CONFLICT", "cx")
        add_bill("SYN-CONFLICT", "cy", settled=23000, coupon=9000, card_principal=14000,
                 line_settled=23000)
        # shared attribution must not count as personal verified history
        add_bill("SYN-SHARED", "cs", attribution="shared")
        # another user's bill must not leak
        add_bill("SYN-OTHER", "co", user_id=other.id)
        # a bill in a different store must not leak into store scope
        add_bill("SYN-OTHER-STORE", "cos", store_id=other_store.id)
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


def test_consumption_history_is_self_only_and_verified_only(consumption_env):
    client, factory, owner_token, other_token, owner_id, other_id = consumption_env
    response = client.get("/api/v1/auth/h5/membership-consumption", headers=_headers(owner_token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["read_only"] is True
    assert body["coverage"]["history"] == "returned"
    assert body["coverage"]["store_ids"] == [1]
    assert body["coverage"]["conflict_bill_groups"] == 1
    bill_nos = [bill["source_bill_no"] for bill in body["bills"]]
    assert set(bill_nos) == {"SYN-V1", "SYN-V2"}  # conflict/shared/other-user/other-store excluded
    assert body["savings"]["status"] == "verified"
    assert body["savings"]["amount_cents"] == 10000
    assert body["savings"]["bill_count"] == 2
    assert body["pagination"]["total"] == 2
    # spoofed query params must not select another customer
    spoof = client.get(
        f"/api/v1/auth/h5/membership-consumption?user_id={other_id}&phone=13800138002",
        headers=_headers(owner_token),
    )
    assert spoof.status_code == 200
    assert {b["source_bill_no"] for b in spoof.json()["bills"]} == {"SYN-V1", "SYN-V2"}


def test_consumption_history_requires_auth_and_isolates_other_user(consumption_env):
    client, factory, owner_token, other_token, owner_id, other_id = consumption_env
    assert client.get("/api/v1/auth/h5/membership-consumption").status_code == 401
    other = client.get("/api/v1/auth/h5/membership-consumption", headers=_headers(other_token))
    assert other.status_code == 200
    other_body = other.json()
    # other user sees only their own verified bill, never the owner's bills.
    assert {b["source_bill_no"] for b in other_body["bills"]} == {"SYN-OTHER"}
    assert other_body["savings"]["status"] == "verified"
    assert other_body["savings"]["amount_cents"] == 6000


def test_consumption_history_empty_user_returns_null_not_zero(consumption_env):
    client, factory, owner_token, other_token, owner_id, other_id = consumption_env
    with factory() as db:
        empty = User(openid="consumption-empty", nickname="无记录", phone="13800138003")
        db.add(empty); db.commit()
        empty_token = create_access_token(str(empty.id), empty.openid, empty.customer_login_version)
    response = client.get("/api/v1/auth/h5/membership-consumption", headers=_headers(empty_token))
    assert response.status_code == 200
    body = response.json()
    assert body["coverage"]["history"] == "no_source_data"
    assert body["bills"] == []
    assert body["savings"]["status"] == "unverified"
    assert body["savings"]["amount_cents"] is None


def test_consumption_history_does_not_write(consumption_env):
    client, factory, owner_token, other_token, owner_id, other_id = consumption_env
    with factory() as db:
        before = [b.id for b in db.scalars(select(MembershipConsumptionBill).order_by(MembershipConsumptionBill.id))]
        card_before = [c.balance_cents for c in db.scalars(select(MembershipCard))]
    client.get("/api/v1/auth/h5/membership-consumption", headers=_headers(owner_token))
    with factory() as db:
        after = [b.id for b in db.scalars(select(MembershipConsumptionBill).order_by(MembershipConsumptionBill.id))]
        card_after = [c.balance_cents for c in db.scalars(select(MembershipCard))]
    assert after == before
    assert card_after == card_before
