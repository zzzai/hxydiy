from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time, timedelta
from io import BytesIO
import os
from threading import Barrier, Event
from uuid import uuid4
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
import pytest

from app.api.admin import create_staff_token
from app.api.manager_daily import _today
from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app
from app.models import DailyAreaPhotoReview, DailyStoreCheckin, InspectionDelivery, InspectionFollowup, Staff, Store
from app.models.staff_access import StaffScopeAssignment
from app.models.staff_external_identity import StaffExternalIdentity
from app.services.inspection_dispatch import deliver_next, enqueue
from app.services.inspection_reviews import process_next
from app.services.inspection_weekly import SHANGHAI, summarize_week, weekly_due, weekly_text
from app.services.wecom_staff import WecomMessageReceipt, WecomMessageRejected, WecomProviderError
from test_inspection_reviews import FIX, enable
from test_manager_daily import BASE, daily


PASS = dict(verdict="pass", location="台面", evidence="原问题位置已清理", action="")
RETAKE = dict(verdict="retake", location="台面左侧", evidence="原位置未入镜", action="对准原位置复拍")


@pytest.fixture(autouse=True)
def isolated_camera_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "media_storage_backend", "local")
    monkeypatch.setattr(settings, "media_storage_root", str(tmp_path))


def make_case(daily, monkeypatch, code):
    client, factory, ids, headers = daily
    enable(monkeypatch)
    start = datetime.now(UTC) - timedelta(days=14)
    monkeypatch.setattr(settings, "inspection_workflow_from", start)
    with factory.begin() as db:
        db.get(Store, ids["store"]).store_code = code
    first = capture(client, headers["manager"], {"area": "cashier"})
    first.raise_for_status()
    response = client.post(BASE + "/photos", headers=headers["manager"], json={**first.json(), "area": "cashier"})
    response.raise_for_status()
    assert process_next(factory, provider=lambda *args: FIX)
    return client.get(BASE, headers=headers["manager"]).json()["open_issues"][0]


def capture(client, manager, root, *, issue=None):
    frame = BytesIO()
    Image.new("RGB", (42, 39), "orange" if issue is None else "green").save(frame, "JPEG")
    data = {"area": root["area"], "business_date": _today().isoformat()}
    if issue is not None:
        data["issue_id"] = issue
    return client.post(BASE + "/camera-captures", headers=manager, data=data,
                       files={"file": ("frame.jpg", frame.getvalue(), "image/jpeg")})


@pytest.mark.parametrize("code", ["hxy-anyang-ziwei-001", "hxy-anyang-huafu-002"])
def test_store_recaptures_until_original_problem_visibly_resolved(daily, monkeypatch, code):
    client, factory, ids, headers = daily
    manager = headers["manager"]
    issue = make_case(daily, monkeypatch, code)
    url = BASE + f"/issues/{issue['id']}/followups"
    with factory.begin() as db:
        day = db.query(DailyStoreCheckin).one()
        day.business_date = _today() - timedelta(days=1)
        day.status, day.submitted_at = "submitted", datetime.now(UTC) - timedelta(hours=2)
        checkin_id, original_submit = day.id, day.submitted_at
    generic = capture(client, manager, issue)
    generic.raise_for_status()
    assert client.post(url, headers=manager, json={**generic.json(), "expected_review_id": issue["id"]}).status_code == 409
    ticket = capture(client, manager, issue, issue=issue["id"])
    ticket.raise_for_status()
    payload = {**ticket.json(), "expected_review_id": issue["id"]}
    assert client.post(url, headers=headers["admin"], json=payload).status_code == 403
    first = client.post(url, headers=manager, json=payload)
    first.raise_for_status()
    assert client.post(url, headers=manager, json=payload).json() == first.json()
    assert client.post(BASE + "/photos", headers=manager, json={**ticket.json(), "area": "cashier"}).status_code == 409

    def compare(area, jpeg, key, *, before, original_result):
        assert before and jpeg and before != jpeg and original_result == FIX and area == "cashier"
        return RETAKE
    assert process_next(factory, provider=compare)
    open_issue = client.get(BASE, headers=manager).json()["open_issues"][0]
    assert open_issue["status"] == "retake" and open_issue["followup_count"] == 1
    second = capture(client, manager, issue, issue=issue["id"]).json()
    assert client.post(url, headers=manager, json={**second, "expected_review_id": issue["id"]}).status_code == 409
    client.post(url, headers=manager, json={**second, "expected_review_id": open_issue["expected_review_id"]}).raise_for_status()
    assert process_next(factory, provider=lambda *args, **kw: PASS)
    assert client.get(BASE, headers=manager).json()["open_issues"] == []
    with factory() as db:
        record = db.get(DailyStoreCheckin, checkin_id)
        assert record.status == "submitted" and record.submitted_at.replace(tzinfo=UTC) == original_submit
        assert db.get(DailyAreaPhotoReview, issue["id"]).result == FIX
        assert db.query(InspectionFollowup).count() == 2


