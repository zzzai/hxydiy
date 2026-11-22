import base64
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import UTC, datetime, timedelta
from io import BytesIO
import json
import os
from threading import Barrier, Event
from uuid import uuid4

import httpx
from PIL import Image
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.api.admin import create_staff_token
from app.core.config import settings
from app.db.session import Base
from app.models import DailyAreaPhoto, DailyAreaPhotoReview, DailyStoreCheckin, MediaAsset, Staff, Store
from app.services.inspection_reviews import process_next
from app.services.inspection_vision import ENDPOINT, InspectionResult, VisionError, inspect_photo, inspection_jpeg
from app.api.manager_daily import _checkin, _today
from test_manager_daily import BASE, _media, daily

FIX = {"verdict": "fix", "location": "锅台左侧", "evidence": "散落药渣", "action": "清走药渣并擦净台面"}


def png(size=(32, 32)):
    data = BytesIO()
    Image.new("RGB", size, (36, 28, 19)).save(data, "PNG")
    return data.getvalue()


class SyntheticStorage:
    def read(self, key, limit):
        assert key.startswith("test/") and limit > 100
        return png()


def enable(monkeypatch):
    monkeypatch.setattr(settings, "inspection_ai_enabled", True)
    monkeypatch.setattr(settings, "inspection_ai_api_key", "synthetic")


def test_historical_review_runs_without_a_request_and_preserves_store_scope(daily, monkeypatch):
    client, factory, ids, headers = daily
    with factory.begin() as db:
        old = _media(db, ids["store"], ids["manager"])
        db.get(MediaAsset, old).created_at = datetime.now(UTC) - timedelta(days=2)
        foreign = Store(store_code="inspection-other", name="Other", address="Synthetic")
        db.add(foreign)
        db.flush()
        manager = Staff(username="inspection-other", name="Other", password_hash="unused", role="manager", store_id=foreign.id)
        db.add(manager)
        db.flush()
        other = {"Authorization": "Bearer " + create_staff_token(manager.id, "manager")}
    monkeypatch.setattr(settings, "inspection_ai_enabled", False)
    body = {"area": "herbal_prep", "mode": "append", "media_id": old}
    attached = client.post(BASE + "/photos", headers=headers["manager"], json=body)
    assert attached.status_code == 200, attached.text
    photo = attached.json()["areas"][-1]["photos"][0]
    assert photo["review"] is None and photo["reviewable"]
    assert not process_next(factory, provider=lambda *args: pytest.fail("disabled worker"))
    enable(monkeypatch)
    assert client.get(BASE, headers=headers["manager"]).json()["inspection_ai_enabled"]
    with factory() as db:
        assert db.query(DailyAreaPhotoReview).count() == 0
    url = BASE + f"/photos/{photo['id']}/review"
    req = {"media_id": old, "expected_attempt": 0}
    tech = {"Authorization": "Bearer " + create_staff_token(ids["tech_staff"], "technician")}
    for principal, code in [(other, 404), (headers["admin"], 403), (tech, 403), ({}, 401)]:
        assert client.post(url, headers=principal, json=req).status_code == code
    assert client.post(url, headers=headers["manager"], json={**req, "media_id": old + 1}).status_code == 409
    manual = url.replace("/review", "/manual-review")
    decision = {"media_id": old, "verdict": "pass"}
    assert client.post(manual, headers=headers["manager"], json=decision).status_code == 409
    assert process_next(factory, storage=SyntheticStorage(), provider=lambda *args: FIX)
    assert not process_next(factory, storage=SyntheticStorage(), provider=lambda *args: pytest.fail("duplicate send"))
    for _ in range(2):
        assert client.post(url, headers=headers["manager"], json=req).json()["review"]["state"] == "done"
    for principal, code in [(other, 404), (tech, 403)]:
        assert client.post(manual, headers=principal, json=decision).status_code == code
    for _ in range(2):
        view = client.post(manual, headers=headers["manager"], json=decision).json()["review"]
        assert view["manual_verdict"] == "pass" and view["result"] == FIX
    assert client.post(manual, headers=headers["manager"], json={**decision, "verdict": "retake"}).status_code == 409
    assert client.post(url, headers=headers["manager"], json=req).json()["review"]["attempt"] == 1
    with factory() as db:
        assert db.query(DailyAreaPhotoReview).count() == 1


