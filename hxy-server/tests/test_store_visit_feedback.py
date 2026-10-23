"""Public store feedback stays browser/store scoped and independent of services."""

import base64
import hashlib
import hmac
import json
import time

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
from app.models import EventLog, Room, ServicePositionQr, Staff, Store, User, VisitFeedback


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
    assert submit(client, enter(client), key="legacy-replay-key").status_code == 409
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(VisitFeedback)) == 1
        assert db.scalar(select(func.count()).select_from(EventLog)) == 0