def bind(db, staff, userid):
    identity = StaffExternalIdentity(provider="wecom", corp_id=settings.wecom_corp_id, userid=userid,
                                     staff_id=staff.id, store_id=staff.store_id, status="active")
    db.add_all([identity, StaffScopeAssignment(staff_id=staff.id, scope_type="store", role="store_manager",
                                               scope_id=staff.store_id, status="active")])
    db.flush()
    return identity


class SyntheticWecom:
    def __init__(self):
        self.calls = []
        self.error = None

    def send_textcard(self, users, title, body, url, button):
        self.calls.append(("store", users, url))
        if self.error:
            raise self.error()
        return WecomMessageReceipt("accepted", 1, 0)

    def send_text(self, users, body):
        self.calls.append(("weekly", users, body))
        return WecomMessageReceipt("accepted", 1, 0)


@pytest.mark.parametrize(("error", "state"), [(None, "accepted"), (WecomProviderError, "unknown"), (WecomMessageRejected, "rejected")])
def test_recipient_separation_weekly_cutoff_and_idempotent_delivery(daily, monkeypatch, error, state):
    client, factory, ids, _ = daily
    issue = make_case(daily, monkeypatch, "hxy-anyang-huafu-002")
    monkeypatch.setattr(settings, "wecom_staff_enabled", True)
    monkeypatch.setattr(settings, "wecom_corp_id", "synthetic-corp")
    monkeypatch.setattr(settings, "inspection_wecom_enabled", True)
    with factory.begin() as db:
        local = db.get(Staff, ids["manager"])
        bind(db, local, "store-recipient")
        contact = Staff(username="summary", name="Summary", role="manager", password_hash="unused", store_id=local.store_id)
        db.add(contact)
        db.flush()
        weekly = bind(db, contact, "weekly-recipient")
        monkeypatch.setattr(settings, "inspection_weekly_binding_id", weekly.id)
        monkeypatch.setattr(settings, "inspection_weekly_binding_version", weekly.binding_version)
        db.add(Store(store_code="hxy-anyang-ziwei-001", name="Other store", address="Synthetic"))
        day = db.query(DailyStoreCheckin).one()
        day.status, day.submitted_at = "submitted", datetime.now(UTC)
    service = SyntheticWecom()
    service.error = error
    start = _today() - timedelta(days=_today().weekday())
    monday = datetime.combine(start + timedelta(days=7), time(9), SHANGHAI)
    assert weekly_due(monday - timedelta(seconds=1)) == start - timedelta(days=7)
    assert weekly_due(monday) == start
    for _ in range(2):
        enqueue(factory, now=monday)
        while deliver_next(factory, now=monday, provider=service):
            pass
    assert len(service.calls) == 2
    card = next(c for c in service.calls if c[0] == "store")
    query = parse_qs(urlsplit(card[2]).query)
    assert card[1] == ["store-recipient"] and query["inspection"] == [str(issue["id"])] and query["notice"]
    summary = next(c for c in service.calls if c[0] == "weekly")
    assert summary[1] == ["weekly-recipient"] and "没有已提交日报" in summary[2]
    with factory() as db:
        assert db.query(InspectionDelivery).filter_by(root_id=issue["id"]).one().state == state
        metrics = summarize_week(db, start, as_of=monday)["hxy-anyang-huafu-002"]
        assert metrics["outstanding"] == 1 and metrics["closed"] == 0 and metrics["fix"] == 1
        assert metrics["no_record"] == 6
        weekly_message = db.query(InspectionDelivery).filter_by(week_start=start).one()
        assert weekly_message.summary_text == summary[2].split("\n\n查看完整周报：")[0]
        assert weekly_message.opened_at is None
        assert parse_qs(urlsplit(summary[2].split("查看完整周报：")[1]).query)["notice"] != query["notice"]


