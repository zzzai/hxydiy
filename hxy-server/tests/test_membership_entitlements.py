from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import Store, User
from app.models import SelectionSession
from app.api.selections import _session_price_type
from app.models.membership import MembershipCard
from app.domain.membership_entitlements import has_membership


NOW = datetime(2026, 9, 28, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Store(id=1, store_code="entitlement-one", name="One", address="Test"),
            Store(id=2, store_code="entitlement-two", name="Two", address="Test"),
            User(id=1, openid="entitlement-user", is_member=False),
            User(id=2, openid="other-user", is_member=False),
        ])
        session.flush()
        yield session
    engine.dispose()


def card(db, key="one", **fields):
    values = dict(user_id=1, store_id=1, source="test", source_card_key=key,
                  card_type="annual", started_at=NOW - timedelta(days=365),
                  expires_at=NOW + timedelta(seconds=1), balance_cents=0, status="active")
    values.update(fields)
    row = MembershipCard(**values)
    db.add(row)
    db.flush()
    return row


@pytest.mark.parametrize("expiry,expected", [(NOW, False), (NOW + timedelta(seconds=1), True)])
def test_annual_expiry_is_exclusive(db, expiry, expected):
    card(db, expires_at=expiry)
    assert has_membership(db, db.get(User, 1), store_id=1, now=NOW) is expected


@pytest.mark.parametrize("balance,expected", [(0, False), (1, True)])
def test_stored_card_requires_positive_principal(db, balance, expected):
    card(db, card_type="stored", expires_at=None, balance_cents=balance)
    assert has_membership(db, db.get(User, 1), store_id=1, now=NOW) is expected


def test_exhausted_card_does_not_cancel_valid_annual_card(db):
    card(db)
    card(db, key="empty", card_type="stored", expires_at=None)
    assert has_membership(db, db.get(User, 1), store_id=1, now=NOW)


def test_expired_annual_does_not_cancel_positive_stored_card(db):
    card(db, expires_at=NOW)
    card(db, key="stored", card_type="stored", expires_at=None, balance_cents=100)
    assert has_membership(db, db.get(User, 1), store_id=1, now=NOW)


def test_card_cannot_grant_other_store_or_other_person_rights(db):
    card(db)
    assert not has_membership(db, db.get(User, 1), store_id=2, now=NOW)
    assert not has_membership(db, db.get(User, 2), store_id=1, now=NOW)
    assert has_membership(db, db.get(User, 1), now=NOW)


@pytest.mark.parametrize("fields", [{"started_at": NOW + timedelta(seconds=1), "expires_at": NOW + timedelta(days=365)}, {"status": "disabled"}])
def test_unstarted_or_disabled_annual_cannot_grant_rights(db, fields):
    card(db, **fields)
    assert not has_membership(db, db.get(User, 1), store_id=1, now=NOW)


def test_legacy_stored_balance_and_independent_annual_are_checked(db):
    user = db.get(User, 1)
    user.is_member, user.member_type, user.balance_cents = True, "stored", 0
    assert not has_membership(db, user, now=NOW)
    user.balance_cents = 1
    assert has_membership(db, user, now=NOW)
    user.member_type, user.member_expire_at = "annual", NOW + timedelta(days=1)
    card(db, card_type="stored", expires_at=None)
    assert has_membership(db, user, store_id=2, now=NOW)


def test_legacy_annual_missing_expiry_cannot_grant_rights(db):
    user = db.get(User, 1)
    user.is_member, user.member_type = True, "annual"
    assert not has_membership(db, user, now=NOW)


def test_selection_requires_dynamic_verification_and_own_store_at_confirmation(db):
    card(db)
    selection = SelectionSession(customer_id=1, store_id=1)
    assert _session_price_type(db, selection, NOW) == "store"
    selection.membership_verified_at = NOW
    assert _session_price_type(db, selection, NOW) == "member"
    assert _session_price_type(db, selection, NOW + timedelta(seconds=1)) == "store"
    selection.store_id = 2
    assert _session_price_type(db, selection, NOW) == "store"
