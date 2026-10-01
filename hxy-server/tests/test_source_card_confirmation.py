from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch

import pytest

import test_selection_closure_v2 as closure
from app.api.admin import create_staff_token
from app.api.selections import refresh_session_pricing
from app.models import MembershipCard, PositionOccupancy, SelectionChangeRequest, SelectionRevision, SelectionSession, User


NOW = datetime(2026, 9, 29, 2, tzinfo=timezone.utc)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


@pytest.fixture(scope="module")
def api():
    closure.SelectionClosureV2Tests.setUpClass()
    yield closure.SelectionClosureV2Tests
    closure.SelectionClosureV2Tests.tearDownClass()


def make_selection(api, cards, *, verified=True):
    key = uuid4().hex
    with api.SessionLocal() as db:
        user = User(openid=f"price01-{key}", is_member=False)
        db.add(user)
        db.flush()
        for index, fields in enumerate(cards):
            values = dict(user_id=user.id, store_id=api.store_id, source="test",
                          source_card_key=f"{key}-{index}", card_type="stored",
                          balance_cents=100, started_at=NOW - timedelta(days=1), status="active")
            values.update(fields)
            db.add(MembershipCard(**values))
        session = SelectionSession(id=key, access_token_hash=key, store_id=api.store_id,
                                   customer_id=user.id, status="submitted",
                                   items=[{"project_id": api.project_id}], diy_preferences={},
                                   membership_verified_at=NOW if verified else None)
        db.add(session)
        db.flush()
        db.commit()
    return key


@pytest.mark.parametrize("cards,verified,expected,basis", [
    ([{}], True, 2990, "member"),
    ([{"card_type": "annual", "expires_at": NOW + timedelta(days=1)}], True, 2713, "tuesday_68"),
    ([{"expires_at": NOW}], True, 3990, "store"),
    ([{"balance_cents": 0}], True, 3990, "store"),
    ([{"status": "disabled"}], True, 3990, "store"),
    ([{"started_at": NOW + timedelta(seconds=1)}], True, 3990, "store"),
    ([{"store_id": 99999}], True, 3990, "store"),
    ([{}], False, 3990, "store"),
    ([{"card_type": "annual", "expires_at": NOW}, {}], True, 2990, "member"),
    ([{"balance_cents": 0}, {"card_type": "annual", "expires_at": NOW + timedelta(days=1)}], True, 2713, "tuesday_68"),
])
def test_confirmation_resolves_current_store_rights_at_confirmation(api, cards, verified, expected, basis):
    key = make_selection(api, cards, verified=verified)
    with patch("app.api.admin_v2.datetime", FrozenDateTime):
        response = api.client.post(f"/api/v1/admin/v2/selection-sessions/{key}/confirm",
                                   headers={"Authorization": f"Bearer {create_staff_token(api.staff_id, 'admin')}"})
    assert response.status_code == 200, response.text
    with api.SessionLocal() as db:
        pricing = db.get(SelectionSession, key).pricing_snapshot
        assert pricing["payable_total_cents"] == expected
        assert pricing["lines"][0]["price_basis"] == basis


def test_source_card_preview_and_confirmation_context_agree(api):
    key = make_selection(api, [{}])
    with api.SessionLocal() as db:
        session = db.get(SelectionSession, key)
        with patch("app.domain.membership_entitlements.datetime", FrozenDateTime):
            preview = refresh_session_pricing(db, session)
        confirmed = refresh_session_pricing(db, session, confirmed_at=NOW)
        assert preview["payable_total_cents"] == confirmed["payable_total_cents"] == 2990


def test_card_exhausted_after_scan_is_rechecked_before_confirmation(api):
    key = make_selection(api, [{}])
    with api.SessionLocal() as db:
        session = db.get(SelectionSession, key)
        card = db.query(MembershipCard).filter_by(user_id=session.customer_id).one()
        card.balance_cents = 0
        db.commit()
    with patch("app.api.admin_v2.datetime", FrozenDateTime):
        response = api.client.post(f"/api/v1/admin/v2/selection-sessions/{key}/confirm",
                                   headers={"Authorization": f"Bearer {create_staff_token(api.staff_id, 'admin')}"})
    assert response.status_code == 200, response.text
    with api.SessionLocal() as db:
        assert db.get(SelectionSession, key).pricing_snapshot["payable_total_cents"] == 3990


@pytest.mark.parametrize("card,unit", [({}, 2990), ({"card_type": "annual", "expires_at": NOW + timedelta(days=1)}, 2713)])
def test_approved_addition_uses_source_rights_and_preserves_prior_revision(api, card, unit):
    key = make_selection(api, [card])
    headers = {"Authorization": f"Bearer {create_staff_token(api.staff_id, 'admin')}"}
    with patch("app.api.admin_v2.datetime", FrozenDateTime):
        confirmed = api.client.post(f"/api/v1/admin/v2/selection-sessions/{key}/confirm", headers=headers)
    assert confirmed.status_code == 200, confirmed.text
    with api.SessionLocal() as db:
        baseline = db.query(SelectionRevision).filter_by(selection_session_id=key).one()
        baseline_id, baseline_snapshot = baseline.id, baseline.snapshot
        revision = SelectionRevision(id=f"added-{key}", selection_session_id=key, revision_no=2,
                                     state="awaiting_staff_confirmation", idempotency_key=key,
                                     snapshot={"added_items": [{"project_id": api.project_id}]})
        change = SelectionChangeRequest(id=f"change-{key}", selection_session_id=key,
                                        selection_revision_id=revision.id, state="awaiting_staff_confirmation")
        occupancy = PositionOccupancy(store_id=api.store_id, room_id=12, selection_session_id=key,
                                      active_session_id=key, status="in_service", source="personal_qr")
        db.add_all([revision, change, occupancy])
        db.commit()
    with patch("app.api.admin_v2.datetime", FrozenDateTime):
        approved = api.client.post(f"/api/v1/admin/v2/selection-change-requests/change-{key}/approve", headers=headers)
    assert approved.status_code == 200, approved.text
    with api.SessionLocal() as db:
        session = db.get(SelectionSession, key)
        assert session.pricing_snapshot["payable_total_cents"] == 2 * unit
        assert db.get(SelectionRevision, baseline_id).snapshot == baseline_snapshot
        frozen = session.pricing_snapshot
        db.query(MembershipCard).filter_by(user_id=session.customer_id).one().status = "disabled"
        db.commit()
    retried = api.client.post(f"/api/v1/admin/v2/selection-sessions/{key}/confirm", headers=headers)
    assert retried.status_code == 200, retried.text
    with api.SessionLocal() as db:
        assert db.get(SelectionSession, key).pricing_snapshot == frozen
        assert db.get(SelectionRevision, baseline_id).snapshot == baseline_snapshot
