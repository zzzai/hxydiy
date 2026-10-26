"""Isolated feedback notification contracts; never contact WeCom or production."""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from test_store_visit_feedback import feedback_client, enter, submit
from app.core.config import settings
from app.models import AuditLog, SelectionSession, ServiceFeedback, Staff, StaffScopeAssignment, VisitFeedback
from app.models.staff_external_identity import StaffExternalIdentity
from app.services import wecom_notify
from app.services.wecom_staff import WecomMessageReceipt, WecomProvider, WecomProviderError


@pytest.fixture
def notifications(feedback_client, monkeypatch):
    client, sessions = feedback_client
    for key, value in {
        "wecom_staff_enabled": True, "wecom_corp_id": "synthetic-corp",
        "wecom_agent_id": "1000001", "wecom_order_notify_userids": "",
        "wecom_visit_feedback_notify_enabled": True,
        "h5_public_base_url": "https://synthetic.invalid/",
    }.items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(wecom_notify, "SessionLocal", sessions)
    with sessions.begin() as db:
        for number in (1, 2):
            db.add(StaffScopeAssignment(staff_id=number, role="store_manager", scope_type="store", scope_id=number, status="active"))
            db.add(StaffExternalIdentity(provider="wecom", corp_id="synthetic-corp", userid=f"manager-{number}", staff_id=number, store_id=number, status="active"))
    calls = []
    class FakeProvider:
        def send_textcard(self, *args):
            with sessions() as db:
                assert list(db.scalars(select(VisitFeedback))) or list(db.scalars(select(ServiceFeedback)))
                assert list(db.scalars(select(AuditLog).where(AuditLog.action == "wecom_feedback_notify")))
            calls.append(args)
            return WecomMessageReceipt("accepted", len(args[0]), 0)
    provider = FakeProvider()
    monkeypatch.setattr(wecom_notify, "get_wecom_provider", lambda: provider)
    return client, sessions, calls, provider


def audits(sessions):
    with sessions() as db:
        return [(r.entity_type, r.entity_id, r.detail) for r in db.scalars(select(AuditLog).where(AuditLog.action == "wecom_feedback_notify").order_by(AuditLog.id))]


def test_qr_feedback_is_committed_before_send_and_duplicate_does_not_notify(notifications):
    client, sessions, calls, _ = notifications
    token = enter(client)
    result = submit(client, token, note="Private synthetic comment")
    assert result.status_code == 200
    assert submit(client, token, note="Private synthetic comment").json() == result.json()
    assert len(calls) == 1 and calls[0][0] == ["manager-1"]
    target = urlsplit(calls[0][3])
    assert target.path == "/technician/store/wecom"
    assert parse_qs(target.query) == {"review": [f"visit_feedback:{result.json()['id']}"]}
    assert "Private synthetic comment" not in calls[0][2]
    rows = audits(sessions)
    assert [r[2]["status"] for r in rows] == ["started", "accepted"]
    assert rows[0][2]["attempt_id"] == rows[1][2]["attempt_id"]
    assert "manager-1" not in json.dumps(rows) and "Private synthetic" not in json.dumps(rows)


def test_provider_timeout_does_not_fail_customer_or_blindly_retry(notifications, monkeypatch):
    client, sessions, calls, provider = notifications
    def unavailable(*args):
        calls.append(args)
        raise WecomProviderError()
    monkeypatch.setattr(provider, "send_textcard", unavailable)
    token = enter(client)
    saved = submit(client, token)
    assert saved.status_code == 200
    assert submit(client, token).json() == saved.json()
    assert len(calls) == 1
    assert [r[2]["status"] for r in audits(sessions)] == ["started", "unknown"]


@pytest.mark.parametrize("guard", ["disabled", "allowlist", "revoked", "expired", "ambiguous", "different_corp", "technician"])
def test_recipient_boundary_and_opt_in(notifications, monkeypatch, guard):
    client, sessions, calls, _ = notifications
    with sessions.begin() as db:
        if guard == "disabled": monkeypatch.setattr(settings, "wecom_visit_feedback_notify_enabled", False)
        elif guard == "allowlist": monkeypatch.setattr(settings, "wecom_order_notify_userids", "manager-2")
        elif guard == "revoked": db.get(StaffExternalIdentity, 1).status = "disabled"
        elif guard == "expired": db.get(Staff, 1).temporary_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        elif guard == "ambiguous": db.add(StaffScopeAssignment(staff_id=1, role="store_manager", scope_type="store", scope_id=2, status="active"))
        elif guard == "different_corp": db.get(StaffExternalIdentity, 1).corp_id = "other-corp"
        else: db.get(Staff, 1).role = "technician"
    assert submit(client, enter(client)).status_code == 200
    assert calls == []
    assert [r[2]["status"] for r in audits(sessions)] == ([] if guard == "disabled" else ["no_recipient"])


def test_audit_failure_prevents_untracked_send_without_breaking_submit(notifications, monkeypatch):
    client, sessions, calls, _ = notifications
    monkeypatch.setattr(wecom_notify, "_review_audit", lambda *a, **kw: False)
    assert submit(client, enter(client)).status_code == 200
    assert not calls
    with sessions() as db: assert len(list(db.scalars(select(VisitFeedback)))) == 1


def test_service_and_visit_ids_have_distinct_routes_and_audits(notifications):
    client, sessions, calls, _ = notifications
    saved = submit(client, enter(client)).json()
    with sessions.begin() as db:
        db.add(SelectionSession(id="synthetic-service", access_token_hash="x" * 64, store_id=1, status="confirmed"))
        db.flush()
        db.add(ServiceFeedback(id=saved["id"], store_id=1, selection_session_id="synthetic-service", rating=4))
    wecom_notify.notify_feedback(saved["id"])
    assert len(calls) == 2
    assert parse_qs(urlsplit(calls[1][3]).query) == {"review": [f"service_review:{saved['id']}"]}
    assert {r[0] for r in audits(sessions)} == {"visit_feedback", "service_feedback"}


@pytest.mark.parametrize("payload,status,accepted,invalid", [
    ({"errcode": 0, "msgid": "synthetic"}, "accepted", 2, 0),
    ({"errcode": 0, "invaliduser": "manager-1"}, "partial", 1, 1),
    ({"errcode": 0, "invaliduser": "manager-1|manager-2"}, "rejected", 0, 2),
    ({"errcode": 0, "unlicenseduser": "manager-2"}, "partial", 1, 1),
])
def test_provider_receipt_never_calls_partial_success_complete(notifications, monkeypatch, payload, status, accepted, invalid):
    provider = WecomProvider()
    monkeypatch.setattr(provider, "_access_token", lambda: "synthetic")
    monkeypatch.setattr(provider, "_post", lambda *args: payload)
    result = provider.send_textcard(["manager-1", "manager-2"], "Title", "Body", "https://synthetic.invalid/review")
    assert result == WecomMessageReceipt(status, accepted, invalid)


@pytest.mark.parametrize("payload", [{}, {"errcode": 0, "invaliduser": "other-store"}, {"errcode": 0, "invaliduser": []}, {"errcode": 0, "invalidparty": "1"}])
def test_malformed_receipt_is_not_success(notifications, monkeypatch, payload):
    provider = WecomProvider()
    monkeypatch.setattr(provider, "_access_token", lambda: "synthetic")
    monkeypatch.setattr(provider, "_post", lambda *args: payload)
    with pytest.raises(WecomProviderError):
        provider.send_textcard(["manager-1"], "Title", "Body", "https://synthetic.invalid/review")
