"""Public store feedback stays browser/store scoped and independent of services."""

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.domain.visit_feedback_tokens import create_visit_feedback_token
from app.main import app
from app.models import AuditLog, EventLog, Room, ServicePositionQr, Staff, Store, Technician, User, VisitFeedback
from app.services import wecom_notify
from app.services.wecom_staff import WecomMessageReceipt


@pytest.fixture
def feedback_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions.begin() as db:
        db.add_all([
            Store(id=1, store_code="store-feedback-one", name="Open one", address="Synthetic", status="open"),
            Store(id=2, store_code="store-feedback-two", name="Open two", address="Synthetic", status="open"),
            Store(id=3, store_code="store-feedback-preparing", name="Preparing", address="Synthetic", status="preparing"),
            Store(id=4, store_code="store-feedback-closed", name="Closed", address="Synthetic", status="closed"),
        ])
        db.flush()
        db.add_all([
            Staff(id=1, username="store-feedback-manager-one", password_hash="unused", name="Manager one", role="manager", store_id=1),
            Staff(id=2, username="store-feedback-manager-two", password_hash="unused", name="Manager two", role="manager", store_id=2),
        ])

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app, base_url="https://testserver") as client:
            yield client, sessions
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def enter(client, store_id=1):
    response = client.post("/api/v1/visit-feedback/store-entry", json={"store_id": store_id})
    assert response.status_code == 200, response.text
    return response.json()["visit_feedback_token"]


def submit(client, token, key="store-feedback-key", **changes):
    body = {"visit_feedback_token": token, "rating": 5, "tags": [], "note": "  helpful  "}
    body.update(changes)
    return client.post("/api/v1/visit-feedback", headers={"Idempotency-Key": key}, json=body)


def sign_payload(payload, prefix="vfs1"):
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(
        settings.jwt_secret.encode(), f"{prefix}.{raw}".encode(), hashlib.sha256,
    ).digest()[:16]).decode().rstrip("=")
    return f"{prefix}.{raw}.{signature}"


def payload_of(token):
    raw = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


def test_public_store_entry_saves_without_seat_or_service(feedback_client, monkeypatch):
    client, sessions = feedback_client
    monkeypatch.setattr(settings, "environment", "production")
    entry = client.post("/api/v1/visit-feedback/store-entry", json={"store_id": 1})
    assert entry.status_code == 200, entry.text
    assert set(entry.json()) == {"visit_feedback_token", "store_id", "store_name"}
    assert entry.json()["store_name"] == "Open one"
    assert "HttpOnly" in entry.headers["set-cookie"] and "Secure" in entry.headers["set-cookie"]
    token = entry.json()["visit_feedback_token"]
    assert token.startswith("vfs1.")
    assert not {"room_id", "qr_id"} & payload_of(token).keys()
    browser = client.cookies.get("hxy_browser_token")
    renewed = enter(client)
    assert client.cookies.get("hxy_browser_token") == browser
    response = submit(client, renewed)
    assert response.status_code == 200, response.text
    assert response.json()["note"] == "helpful"
    assert not {"customer_id", "room_id", "store_id", "selection_session_id", "technician_id"} & response.json().keys()
    with sessions() as db:
        row = db.get(VisitFeedback, response.json()["id"])
        assert (row.store_id, row.room_id, row.service_position_qr_id, row.source) == (1, None, None, "store_qr")
        assert row.customer_id is None
        for name in ("selection_sessions", "orders", "position_occupancies", "service_feedback"):
            assert db.scalar(select(func.count()).select_from(Base.metadata.tables[name])) == 0
        assert db.scalar(select(func.count()).select_from(EventLog)) == 1


@pytest.mark.parametrize("store_id", [3, 4, 999])
def test_entry_rejects_unavailable_store_without_cookie(feedback_client, store_id):
    client, sessions = feedback_client
    response = client.post("/api/v1/visit-feedback/store-entry", json={"store_id": store_id})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "STORE_UNAVAILABLE"
    assert not client.cookies
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Base.metadata.tables["users"])) == 0