def test_new_photo_automatic_retry_and_inflight_replacement(daily, monkeypatch):
    client, factory, ids, headers = daily
    enable(monkeypatch)
    with factory.begin() as db:
        first, second = [_media(db, ids["store"], ids["manager"]) for _ in range(2)]
    manager = headers["manager"]
    def save(media, **extra):
        response = client.post(BASE + "/photos", headers=manager,
                               json={"area": "herbal_prep", "media_id": media, "mode": "append", **extra})
        assert response.status_code == 200, response.text
        return response.json()["areas"][-1]["photos"][0]
    old = save(first)
    assert old["review"]["state"] == "pending" and save(first) == old
    url = BASE + f"/photos/{old['id']}/review"
    def quota(*args):
        raise VisionError("quota")
    assert process_next(factory, storage=SyntheticStorage(), provider=quota)
    failed = client.get(BASE, headers=manager).json()["areas"][-1]["photos"][0]["review"]
    assert failed == {"state": "failed", "result": None, "attempt": 1, "manual_verdict": None, "retry_scheduled": True}
    assert client.post(url, headers=manager, json={"media_id": first, "expected_attempt": 0}).status_code == 409
    assert not process_next(factory, provider=lambda *args: pytest.fail("backoff ignored"))
    with factory.begin() as db:
        db.query(DailyAreaPhotoReview).one().finished_at = datetime.now(UTC) - timedelta(minutes=3)
    def replace_while_running(area, image, key):
        assert area == "herbal_prep" and key == "synthetic" and image[:2] == bytes([255, 216])
        new = save(second, mode="replace", photo_id=old["id"], expected_media_id=first)
        assert new["review"]["state"] == "pending"
        return FIX
    assert process_next(factory, storage=SyntheticStorage(), provider=replace_while_running)
    with factory() as db:
        superseded = db.query(DailyAreaPhotoReview).filter_by(media_id=first).one()
        assert superseded.state == "superseded" and superseded.result is None and superseded.attempt == 2
    assert client.post(url, headers=manager, json={"media_id": first, "expected_attempt": 2}).status_code == 409
    assert process_next(factory, storage=SyntheticStorage(), provider=lambda *args: FIX)
    current = client.get(BASE, headers=manager).json()
    assert current["completion"]["areas_done"] == 1 and current["status"] == "draft"
    assert current["areas"][-1]["photos"][0]["review"]["result"] == FIX


def test_background_scan_only_uses_current_valid_store_photos(daily, monkeypatch):
    _, factory, ids, _ = daily
    enable(monkeypatch)
    with factory.begin() as db:
        other = Store(store_code="scope-filter", name="Other", address="Synthetic")
        db.add(other)
        db.flush()
        now = datetime.now(UTC)
        for i, problem in enumerate(("valid", "expired", "deleted", "foreign", "purpose", "audio")):
            check = _checkin(db, ids["store"], ids["manager"], _today() - timedelta(days=i), create=True)
            if problem == "expired":
                check.created_at = now - timedelta(days=91)
            media = _media(db, other.id if problem == "foreign" else ids["store"], ids["manager"])
            asset = db.get(MediaAsset, media)
            if problem == "deleted":
                asset.deleted_at = now
            if problem == "purpose":
                asset.purpose = "general"
            if problem == "audio":
                asset.media_type = "audio"
            photo = DailyAreaPhoto(checkin_id=check.id, area="herbal_prep", slot=1, media_id=media,
                                   created_by_staff_id=ids["manager"])
            db.add(photo)
            if problem == "valid":
                expected_media = media
    assert process_next(factory, storage=SyntheticStorage(), provider=lambda *args: FIX)
    assert not process_next(factory, provider=lambda *args: pytest.fail("non-inspection media sent"))
    with factory() as db:
        assert db.query(DailyAreaPhotoReview).one().media_id == expected_media


def test_failed_review_stops_after_bounded_automatic_retries(daily, monkeypatch):
    client, factory, ids, headers = daily
    enable(monkeypatch)
    with factory.begin() as db:
        media = _media(db, ids["store"], ids["manager"])
    client.post(BASE + "/photos", headers=headers["manager"], json={"area": "cashier", "media_id": media}).raise_for_status()
    def unavailable(*args):
        raise VisionError("provider_unavailable")
    for number in (1, 2, 3):
        assert process_next(factory, storage=SyntheticStorage(), provider=unavailable)
        with factory.begin() as db:
            row = db.query(DailyAreaPhotoReview).one()
            assert row.attempt == number
            row.finished_at = datetime.now(UTC) - timedelta(hours=1)
    assert not process_next(factory, storage=SyntheticStorage(), provider=lambda *args: pytest.fail("retry limit"))
    cashier = next(a for a in client.get(BASE, headers=headers["manager"]).json()["areas"] if a["key"] == "cashier")
    result = cashier["photos"][0]["review"]
    assert result["state"] == "failed" and result["result"] is None and not result["retry_scheduled"]


