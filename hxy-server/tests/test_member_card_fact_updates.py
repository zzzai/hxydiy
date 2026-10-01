from datetime import UTC, datetime, timedelta
import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.domain.membership_entitlements import has_membership
from app.main import app
from app.models import AuditLog, MembershipCard, Order, Recharge, Staff, Store, User


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with sessions() as db:
        db.add_all([Store(id=i, store_code=f"fact-{i}", name="Test", address="Test") for i in (1, 2)])
        db.add(User(id=1, openid="fact-user", nickname="Original", balance_cents=500, is_member=False))
        db.flush()
        db.add(Order(id=1, order_no="fact-frozen-order", order_type="service", user_id=1, store_id=1,
                     status="completed", total_amount_cents=3990, pay_amount_cents=2990,
                     items=[{"price_cents": 2990}]))
        for identifier, role, store in [(1, "manager", 1), (2, "manager", 2), (3, "staff", 1), (4, "technician", 1), (5, "admin", None)]:
            db.add(Staff(id=identifier, username=f"fact-{identifier}", name="Checker", role=role,
                         store_id=store, status="active", password_hash=hash_password("test")))
        for identifier, kind, store in [(1, "stored", 1), (2, "annual", 1), (3, "stored", 2)]:
            db.add(MembershipCard(id=identifier, user_id=1, store_id=store, source="test",
                                  source_card_key=f"private-{identifier}", card_type=kind, balance_cents=100,
                                  started_at=now - timedelta(days=2), observed_at=now - timedelta(days=1),
                                  expires_at=now + timedelta(days=1) if kind == "annual" else None))
        db.commit()

    def override():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, sessions
    app.dependency_overrides.clear()
    engine.dispose()


def request(api, body, *, staff=1, role="manager", card=1, store=None):
    suffix = f"?store_id={store}" if store is not None else ""
    return api[0].post(f"/api/v1/admin/v2/membership-cards/{card}/facts" + suffix, json=body,
                       headers={"Authorization": "Bearer " + create_staff_token(staff, role)})


def fact(**fields):
    values = {"balance_cents": 0, "observed_at": datetime.now(UTC).isoformat(),
              "evidence": "Source ledger checked", "reason": "Verified principal balance"}
    values.update(fields)
    return values


def apply(api, body, **scope):
    preview = request(api, body, **scope)
    assert preview.status_code == 200, preview.text
    return request(api, {**body, "apply": True, "expected_version": preview.json()["version"],
                         "preview_token": preview.json()["preview_token"], "idempotency_key": "fact-test"}, **scope)