@pytest.mark.parametrize("body", [{}, {"store_id": True}, {"store_id": "1"}, {"store_id": 0}, {"store_id": 1, "room_id": 1}])
def test_entry_rejects_malformed_scope(feedback_client, body):
    client, _ = feedback_client
    assert client.post("/api/v1/visit-feedback/store-entry", json=body).status_code == 422


def test_rating_required_and_payload_cannot_override_scope(feedback_client):
    client, sessions = feedback_client
    token = enter(client)
    response = client.post("/api/v1/visit-feedback", headers={"Idempotency-Key": "missing-rating"}, json={"visit_feedback_token": token})
    assert response.status_code == 422
    for changes in ({"store_id": 2}, {"rating": 0}, {"rating": 6}, {"room_id": 1}, {"note": "x" * 301}):
        assert submit(client, token, **changes).status_code == 422
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(VisitFeedback)) == 0


def test_store_closure_browser_swap_and_tampering_reject(feedback_client):
    client, sessions = feedback_client
    token = enter(client)
    original_browser = client.cookies.get("hxy_browser_token")
    client.cookies.clear()
    assert submit(client, token).status_code == 403
    enter(client)
    assert client.cookies.get("hxy_browser_token") != original_browser
    assert submit(client, token).status_code == 403
    token = enter(client)
    prefix, raw, signature = token.split(".")
    assert submit(client, f"{prefix}.{raw}.{signature[:-1]}!").status_code == 403
    payload = payload_of(token)
    payload["store_id"] = 2
    changed_raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    assert submit(client, f"{prefix}.{changed_raw}.{signature}").status_code == 403
    assert submit(client, sign_payload(payload, "vf1")).status_code == 403
    with sessions.begin() as db:
        db.get(Store, 1).status = "closed"
    assert submit(client, token).status_code == 403


@pytest.mark.parametrize("change", [
    {"exp": None}, {"exp": "soon"}, {"exp": True}, {"exp": 1.5},
    {"store_id": True}, {"store_id": "1"}, {"store_id": []},
    {"browser_hash": []}, {"browser_hash": None}, {"room_id": 1}, {"qr_id": 1},
    {"v": 2}, {"source": "personal_qr"},
])
def test_signed_malformed_store_payload_is_denied_not_500(feedback_client, change):
    client, _ = feedback_client
    payload = payload_of(enter(client))
    payload.update(change)
    response = submit(client, sign_payload(payload))
    assert response.status_code == 403, response.text


@pytest.mark.parametrize("payload", [["not-an-object"], None, True, "store"])
def test_non_object_signed_payload_is_denied(feedback_client, payload):
    client, _ = feedback_client
    enter(client)
    assert submit(client, sign_payload(payload)).status_code == 403


def test_expired_store_token_rejected(feedback_client):
    client, _ = feedback_client
    payload = payload_of(enter(client))
    payload["exp"] = int(time.time()) - 1
    response = submit(client, sign_payload(payload))
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "VISIT_FEEDBACK_TOKEN_EXPIRED"


def test_invalid_authorization_never_falls_back_to_anonymous(feedback_client):
    client, sessions = feedback_client
    for header in ("Bearer invalid", "Basic invalid", ""):
        response = client.post("/api/v1/visit-feedback/store-entry", headers={"Authorization": header}, json={"store_id": 1})
        assert response.status_code == 401
    token = enter(client)
    for header in ("Bearer invalid", "Basic invalid", ""):
        response = client.post("/api/v1/visit-feedback", headers={"Authorization": header, "Idempotency-Key": "bad-auth-feedback"}, json={"visit_feedback_token": token, "rating": 5})
        assert response.status_code == 401
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(VisitFeedback)) == 0


def test_cross_store_key_conflicts_but_rate_limits_are_store_scoped(feedback_client):
    client, sessions = feedback_client
    first = enter(client, 1)
    second = enter(client, 2)
    saved = submit(client, first)
    assert saved.status_code == 200
    assert submit(client, first).json()["id"] == saved.json()["id"]
    assert submit(client, first, rating=4).status_code == 409
    assert submit(client, second).status_code == 409
    other = submit(client, second, key="other-store-first")
    assert other.status_code == 200 and other.json()["id"] != saved.json()["id"]
    for index in range(4):
        assert submit(client, first, key=f"store-rate-{index}").status_code == 200
    assert submit(client, first, key="store-rate-sixth").status_code == 429
    assert submit(client, second, key="other-store-next").status_code == 200
    assert submit(client, first).json()["id"] == saved.json()["id"]
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(VisitFeedback)) == 7
        assert db.scalar(select(func.count()).select_from(EventLog)) == 7