def test_image_and_provider_contract():
    exif = Image.Exif()
    exif[315] = "synthetic private metadata"
    raw = BytesIO()
    Image.new("RGB", (1600, 800)).save(raw, format="JPEG", exif=exif)
    body = inspection_jpeg(raw.getvalue(), 2_000_000)
    redacted = Image.open(BytesIO(body))
    assert redacted.size == (1280, 640) and not redacted.getexif()
    def provider(request):
        payload = json.loads(request.content)
        assert str(request.url) == ENDPOINT and request.headers["Authorization"] == "Bearer synthetic"
        content = payload["messages"][1]["content"]
        assert "煮药区" in content[0]["text"]
        prefix, encoded = content[1]["image_url"]["url"].split(",", 1)
        assert prefix == "data:image/jpeg;base64" and base64.b64decode(encoded) == body
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(FIX)}}]})
    assert inspect_photo("herbal_prep", body, "synthetic", transport=httpx.MockTransport(provider)) == FIX
    with pytest.raises(VisionError, match="image_unreadable"):
        inspection_jpeg(raw.getvalue(), 100)
    with pytest.raises(ValueError):
        InspectionResult.model_validate({**FIX, "action": "请联系13900000000清理"})


def test_stale_lease_and_expired_photo_do_not_resend(daily, monkeypatch):
    client, factory, ids, headers = daily
    enable(monkeypatch)
    with factory.begin() as db:
        media = _media(db, ids["store"], ids["manager"])
    photo = client.post(BASE + "/photos", headers=headers["manager"],
                       json={"area": "herbal_prep", "mode": "append", "media_id": media}).json()["areas"][-1]["photos"][0]
    with factory.begin() as db:
        review = db.query(DailyAreaPhotoReview).one()
        review.state, review.attempt = "running", 1
        review.started_at = datetime.now(UTC) - timedelta(minutes=5)
    assert not process_next(factory, provider=lambda *args: pytest.fail("interrupted job resubmitted"))
    with factory.begin() as db:
        review = db.query(DailyAreaPhotoReview).one()
        assert review.state == "failed" and review.error_code == "interrupted"
        db.query(DailyStoreCheckin).one().created_at = datetime.now(UTC) - timedelta(days=91)
    assert client.post(BASE + f"/photos/{photo['id']}/review", headers=headers["manager"],
                       json={"media_id": media, "expected_attempt": 1}).status_code == 404


@pytest.mark.skipif(not os.environ.get("INSPECTION_TEST_POSTGRES_URL"), reason="needs isolated PostgreSQL")
def test_concurrent_workers_discover_and_call_provider_once(monkeypatch):
    url = make_url(os.environ["INSPECTION_TEST_POSTGRES_URL"])
    assert url.database == "inspection_test" and url.host in {"localhost", "127.0.0.1"}
    control = create_engine(url)
    schema = "inspection_review_" + uuid4().hex
    with control.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    enable(monkeypatch)
    with factory.begin() as db:
        key = uuid4().hex[:12]
        store = Store(store_code=key, name="Synthetic", address="Synthetic")
        db.add(store)
        db.flush()
        manager = Staff(username=key, name="Synthetic", password_hash="unused", role="manager", store_id=store.id)
        db.add(manager)
        db.flush()
        checkin = _checkin(db, store.id, manager.id, _today(), create=True)
        media = _media(db, store.id, manager.id)
        photo = DailyAreaPhoto(checkin_id=checkin.id, area="herbal_prep", slot=1, media_id=media,
                              created_by_staff_id=manager.id)
        db.add(photo)
        db.flush()
    ready, release = Barrier(2), Event()
    calls = []
    def slow(*args):
        calls.append(1)
        assert release.wait(15)
        return FIX
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            def start():
                ready.wait(timeout=10)
                return process_next(factory, provider=slow, storage=SyntheticStorage())
            futures = [pool.submit(start) for _ in range(2)]
            try:
                completed, _ = wait(futures, timeout=8, return_when=FIRST_COMPLETED)
                assert completed and not next(iter(completed)).result()
            finally:
                release.set()
            assert sorted(f.result(timeout=10) for f in futures) == [False, True]
        with factory() as db:
            row = db.query(DailyAreaPhotoReview).filter_by(media_id=media).one()
            assert len(calls) == row.attempt == 1 and row.result == FIX
    finally:
        engine.dispose()
        with control.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


@pytest.mark.parametrize("status,body,code", [(402, {}, "quota"), (429, {}, "rate_limited"),
    (403, {}, "configuration"), (200, {"choices": []}, "invalid_result"),
    (200, {"choices": [{"finish_reason": "length"}]}, "invalid_result"),
    (200, {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}, "invalid_result")])
def test_unsuccessful_provider_has_no_verdict(status, body, code):
    provider = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    with pytest.raises(VisionError, match=code):
        inspect_photo("restroom", b"synthetic", "synthetic", transport=provider)
