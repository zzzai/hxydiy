from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    MembershipBalanceSnapshot,
    MembershipCard,
    MembershipConsumptionBatch,
    Store,
    User,
)


@pytest.fixture
def balance_env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with factory() as db:
        store = Store(store_code="bal-1", name="紫薇壹号店", address="Synthetic")
        other_store = Store(store_code="bal-2", name="Other", address="Synthetic")
        db.add_all([store, other_store]); db.flush()
        owner = User(openid="bal-owner", nickname="阿悦", phone="13800138001")
        other = User(openid="bal-other", nickname="另一位", phone="13800138002")
        db.add_all([owner, other]); db.flush()
        card = MembershipCard(user_id=owner.id, store_id=store.id, source="meiguanjia_export",
                              source_card_key="stored-owner", card_type="stored",
                              started_at=now - timedelta(days=30), expires_at=None,
                              balance_cents=15000, status="active",
                              observed_at=now - timedelta(days=10))
        other_card = MembershipCard(user_id=other.id, store_id=store.id, source="meiguanjia_export",
                                    source_card_key="stored-other", card_type="stored",
                                    started_at=now - timedelta(days=30), expires_at=None,
                                    balance_cents=8800, status="active", observed_at=now - timedelta(days=5))
        db.add_all([card, other_card]); db.flush()

        applied = MembershipConsumptionBatch(source="meiguanjia_export", store_id=store.id, batch_key="applied",
                                             source_snapshot_sha256="s" * 64, manifest_sha256="m" * 64,
                                             query_range_start=now - timedelta(days=90), query_range_end=now,
                                             observed_at=now, status="applied", evidence_ref="redacted")
        applied2 = MembershipConsumptionBatch(source="meiguanjia_export", store_id=store.id, batch_key="applied-2",
                                              source_snapshot_sha256="s" * 64, manifest_sha256="m" * 64,
                                              query_range_start=now - timedelta(days=90), query_range_end=now,
                                              observed_at=now, status="applied", evidence_ref="redacted")
        preview = MembershipConsumptionBatch(source="meiguanjia_export", store_id=store.id, batch_key="preview",
                                             source_snapshot_sha256="s" * 64, manifest_sha256="m" * 64,
                                             query_range_start=now - timedelta(days=90), query_range_end=now,
                                             observed_at=now, status="preview", evidence_ref="redacted")
        other_store_batch = MembershipConsumptionBatch(source="meiguanjia_export", store_id=other_store.id, batch_key="other-store",
                                                       source_snapshot_sha256="s" * 64, manifest_sha256="m" * 64,
                                                       query_range_start=now - timedelta(days=90), query_range_end=now,
                                                       observed_at=now, status="applied", evidence_ref="redacted")
        other_source_batch = MembershipConsumptionBatch(source="other_source", store_id=store.id, batch_key="other-source",
                                                        source_snapshot_sha256="s" * 64, manifest_sha256="m" * 64,
                                                        query_range_start=now - timedelta(days=90), query_range_end=now,
                                                        observed_at=now, status="applied", evidence_ref="redacted")
        db.add_all([applied, applied2, preview, other_store_batch, other_source_batch]); db.flush()

        def add_snapshot(card_row, batch_row, observed_at, *, principal=None, bonus=None, total=None, source="meiguanjia_export", store_id=None):
            snap = MembershipBalanceSnapshot(
                card_id=card_row.id, source=source, store_id=store_id if store_id is not None else card_row.store_id,
                observed_at=observed_at, principal_cents=principal, bonus_cents=bonus, total_cents=total,
                source_batch_id=batch_row.id, evidence_ref="redacted",
            )
            db.add(snap)
            return snap

        db.commit()
        owner_token = create_access_token(str(owner.id), owner.openid, owner.customer_login_version)
        other_token = create_access_token(str(other.id), other.openid, other.customer_login_version)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, factory, owner_token, other_token, {"applied": applied, "applied2": applied2, "preview": preview,
                                                           "other_store": other_store_batch, "other_source": other_source_batch}, card, other_card
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _balance(client, token, card_id):
    body = client.get("/api/v1/auth/h5/membership-overview", headers=_headers(token)).json()
    return next(card["balance"] for card in body["cards"] if card["id"] == card_id)