def test_admin_lists_roomless_feedback_only_for_own_store(feedback_client):
    client, _ = feedback_client
    first = submit(client, enter(client, 1)).json()["id"]
    second = submit(client, enter(client, 2), key="admin-second-store").json()["id"]
    for staff_id, expected, forbidden in ((1, first, second), (2, second, first)):
        headers = {"Authorization": "Bearer " + create_staff_token(staff_id, "manager")}
        listing = client.get("/api/v1/admin/v2/feedback?feedback_type=visit_feedback", headers=headers)
        assert listing.status_code == 200, listing.text
        rows = listing.json()["items"]
        assert [row["id"] for row in rows] == [expected]
        assert rows[0]["source"] == "store_qr" and rows[0]["selection_session_id"] is None
        assert client.get(f"/api/v1/admin/v2/feedback/visit_feedback/{expected}", headers=headers).status_code == 200
        assert client.get(f"/api/v1/admin/v2/feedback/visit_feedback/{forbidden}", headers=headers).status_code == 404


def test_account_identity_is_preserved_and_renewal_replays(feedback_client):
    client, sessions = feedback_client
    with sessions.begin() as db:
        user = User(openid="store-feedback-account", phone="13800000001")
        db.add(user)
        db.flush()
        user_id = user.id
        access_token = create_access_token(str(user.id), user.openid, user.customer_login_version)
    client.headers["Authorization"] = "Bearer " + access_token
    token = enter(client)
    first = submit(client, token)
    assert first.status_code == 200, first.text
    renewed = enter(client)
    assert submit(client, renewed).json()["id"] == first.json()["id"]
    with sessions() as db:
        row = db.get(VisitFeedback, first.json()["id"])
        assert row.customer_id == user_id
        assert row.identity_hash == hashlib.sha256(f"customer:{user_id}".encode()).hexdigest()


def test_legacy_vf1_frozen_fingerprint_still_replays(feedback_client):
    client, sessions = feedback_client
    enter(client)
    browser = client.cookies.get("hxy_browser_token")
    with sessions.begin() as db:
        room = Room(id=1, store_id=1, code="legacy-feedback", name="Legacy", room_type="sofa", is_service_position=True, operational_status="active")
        db.add(room)
        db.flush()
        qr = ServicePositionQr(id=1, public_id="legacy-feedback-qr", store_id=1, room_id=1, source="personal_qr", status="active")
        db.add(qr)
        db.flush()
        token = create_visit_feedback_token(room, "personal_qr", browser, qr.id)
        # Exact canonical bytes of the pre-store-entry contract, not its current helper.
        old_fingerprint = hashlib.sha256(b'{"note":"helpful","qr_id":1,"rating":5,"room_id":1,"tags":[]}').hexdigest()
        db.add(VisitFeedback(
            id=1, store_id=1, room_id=1, service_position_qr_id=1, source="personal_qr", rating=5, tags=[], note="helpful",
            identity_hash=hashlib.sha256(f"browser:{browser}".encode()).hexdigest(),
            idempotency_key_hash=hashlib.sha256(b"legacy-replay-key").hexdigest(), request_fingerprint=old_fingerprint,
        ))
    response = submit(client, token, key="legacy-replay-key")
    assert response.status_code == 200 and response.json()["id"] == 1
    assert submit(client, token, key="legacy-replay-key", callback_phone=None).json()["id"] == 1
    assert submit(client, token, key="legacy-replay-key", callback_phone="13900000071").status_code == 409
    assert submit(client, enter(client), key="legacy-replay-key").status_code == 409
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(VisitFeedback)) == 1
        assert db.scalar(select(func.count()).select_from(EventLog)) == 0


