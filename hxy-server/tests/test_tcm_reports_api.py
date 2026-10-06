import hashlib
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import Base, get_db
from app.models import CustomerVerificationCode, User
from app.core.security import create_access_token
from app.api.admin import create_staff_token


@pytest.fixture
def context(monkeypatch):
    from app.api import tcm_reports
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with sessions.begin() as db:
        user = User(openid="h5_" + hashlib.sha256(b"13800138000").hexdigest()[:32], phone="13800138000",
                    last_login_at=now, customer_login_version=2)
        db.add(user)
        db.add(CustomerVerificationCode(phone=user.phone, code_hash="fixture", used_at=now,
            sent_at=now - timedelta(minutes=1), expires_at=now + timedelta(minutes=1), attempts=0))
        db.flush()
        identifier = user.id
    calls = []

    def source(phone, *, report_id=None, limit=20, offset=0):
        calls.append((phone, report_id))
        if report_id == "R2":
            from fastapi import HTTPException
            raise HTTPException(404, "Report not found")
        item = {"report_id": "R1", "reported_at": "2026-10-06T03:00:00+00:00", "title": "检测报告"}
        if report_id:
            return {**item, "physiques": [{"name": "平和质", "score": 42}], "heart_rate": 77,
                    "blood_oxygen": 92, "moisture": 3, "face_url": "https://private.invalid/face"}
        return {"items": [item], "limit": limit, "offset": offset, "has_more": False}

    monkeypatch.setattr(tcm_reports, "read_report_source", source)

    def override():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, sessions, identifier, calls
    app.dependency_overrides.clear()
    engine.dispose()


def customer_header(identifier, version=2):
    # Legacy valid JWT intentionally has no new phone-proof field.
    return {"Authorization": "Bearer " + create_access_token(str(identifier), "legacy-h5", version)}


def grant(client, headers):
    return client.post("/api/v1/me/tcm-report-consent", headers=headers,
                       json={"accepted": True, "version": "tcm-report-access-v1"})


def test_existing_otp_login_reused_separate_consent_withdrawal_and_minimal_fields(context):
    client, _, identifier, calls = context
    headers = customer_header(identifier)
    endpoint = "/api/v1/me/tcm-reports"
    assert client.get(endpoint, headers=headers).status_code == 403
    assert calls == []
    assert grant(client, headers).status_code == 200
    listed = client.get(endpoint, headers=headers)
    assert listed.status_code == 200
    assert set(listed.json()["items"][0]) == {"report_id", "reported_at", "title"}
    detail = client.get(endpoint + "/R1", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["heart_rate"] == 77
    assert "private.invalid" not in detail.text
    assert calls == [("13800138000", None), ("13800138000", "R1")]
    assert client.delete("/api/v1/me/tcm-report-consent", headers=headers).status_code == 200
    assert client.get(endpoint + "/R1", headers=headers).status_code == 403
    assert len(calls) == 2


def test_unauthorized_phone_override_stale_session_and_other_report_rejected(context):
    client, _, identifier, calls = context
    endpoint = "/api/v1/me/tcm-reports"
    headers = customer_header(identifier)
    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers={"Authorization": "Bearer " + create_staff_token(identifier, "manager")}).status_code == 401
    assert client.get(endpoint, headers=customer_header(identifier, 1)).status_code == 401
    assert grant(client, headers).status_code == 200
    assert client.get(endpoint + "?phone=13900139000", headers=headers).status_code == 422
    assert client.get(endpoint + "/R2", headers=headers).status_code == 404
    assert calls == [("13800138000", "R2")]


def test_arbitrary_old_used_code_or_stored_phone_is_not_session_proof(context):
    client, sessions, identifier, calls = context
    with sessions.begin() as db:
        user = db.get(User, identifier)
        user.last_login_at = user.last_login_at + timedelta(seconds=1)
    assert grant(client, customer_header(identifier)).status_code == 403
    assert calls == []


def test_unverified_cookie_and_non_customer_tokens_never_read(context):
    client, sessions, identifier, calls = context
    with sessions.begin() as db:
        db.query(CustomerVerificationCode).delete()
    client.cookies.set("hxy_trusted_device", "unverified-fixture")
    assert grant(client, customer_header(identifier)).status_code == 403
    for role in ("admin", "technician", "staff"):
        headers = {"Authorization": "Bearer " + create_staff_token(identifier, role)}
        assert client.get("/api/v1/me/tcm-reports", headers=headers).status_code == 401
        assert client.delete("/api/v1/me/tcm-report-consent", headers=headers).status_code == 401
    assert calls == []


def test_explicit_consent_cannot_be_replaced_by_extra_identity_fields(context):
    client, _, identifier, calls = context
    headers = customer_header(identifier)
    endpoint = "/api/v1/me/tcm-report-consent"
    assert client.post(endpoint, headers=headers, json={"accepted": False, "version": "tcm-report-access-v1"}).status_code == 422
    assert client.post(endpoint, headers=headers, json={"accepted": True, "version": "tcm-report-access-v1", "phone": "13900139000"}).status_code == 422
    assert client.get(endpoint + "?phone=13900139000", headers=headers).status_code == 422
    assert client.get("/api/v1/me/tcm-reports", headers=headers).status_code == 403
    assert calls == []


def test_real_otp_login_proof_survives_code_cleanup_and_phone_change_is_rejected(context):
    client, sessions, identifier, calls = context
    from app.api import auth
    now = datetime.now(UTC)
    with sessions.begin() as db:
        code = db.scalar(select(CustomerVerificationCode))
        code.used_at = None
        code.code_hash = auth._hash_code("123456")
        code.expires_at = now + timedelta(minutes=5)
    login = client.post("/api/v1/auth/h5/login", json={"phone": "13800138000", "code": "123456"})
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["token"]}
    with sessions.begin() as db:
        db.query(CustomerVerificationCode).delete()
    assert grant(client, headers).status_code == 200
    with sessions.begin() as db:
        db.get(User, identifier).phone = "13900139000"
    assert client.get("/api/v1/me/tcm-reports", headers=headers).status_code == 403
    assert calls == []
    assert client.delete("/api/v1/me/tcm-report-consent", headers=headers).status_code == 200