def test_preview_and_apply_preserve_other_facts_and_record_audit(api):
    body = fact()
    preview = request(api, body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["before"]["balance_cents"] == 100
    assert preview.json()["after"]["balance_cents"] == 0
    assert "private-1" not in preview.text
    with api[1]() as db:
        assert db.get(MembershipCard, 1).balance_cents == 100
        assert db.scalar(select(AuditLog)) is None
    response = apply(api, body)
    assert response.status_code == 200, response.text
    with api[1]() as db:
        assert db.get(MembershipCard, 1).balance_cents == 0
        user = db.get(User, 1)
        assert (user.nickname, user.balance_cents, user.is_member) == ("Original", 500, False)
        order = db.get(Order, 1)
        assert (order.status, order.total_amount_cents, order.pay_amount_cents, order.items) == (
            "completed", 3990, 2990, [{"price_cents": 2990}])
        assert db.scalar(select(Recharge)) is None
        assert has_membership(db, user, store_id=1)
        audit = db.scalar(select(AuditLog))
        assert audit.store_id == 1
        assert audit.detail["checked_by_staff_id"] == 1
        assert audit.detail["evidence"] == body["evidence"]
        assert audit.detail["before"]["balance_cents"] == 100
        assert audit.detail["after"]["balance_cents"] == 0


def test_idempotency_and_stale_version_reject_blind_or_changed_writes(api):
    body = fact()
    preview = request(api, body)
    assert preview.status_code == 200, preview.text
    write = {**body, "apply": True, "expected_version": preview.json()["version"],
             "preview_token": preview.json()["preview_token"], "idempotency_key": "stable-key"}
    first = request(api, write)
    assert first.status_code == 200, first.text
    assert request(api, write).json() == first.json()
    assert request(api, {**write, "balance_cents": 20}).status_code == 409
    assert request(api, {**write, "idempotency_key": "other-key"}).status_code == 409
    assert request(api, {**body, "apply": True}).status_code == 422
    with api[1]() as db:
        assert len(db.scalars(select(AuditLog)).all()) == 1


def test_apply_cannot_change_previewed_payload_or_use_another_checkers_preview(api):
    body = fact()
    preview = request(api, body)
    assert preview.status_code == 200, preview.text
    write = {**body, "apply": True, "expected_version": preview.json()["version"],
             "preview_token": preview.json()["preview_token"], "idempotency_key": "proof-key"}
    assert request(api, {**write, "balance_cents": 99}).status_code == 409
    assert request(api, write, staff=5, role="admin", store=1).status_code == 409
    with api[1]() as db:
        assert db.get(MembershipCard, 1).balance_cents == 100
        assert db.scalar(select(AuditLog)) is None


def test_stop_and_restore_card_and_multi_card_union(api):
    assert apply(api, fact(balance_cents=None, status="disabled"), card=1).status_code == 200
    with api[1]() as db:
        assert has_membership(db, db.get(User, 1), store_id=1)
    assert apply(api, fact(balance_cents=None, status="disabled"), card=2).status_code == 200
    with api[1]() as db:
        assert not has_membership(db, db.get(User, 1), store_id=1)
    restored = apply(api, fact(balance_cents=None, status="active"), card=1)
    assert restored.status_code == 409  # The same key cannot describe a different update.
    body = fact(balance_cents=None, status="active")
    preview = request(api, body)
    response = request(api, {**body, "apply": True, "expected_version": preview.json()["version"],
                             "preview_token": preview.json()["preview_token"], "idempotency_key": "restore-card"})
    assert response.status_code == 200, response.text
    with api[1]() as db:
        assert has_membership(db, db.get(User, 1), store_id=1)


@pytest.mark.parametrize("staff,role,card,store,code", [(2, "manager", 1, None, 404),
    (1, "manager", 3, None, 404), (1, "manager", 1, 2, 403), (3, "staff", 1, None, 403),
    (4, "technician", 1, None, 403), (5, "admin", 1, None, 422), (1, "manager", 999, None, 404)])
def test_permissions_and_unknown_cards(api, staff, role, card, store, code):
    assert request(api, fact(), staff=staff, role=role, card=card, store=store).status_code == code


def test_headquarters_requires_explicit_store(api):
    assert apply(api, fact(), staff=5, role="admin", store=1).status_code == 200


@pytest.mark.parametrize("fields", [{"evidence": " "}, {"reason": " "}, {"balance_cents": -1},
    {"balance_cents": True}, {"observed_at": "2020-01-01T00:00:00+00:00"},
    {"observed_at": "2099-01-01T00:00:00+00:00"}, {"observed_at": "2026-01-01T00:00:00"},
    {"expires_at": "2099-01-01"}, {"balance_cents": None}])
def test_invalid_evidence_dates_and_unsupported_updates(api, fields):
    assert request(api, fact(**fields)).status_code in (409, 422)


def test_expired_card_cannot_be_restored_or_dates_overwritten(api):
    with api[1]() as db:
        card = db.get(MembershipCard, 2)
        card.status = "disabled"
        card.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert request(api, fact(balance_cents=None, status="active"), card=2).status_code == 409
    assert request(api, fact(), card=2).status_code == 422


def test_server_tool_previews_then_applies_through_authenticated_http(api, tmp_path, monkeypatch):
    from scripts import update_member_card_facts as tool

    token = create_staff_token(1, "manager")
    monkeypatch.setenv("HXY_STAFF_TOKEN", token)

    def http(request, timeout):
        response = api[0].post(request.full_url.replace("http://testserver", ""),
                               content=request.data, headers=dict(request.header_items()))
        assert response.status_code == 200, response.text
        return io.BytesIO(response.content)

    monkeypatch.setattr(tool, "urlopen", http)
    input_file, preview, report = (tmp_path / name for name in ("input.json", "preview.json", "applied.json"))
    input_file.write_text(json.dumps({"card_id": 1, "idempotency_key": "cli-update", **fact()}), encoding="utf-8")
    assert tool.main([str(input_file), "--base-url", "http://testserver", "--report", str(preview)]) == 0
    with api[1]() as db:
        assert db.get(MembershipCard, 1).balance_cents == 100
    assert tool.main([str(input_file), "--base-url", "http://testserver", "--report", str(report),
                      "--apply", "--preview-file", str(preview)]) == 0
    assert json.loads(report.read_text())["applied"] is True
    assert token not in preview.read_text() + report.read_text()
    with api[1]() as db:
        assert db.get(MembershipCard, 1).balance_cents == 0
        assert len(db.scalars(select(AuditLog)).all()) == 1