@pytest.mark.parametrize("logged_in", [False, True])
def test_callback_phone_does_not_bind_or_replace_a_customer_account(feedback_client, logged_in):
    client, sessions = feedback_client
    callback = "13900000071"
    account_phone = "13800000072"
    with sessions.begin() as db:
        account = User(openid="feedback-account-owner", phone=account_phone)
        db.add_all([account, User(openid="feedback-other-account", phone=callback)])
        db.flush()
        customer_id = account.id if logged_in else None
        if logged_in:
            client.headers["Authorization"] = "Bearer " + create_access_token(
                str(account.id), account.openid, account.customer_login_version,
            )
    token = enter(client)
    account_state = select(User.id, User.openid, User.phone).order_by(User.id)
    with sessions() as db:
        original_accounts = db.execute(account_state).all()

    saved = submit(client, token, callback_phone=callback)
    assert saved.status_code == 200, saved.text
    assert "callback_phone" not in saved.json() and callback not in saved.text
    replay = submit(client, enter(client), callback_phone=callback)
    assert replay.status_code == 200 and replay.json() == saved.json()
    for changes in ({"callback_phone": "13900000073"}, {"callback_phone": None}, {}):
        conflict = submit(client, token, **changes)
        assert conflict.status_code == 409 and callback not in conflict.text
        assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    with sessions() as db:
        row = db.scalars(select(VisitFeedback)).one()
        assert (row.id, row.callback_phone, row.customer_id) == (saved.json()["id"], callback, customer_id)
        assert db.execute(account_state).all() == original_accounts
        assert db.scalar(select(func.count()).select_from(EventLog)) == 1
    manager = {"Authorization": "Bearer " + create_staff_token(1, "manager")}
    detail = client.get(f"/api/v1/admin/v2/feedback/visit_feedback/{row.id}", headers=manager)
    assert detail.status_code == 200
    assert detail.json()["callback_phone"] == callback
    assert detail.json()["customer_phone"] == (account_phone if logged_in else None)


@pytest.mark.parametrize("value, marker", [
    ("12800000071", "12800000071"),
    ("1390000071", "1390000071"),
    ("139000000710", "139000000710"),
    ("+8613900000071", "13900000071"),
    ("139-0000-0071", "139-0000-0071"),
    ("1390000007x", "1390000007x"),
    ("139００００００７１", "139００００００７１"),
    (13900000071, "13900000071"),
    ({"phone": "13900000071"}, "13900000071"),
])
def test_invalid_callback_phone_is_rejected_without_echo_or_record(feedback_client, value, marker):
    client, sessions = feedback_client
    response = submit(client, enter(client), callback_phone=value)
    assert response.status_code == 422
    assert marker not in json.dumps(response.json(), ensure_ascii=False)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(VisitFeedback)) == 0
        assert db.scalar(select(func.count()).select_from(EventLog)) == 0


def test_empty_callback_phone_creates_anonymous_feedback(feedback_client):
    client, sessions = feedback_client
    token = enter(client)
    for index, changes in enumerate(({}, {"callback_phone": None}, {"callback_phone": ""}, {"callback_phone": "  "})):
        saved = submit(client, token, key=f"empty-phone-{index}", **changes)
        assert saved.status_code == 200, saved.text
        assert "callback_phone" not in saved.json()
    with sessions() as db:
        assert db.execute(select(VisitFeedback.callback_phone, VisitFeedback.customer_id)).all() == [(None, None)] * 4
    manager = {"Authorization": "Bearer " + create_staff_token(1, "manager")}
    detail = client.get(f"/api/v1/admin/v2/feedback/visit_feedback/{saved.json()['id']}", headers=manager)
    assert detail.status_code == 200 and detail.json()["callback_phone"] is None