def test_eligible_snapshot_projected_with_split_and_original(balance_env):
    client, factory, owner_token, other_token, batches, card, other_card = balance_env
    now = datetime.now(UTC)
    with factory() as db:
        db.add(MembershipBalanceSnapshot(card_id=card.id, source="meiguanjia_export", store_id=card.store_id,
                                         observed_at=now - timedelta(days=1), principal_cents=8000, bonus_cents=2000,
                                         total_cents=10000, source_batch_id=batches["applied"].id, evidence_ref="redacted"))
        db.commit()
    balance = _balance(client, owner_token, card.id)
    assert balance["evidence"] == "balance_snapshot"
    assert balance["status"] == "observed"
    assert balance["amount_cents"] == 10000
    assert balance["principal_cents"] == 8000
    assert balance["bonus_cents"] == 2000
    assert balance["split"] == "verified"
    assert balance["original"] == {"amount_cents": 15000, "observed_at": balance["original"]["observed_at"]}
    assert balance["original"]["amount_cents"] == 15000


def test_newest_eligible_snapshot_wins(balance_env):
    client, factory, owner_token, other_token, batches, card, other_card = balance_env
    now = datetime.now(UTC)
    with factory() as db:
        db.add(MembershipBalanceSnapshot(card_id=card.id, source="meiguanjia_export", store_id=card.store_id,
                                         observed_at=now - timedelta(days=2), total_cents=9000,
                                         source_batch_id=batches["applied"].id, evidence_ref="redacted"))
        db.add(MembershipBalanceSnapshot(card_id=card.id, source="meiguanjia_export", store_id=card.store_id,
                                         observed_at=now - timedelta(hours=1), total_cents=11000,
                                         source_batch_id=batches["applied"].id, evidence_ref="redacted"))
        db.commit()
    balance = _balance(client, owner_token, card.id)
    assert balance["amount_cents"] == 11000


def test_same_time_conflict_is_unknown_and_keeps_original(balance_env):
    client, factory, owner_token, other_token, batches, card, other_card = balance_env
    now = datetime.now(UTC)
    at = now - timedelta(days=1)
    with factory() as db:
        db.add(MembershipBalanceSnapshot(card_id=card.id, source="meiguanjia_export", store_id=card.store_id,
                                         observed_at=at, total_cents=10000, source_batch_id=batches["applied"].id, evidence_ref="redacted"))
        db.add(MembershipBalanceSnapshot(card_id=card.id, source="meiguanjia_export", store_id=card.store_id,
                                         observed_at=at, total_cents=12000, source_batch_id=batches["applied2"].id, evidence_ref="redacted"))
        db.commit()
    balance = _balance(client, owner_token, card.id)
    assert balance["status"] == "conflicted"
    assert balance["amount_cents"] is None
    assert balance["split"] == "unknown"
    assert balance["original"]["amount_cents"] == 15000


def test_preview_or_other_scope_batches_are_excluded(balance_env):
    client, factory, owner_token, other_token, batches, card, other_card = balance_env
    now = datetime.now(UTC)
    with factory() as db:
        db.add(MembershipBalanceSnapshot(card_id=card.id, source="meiguanjia_export", store_id=card.store_id,
                                         observed_at=now - timedelta(days=1), total_cents=9999,
                                         source_batch_id=batches["preview"].id, evidence_ref="redacted"))
        db.add(MembershipBalanceSnapshot(card_id=card.id, source="meiguanjia_export", store_id=2,
                                         observed_at=now - timedelta(days=1), total_cents=7777,
                                         source_batch_id=batches["other_store"].id, evidence_ref="redacted"))
        db.add(MembershipBalanceSnapshot(card_id=card.id, source="other_source", store_id=card.store_id,
                                         observed_at=now - timedelta(days=1), total_cents=5555,
                                         source_batch_id=batches["other_source"].id, evidence_ref="redacted"))
        db.commit()
    balance = _balance(client, owner_token, card.id)
    # no eligible snapshot -> original card fact with its true original date
    assert balance["evidence"] == "card_fact"
    assert balance["amount_cents"] == 15000


def test_null_total_is_not_zero_and_not_principal(balance_env):
    client, factory, owner_token, other_token, batches, card, other_card = balance_env
    now = datetime.now(UTC)
    with factory() as db:
        db.add(MembershipBalanceSnapshot(card_id=card.id, source="meiguanjia_export", store_id=card.store_id,
                                         observed_at=now - timedelta(days=1), principal_cents=None, bonus_cents=None,
                                         total_cents=None, source_batch_id=batches["applied"].id, evidence_ref="redacted"))
        db.commit()
    balance = _balance(client, owner_token, card.id)
    assert balance["status"] == "observed"
    assert balance["amount_cents"] is None
    assert balance["principal_cents"] is None
    assert balance["bonus_cents"] is None
    assert balance["split"] == "unverified"
