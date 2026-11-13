from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token
from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models import MembershipCard, Store, User


@pytest.fixture
def customer_membership():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        store = Store(store_code="member-overview-1", name="紫薇壹号店", address="Synthetic")
        other = Store(store_code="member-overview-2", name="Other store", address="Synthetic")
        db.add_all([store, other]); db.flush()
        owner = User(openid="member-overview-owner", nickname="阿悦", phone="13800138001", membership_store_id=store.id)
        other_user = User(openid="member-overview-other", nickname="另一位", phone="13800138002")
        no_card = User(openid="member-overview-empty", nickname="无卡", phone="13800138003", membership_store_id=store.id)
        no_legacy = User(openid="member-overview-no-legacy", nickname="无旧归属", phone="13800138004")
        wrong_legacy = User(openid="member-overview-wrong-legacy", nickname="异店旧归属", phone="13800138005", membership_store_id=other.id)
        db.add_all([owner, other_user, no_card, no_legacy, wrong_legacy]); db.flush()
        now = datetime.now(UTC)
        db.add_all([
            MembershipCard(user_id=owner.id, store_id=store.id, source="meiguanjia_export", source_card_key="annual-owner",
                           card_type="annual", started_at=now - timedelta(days=10), expires_at=now + timedelta(days=355),
                           balance_cents=0, status="active", observed_at=now - timedelta(days=1)),
            MembershipCard(user_id=owner.id, store_id=store.id, source="meiguanjia_export", source_card_key="stored-owner",
                           card_type="stored", started_at=now - timedelta(days=20), expires_at=None,
                           balance_cents=15000, status="active", observed_at=now - timedelta(hours=2)),
            MembershipCard(user_id=owner.id, store_id=other.id, source="meiguanjia_export", source_card_key="stored-other-store",
                           card_type="stored", started_at=now - timedelta(days=20), expires_at=None,
                           balance_cents=9000, status="active", observed_at=now - timedelta(hours=1)),
            MembershipCard(user_id=other_user.id, store_id=store.id, source="meiguanjia_export", source_card_key="stored-other-user",
                           card_type="stored", started_at=now - timedelta(days=20), expires_at=None,
                           balance_cents=8800, status="active", observed_at=now),
            MembershipCard(user_id=owner.id, store_id=store.id, source="manual_other_source", source_card_key="manual-owner",
                           card_type="stored", started_at=now - timedelta(days=20), expires_at=None,
                           balance_cents=7777, status="active", observed_at=now),
            MembershipCard(user_id=no_legacy.id, store_id=store.id, source="meiguanjia_export", source_card_key="no-legacy-owner",
                           card_type="stored", started_at=now - timedelta(days=20), expires_at=None,
                           balance_cents=12345, status="active", observed_at=now),
            MembershipCard(user_id=wrong_legacy.id, store_id=store.id, source="meiguanjia_export", source_card_key="wrong-legacy-owner",
                           card_type="stored", started_at=now - timedelta(days=20), expires_at=None,
                           balance_cents=23456, status="active", observed_at=now),
        ])
        db.commit()
        owner_token = create_access_token(str(owner.id), owner.openid, owner.customer_login_version)
        other_token = create_access_token(str(other_user.id), other_user.openid, other_user.customer_login_version)
        empty_token = create_access_token(str(no_card.id), no_card.openid, no_card.customer_login_version)
        no_legacy_token = create_access_token(str(no_legacy.id), no_legacy.openid, no_legacy.customer_login_version)
        wrong_legacy_token = create_access_token(str(wrong_legacy.id), wrong_legacy.openid, wrong_legacy.customer_login_version)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, factory, {"owner": owner_token, "other": other_token, "empty": empty_token,
                                "no_legacy": no_legacy_token, "wrong_legacy": wrong_legacy_token}, owner.id, other.id
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_customer_membership_overview_is_self_only_and_read_only(customer_membership):
    client, factory, tokens, owner_id, other_id = customer_membership
    before = None
    with factory() as db:
        before = [(card.id, card.balance_cents, card.status) for card in db.scalars(select(MembershipCard).order_by(MembershipCard.id))]
    response = client.get("/api/v1/auth/h5/membership-overview", headers=_headers(tokens["owner"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["identity"]["is_member"] is True
    assert body["card_count"] == 2  # other-store and other-source cards are outside the verified scope
    assert all(card["store_id"] == 1 for card in body["cards"])
    assert all("source_card_key" not in str(card) for card in body["cards"])
    assert body["coverage"]["store_ids"] == [1]
    assert body["coverage"]["returned_store_ids"] == [1]
    annual = next(card for card in body["cards"] if card["card_type"] == "annual")
    stored = next(card for card in body["cards"] if card["card_type"] == "stored")
    assert annual["balance"]["status"] == "not_applicable"
    assert annual["balance"]["amount_cents"] is None
    assert stored["balance"]["status"] == "source_snapshot"
    assert stored["balance"]["amount_cents"] == 15000
    assert stored["balance"]["real_time"] is False
    assert stored["balance"]["split"] == "unverified"
    assert stored["balance"]["observed_at"]
    assert body["consumption"]["status"] == "unverified"
    assert body["consumption"]["amount_cents"] is None
    assert body["savings"]["status"] == "unverified"
    assert body["savings"]["amount_cents"] is None
    assert body["coverage"]["history"] == "unverified"
    stored_benefits = " ".join(stored["benefits"])
    annual_benefits = " ".join(annual["benefits"])
    assert "周二会员活动" in stored_benefits and "周二会员活动" in annual_benefits
    assert "DIY 钱包" not in stored_benefits + annual_benefits
    assert "是否已登记/发放" in annual_benefits
    with factory() as db:
        after = [(card.id, card.balance_cents, card.status) for card in db.scalars(select(MembershipCard).order_by(MembershipCard.id))]
    assert after == before

    other = client.get("/api/v1/auth/h5/membership-overview", headers=_headers(tokens["other"]))
    assert other.status_code == 200
    other_body = other.json()
    assert other_body["card_count"] == 1
    assert other_body["cards"][0]["balance"]["amount_cents"] == 8800
    assert not any(card["id"] == stored["id"] for card in other_body["cards"])

    # Legacy membership_store_id is neither a filter nor a scope denial.
    no_legacy = client.get("/api/v1/auth/h5/membership-overview", headers=_headers(tokens["no_legacy"]))
    assert no_legacy.status_code == 200
    assert no_legacy.json()["card_count"] == 1
    assert no_legacy.json()["cards"][0]["balance"]["amount_cents"] == 12345
    wrong_legacy = client.get("/api/v1/auth/h5/membership-overview", headers=_headers(tokens["wrong_legacy"]))
    assert wrong_legacy.status_code == 200
    assert wrong_legacy.json()["card_count"] == 1
    assert wrong_legacy.json()["cards"][0]["balance"]["amount_cents"] == 23456

    assert client.get("/api/v1/auth/h5/membership-overview").status_code == 401
    empty = client.get("/api/v1/auth/h5/membership-overview", headers=_headers(tokens["empty"]))
    assert empty.status_code == 200
    assert empty.json()["card_count"] == 0
    assert empty.json()["identity"]["is_member"] is False
    assert empty.json()["savings"]["amount_cents"] is None
    # Unknown extra identity parameters must not select another customer.
    spoof = client.get(f"/api/v1/auth/h5/membership-overview?user_id={other_id}&phone=13800138002", headers=_headers(tokens["owner"]))
    assert spoof.status_code == 200
    assert spoof.json()["card_count"] == 2