def test_pre_callback_phone_store_fingerprint_is_still_replayable(feedback_client):
    client, sessions = feedback_client
    token = enter(client)
    browser = client.cookies.get("hxy_browser_token")
    legacy_payload = b'{"note":"helpful","qr_id":null,"rating":5,"room_id":null,"scope":"store","store_id":1,"tags":[]}'
    key = "pre-callback-store-key"
    with sessions.begin() as db:
        db.add(VisitFeedback(
            id=81, store_id=1, source="store_qr", rating=5, tags=[], note="helpful",
            identity_hash=hashlib.sha256(f"browser:{browser}".encode()).hexdigest(),
            idempotency_key_hash=hashlib.sha256(key.encode()).hexdigest(),
            request_fingerprint=hashlib.sha256(legacy_payload).hexdigest(),
        ))
    for changes in ({}, {"callback_phone": None}, {"callback_phone": ""}):
        replay = submit(client, token, key=key, **changes)
        assert replay.status_code == 200 and replay.json()["id"] == 81
        assert "callback_phone" not in replay.json()
    assert submit(client, token, key=key, callback_phone="13900000071").status_code == 409
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(VisitFeedback)) == 1
        assert db.scalar(select(func.count()).select_from(EventLog)) == 0


def test_only_own_manager_detail_discloses_the_callback_phone(feedback_client):
    client, sessions = feedback_client
    callback = "13900000071"
    with sessions.begin() as db:
        technician = Technician(id=6, code="feedback-privacy-tech", name="Synthetic technician", store_id=1)
        db.add(technician)
        db.flush()
        db.add(Staff(id=3, username="feedback-privacy-tech", password_hash="unused", role="technician", store_id=1, technician_id=technician.id))
    saved = submit(client, enter(client), callback_phone=callback)
    assert saved.status_code == 200, saved.text
    detail_url = f"/api/v1/admin/v2/feedback/visit_feedback/{saved.json()['id']}"
    manager = {"Authorization": "Bearer " + create_staff_token(1, "manager")}
    other_manager = {"Authorization": "Bearer " + create_staff_token(2, "manager")}
    technician = {"Authorization": "Bearer " + create_staff_token(3, "technician")}
    for headers, expected_status in (({}, 401), (technician, 403), (other_manager, 404)):
        denied = client.get(detail_url, headers=headers)
        assert denied.status_code == expected_status and callback not in denied.text
    for params in ({}, {"feedback_type": "visit_feedback"}):
        listing = client.get("/api/v1/admin/v2/feedback", params=params, headers=manager)
        assert listing.status_code == 200 and listing.json()["total"] == 1
        assert "callback_phone" not in listing.json()["items"][0] and callback not in listing.text
    changed = client.patch(detail_url, headers=manager, json={"follow_up_status": "in_progress"})
    assert changed.status_code == 200 and "callback_phone" not in changed.json() and callback not in changed.text
    detail = client.get(detail_url, headers=manager)
    assert detail.status_code == 200 and detail.json()["callback_phone"] == callback
    with sessions() as db:
        follow_up_audit = db.scalars(select(AuditLog).where(AuditLog.action == "update_feedback_follow_up")).one()
        assert callback not in json.dumps(follow_up_audit.detail)


def test_callback_phone_is_absent_from_wecom_card_and_audits(feedback_client, monkeypatch):
    client, sessions = feedback_client
    callback = "13900000071"
    provider = Mock()
    provider.send_textcard.return_value = WecomMessageReceipt("accepted", 1, 0)
    monkeypatch.setattr(settings, "wecom_staff_enabled", True)
    monkeypatch.setattr(settings, "wecom_visit_feedback_notify_enabled", True)
    monkeypatch.setattr(wecom_notify, "SessionLocal", sessions)
    monkeypatch.setattr(wecom_notify, "manager_userids", lambda *args, **kwargs: ["synthetic-manager"])
    monkeypatch.setattr(wecom_notify, "get_wecom_provider", lambda: provider)
    token = enter(client)
    saved = submit(client, token, callback_phone=callback)
    assert saved.status_code == 200, saved.text
    assert submit(client, token, callback_phone=callback).json() == saved.json()
    provider.send_textcard.assert_called_once()
    assert callback not in str(provider.send_textcard.call_args)
    with sessions() as db:
        audits = db.scalars(select(AuditLog).where(AuditLog.action == "wecom_feedback_notify").order_by(AuditLog.id)).all()
        assert [row.detail["status"] for row in audits] == ["started", "accepted"]
        assert callback not in json.dumps([row.detail for row in audits])
        events = db.scalars(select(EventLog)).all()
        assert len(events) == 1 and callback not in json.dumps(events[0].data)