def test_other_store_and_historical_manual_corrections(daily, monkeypatch):
    client, factory, ids, headers = daily
    issue = make_case(daily, monkeypatch, "hxy-anyang-huafu-002")
    with factory.begin() as db:
        other = Store(store_code="hxy-anyang-ziwei-001", name="Synthetic other", address="Synthetic")
        db.add(other)
        db.flush()
        staff = Staff(store_id=other.id, username="other", role="manager", name="Other", password_hash="unused")
        db.add(staff)
        db.flush()
        other_headers = {"Authorization": "Bearer " + create_staff_token(staff.id, staff.role)}
    assert client.get(BASE, headers=other_headers).json()["open_issues"] == []
    assert capture(client, other_headers, issue, issue=issue["id"]).status_code == 404
    start = _today() - timedelta(days=_today().weekday())
    end = datetime.combine(start + timedelta(days=7), time.min, SHANGHAI)
    with factory.begin() as db:
        original = db.get(DailyAreaPhotoReview, issue["id"])
        original.manual_verdict, original.manual_at = "pass", datetime.now(UTC)
        metrics = summarize_week(db, start, as_of=end)["hxy-anyang-huafu-002"]
        assert (metrics["draft"], metrics["draft_points"], metrics["draft_expected"]) == (1, 1, 12)
        day = db.query(DailyStoreCheckin).filter_by(store_id=ids["store"]).one()
        day.status, day.submitted_at = "submitted", datetime.now(UTC)
        db.flush()
        metrics = summarize_week(db, start, as_of=end)["hxy-anyang-huafu-002"]
        assert (metrics["legacy_manual"], metrics["fix"], metrics["outstanding"], metrics["closed"]) == (1, 1, 0, 0)
    assert client.get(BASE, headers=headers["manager"]).json()["open_issues"] == []


@pytest.mark.skipif(not os.environ.get("INSPECTION_TEST_POSTGRES_URL"), reason="requires isolated PostgreSQL")
def test_concurrent_recaptures_and_delivery_claims(monkeypatch):
    url = make_url(os.environ["INSPECTION_TEST_POSTGRES_URL"])
    assert url.database == "inspection_test" and url.host in {"localhost", "127.0.0.1"}
    control = create_engine(url)
    schema = "inspection_flow_" + uuid4().hex
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    factory = sessionmaker(engine, expire_on_commit=False)

    def isolated_db():
        with factory() as db:
            yield db

    try:
        Base.metadata.create_all(engine)
        with factory.begin() as db:
            store = Store(store_code="hxy-anyang-huafu-002", name="Synthetic store", address="Synthetic")
            db.add(store)
            db.flush()
            manager = Staff(store_id=store.id, username="case", role="manager", name="Local", password_hash="unused")
            contact = Staff(store_id=store.id, username="contact", role="manager", name="Weekly", password_hash="unused")
            db.add_all([manager, contact])
            db.flush()
            monkeypatch.setattr(settings, "wecom_corp_id", "synthetic")
            bind(db, manager, "local")
            weekly = bind(db, contact, "summary")
            ids = {"store": store.id, "manager": manager.id}
            header = {"Authorization": "Bearer " + create_staff_token(manager.id, manager.role)}
            monkeypatch.setattr(settings, "inspection_weekly_binding_id", weekly.id)
            monkeypatch.setattr(settings, "inspection_weekly_binding_version", weekly.binding_version)
        app.dependency_overrides[get_db] = isolated_db
        with TestClient(app) as client:
            issue = make_case((client, factory, ids, {"manager": header}), monkeypatch, "hxy-anyang-huafu-002")
            monkeypatch.setattr(settings, "inspection_workflow_from", datetime.now(UTC) - timedelta(minutes=5))
            monkeypatch.setattr(settings, "wecom_staff_enabled", True)
            monkeypatch.setattr(settings, "inspection_wecom_enabled", True)
            with ThreadPoolExecutor(max_workers=2) as workers:
                barrier = Barrier(2)
                def queue_one():
                    barrier.wait(timeout=8)
                    enqueue(factory)
                for future in [workers.submit(queue_one) for _ in range(2)]:
                    future.result(timeout=15)
                entered, release = Event(), Event()
                class SlowWecom(SyntheticWecom):
                    def send_textcard(self, *args):
                        entered.set()
                        assert release.wait(10)
                        return super().send_textcard(*args)
                service = SlowWecom()
                first = workers.submit(deliver_next, factory, provider=service)
                try:
                    assert entered.wait(10)
                    assert not deliver_next(factory, provider=service)
                finally:
                    release.set()
                assert first.result(timeout=10) and len(service.calls) == 1
                url_path = BASE + f"/issues/{issue['id']}/followups"
                payloads = [{**capture(client, header, issue, issue=issue["id"]).json(),
                             "expected_review_id": issue["id"]} for _ in range(2)]
                gate = Barrier(2)
                def submit_one(body):
                    gate.wait(timeout=8)
                    return client.post(url_path, headers=header, json=body).status_code
                futures = [workers.submit(submit_one, body) for body in payloads]
                assert sorted(f.result(timeout=15) for f in futures) == [200, 409]
            with factory() as db:
                assert db.query(InspectionFollowup).count() == db.query(InspectionDelivery).count() == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()
