import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token
from app.api.manager_daily import _checkin, _today, _capture_receipt
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    DailyAreaPhoto,
    DailyStoreCheckin,
    DailyMeetingRecording,
    LearningCourseVersion,
    MediaAsset,
    Staff,
    StaffLearningAssignment,
    Store,
    Technician,
    TrainingAssessment,
)

BASE = "/api/v1/admin/v2/manager/daily"


@pytest.fixture
def daily():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        store = Store(store_code="daily-store", name="Daily Store", address="Synthetic")
        db.add(store)
        db.flush()
        manager = Staff(username="daily-manager", name="店长", password_hash="unused", role="manager", store_id=store.id)
        admin = Staff(username="daily-admin", name="总部", password_hash="unused", role="admin", store_id=None)
        tech = Technician(store_id=store.id, code="daily-tech", name="技师甲", status="available")
        db.add_all([manager, admin, tech])
        db.flush()
        tech_staff = Staff(username="daily-tech", name="技师甲", password_hash="unused", role="technician",
                           store_id=store.id, technician_id=tech.id)
        db.add(tech_staff)
        db.flush()
        course = LearningCourseVersion(
            id=str(uuid.uuid4()), code="daily-course", version="1", status="published",
            content={"title": "足部精修", "sections": [{"id": "s1", "title": "基础"}, {"id": "s2", "title": "实操"}], "questions": []},
            content_sha256="x", approval_reference="",
        )
        db.add(course)
        db.flush()
        assignment = StaffLearningAssignment(
            id=str(uuid.uuid4()), store_id=store.id, staff_id=tech_staff.id, staff_name=tech_staff.name,
            course_version_id=course.id, assigned_by=manager.id, sections_read=["s1"], revision=1,
        )
        db.add(assignment)
        db.commit()
        ids = {"store": store.id, "manager": manager.id, "admin": admin.id, "tech_staff": tech_staff.id,
               "assignment": assignment.id}
        headers = {
            "manager": {"Authorization": "Bearer " + create_staff_token(manager.id, manager.role)},
            "admin": {"Authorization": "Bearer " + create_staff_token(admin.id, admin.role)},
        }
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, factory, ids, headers
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def _media(db, store_id, staff_id, media_type="image"):
    media = MediaAsset(store_id=store_id, object_key=f"test/{uuid.uuid4().hex}", original_name="x",
                       content_type="image/jpeg" if media_type == "image" else "audio/wav",
                       media_type=media_type, size_bytes=10, purpose="daily_area" if media_type == "image" else "meeting_audio",
                       created_by_staff_id=staff_id)
    db.add(media)
    db.flush()
    return media.id


def _frame(ids, area, media):
    return {"area": area, "media_id": media,
            "capture_receipt": _capture_receipt(ids["store"], ids["manager"], area, _today(), media)}


def test_capture_endpoint_requires_manager_and_binds_frame(daily):
    from io import BytesIO
    from PIL import Image
    client, factory, ids, headers = daily
    buf = BytesIO()
    Image.new("RGB", (48, 36), "green").save(buf, format="JPEG")
    file = {"file": ("inspection.jpg", buf.getvalue(), "image/jpeg")}
    data = {"area": "restroom", "business_date": _today().isoformat()}
    path = BASE + "/camera-captures"
    assert client.post(path, data=data, files=file).status_code == 401
    tech = {"Authorization": "Bearer " + create_staff_token(ids["tech_staff"], "technician")}
    assert client.post(path, data=data, files=file, headers=tech).status_code == 403
    manager = headers["manager"]
    assert client.post(path, data={**data, "business_date": "2000-01-01"}, files=file, headers=manager).status_code == 409
    assert client.post(path, data={**data, "area": "other"}, files=file, headers=manager).status_code == 422
    receipt = client.post(path, data=data, files=file, headers=manager)
    assert receipt.status_code == 201, receipt.text
    def save(area, body):
        return client.post(BASE + "/photos", headers=manager, json={"area": area, **body})
    frame = receipt.json()
    assert save("restroom", {"media_id": frame["media_id"]}).status_code == 409
    assert save("cashier", frame).status_code == 409
    other = client.post("/api/v1/admin/media", headers=manager, data={"purpose": "daily_area"}, files=file).json()
    assert save("restroom", {**frame, "media_id": other["id"]}).status_code == 409
    assert save("restroom", frame).status_code == 200
    with factory() as db:
        assert db.query(DailyAreaPhoto).one().media_id == frame["media_id"]


def test_daily_photos_meeting_submit(daily):
    client, factory, ids, headers = daily
    wav = b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little") + b"\x01\x00\x01\x00" + (16000).to_bytes(4, "little") + (32000).to_bytes(4, "little") + b"\x02\x00\x10\x00" + b"data" + (0).to_bytes(4, "little")
    uploaded = client.post("/api/v1/admin/media", headers=headers["manager"], data={"purpose": "meeting_audio"},
                           files={"file": ("meeting.wav", wav, "audio/wav")})
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["media_type"] == "audio"

    initial = client.get(BASE, headers=headers["manager"])
    assert initial.status_code == 200, initial.text
    assert initial.json()["completion"]["areas_done"] == 0

    with factory() as db:
        media_ids = {area: _media(db, ids["store"], ids["manager"]) for area in
                     ("restroom", "water_room", "cashier", "rest_area", "foot_area", "herbal_prep")}
        audio_id = _media(db, ids["store"], ids["manager"], "audio")
        db.commit()
    for area, media_id in media_ids.items():
        response = client.post(BASE + "/photos", headers=headers["manager"], json=_frame(ids, area, media_id))
        assert response.status_code == 200, response.text
    response = client.post(BASE + "/meeting", headers=headers["manager"],
                           json={"media_id": audio_id, "duration_seconds": 600, "title": "晨会"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["completion"]["areas_done"] == data["completion"]["areas_total"] == 6
    assert data["completion"]["has_meeting"] is True
    assert data["meetings"][0]["transcript_status"] == "not_configured"

    submitted = client.post(BASE + "/submit", headers=headers["manager"])
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["completion"]["submitted"] is True
    replay = client.post(BASE + "/photos", headers=headers["manager"],
                         json={"area": "herbal_prep", "mode": "append", "media_id": media_ids["herbal_prep"]})
    assert replay.json()["submitted_at"] == submitted.json()["submitted_at"]
    assert client.post(BASE + "/submit", headers=headers["manager"]).json()["submitted_at"] == replay.json()["submitted_at"]


def test_photo_slots_and_targeted_replacement(daily):
    client, factory, ids, headers = daily
    with factory() as db:
        media = [_media(db, ids["store"], ids["manager"]) for _ in range(7)]
        other = Store(store_code="other-inspection", name="Other", address="Other")
        db.add(other)
        db.flush()
        foreign = _media(db, other.id, ids["manager"])
        unrelated = _media(db, ids["store"], ids["manager"])
        db.get(MediaAsset, unrelated).purpose = "general"
        db.commit()

    def save(media_id, area="herbal_prep", **kwargs):
        return client.post(BASE + "/photos", headers=headers["manager"],
                           json={**_frame(ids, area, media_id), "mode": "append", **kwargs})

    assert save(foreign).status_code == save(unrelated).status_code == 404
    assert save(media[0], business_date=str(_today() - timedelta(days=1))).status_code == 409
    assert client.post(BASE + "/photos",
                       headers={"Authorization": "Bearer " + create_staff_token(ids["tech_staff"], "technician")},
                       json={"area": "herbal_prep", "media_id": media[0]}).status_code == 403
    for photo_id in media[:3]:
        added = save(photo_id)
        assert added.status_code == 200, added.text
    view = added.json()
    assert view["completion"]["areas_done"] == 1 and view["completion"]["areas_total"] == 6
    photos = view["areas"][-1]["photos"]
    assert [p["slot"] for p in photos] == [1, 2, 3]
    assert view["areas"][-1]["photo"] == photos[0]
    assert save(media[2]).json()["areas"][-1]["photos"] == photos
    assert save(media[3]).json()["detail"]["code"] == "AREA_PHOTO_LIMIT"
    assert save(media[0], area="cashier").status_code == 409
    edit = {"mode": "replace", "photo_id": photos[1]["id"], "expected_media_id": media[1]}
    assert save(media[3], area="cashier", **edit).status_code in (404, 409)
    updated = save(media[3], **edit).json()["areas"][-1]["photos"]
    assert updated[0] == photos[0] and updated[2] == photos[2]
    assert updated[1]["id"] == photos[1]["id"] and updated[1]["media_id"] == media[3]
    assert save(media[3], **edit).json()["areas"][-1]["photos"] == updated
    assert save(media[4], **edit).json()["detail"]["code"] == "PHOTO_CHANGED"
    legacy = client.post(BASE + "/photos", headers=headers["manager"],
                         json={"area": "herbal_prep", "media_id": media[5]})
    assert legacy.status_code == 409
    assert client.get(BASE, headers=headers["manager"]).json()["areas"][-1]["photos"] == updated


def test_legacy_day_uses_original_checklist_and_open_draft_requires_herbal(daily):
    client, factory, ids, headers = daily
    previous = _today() - timedelta(days=1)
    with factory() as db:
        past = DailyStoreCheckin(store_id=ids["store"], manager_staff_id=ids["manager"],
                                 business_date=previous, status="submitted")
        draft = DailyStoreCheckin(store_id=ids["store"], manager_staff_id=ids["manager"], business_date=_today())
        db.add_all([past, draft])
        db.flush()
        old = ("restroom", "water_room", "cashier", "rest_area", "foot_area")
        for row in (past, draft):
            for area in old:
                db.add(DailyAreaPhoto(checkin_id=row.id, area=area, media_id=_media(db, ids["store"], ids["manager"]),
                                      created_by_staff_id=ids["manager"]))
        db.commit()
    historical = client.get(BASE, params={"date": str(previous)}, headers=headers["manager"]).json()
    assert historical["status"] == "submitted"
    assert historical["completion"]["areas_done"] == historical["completion"]["areas_total"] == 5
    assert client.get(BASE, params={"date": str(previous - timedelta(days=1))},
                      headers=headers["manager"]).json()["checkin_id"] is None
    today = client.get(BASE, headers=headers["manager"]).json()
    assert today["completion"]["areas_done"] == 5 and today["completion"]["areas_total"] == 6
    assert [a["key"] for a in today["areas"] if not a["done"]] == ["herbal_prep"]
    blocked = client.post(BASE + "/submit", headers=headers["manager"])
    assert blocked.status_code == 409 and "煮药区" in blocked.json()["detail"]["message"]
    with factory() as db:
        assert db.query(DailyStoreCheckin).count() == 2 and db.query(DailyAreaPhoto).count() == 10


@pytest.mark.skipif(not os.environ.get("INSPECTION_TEST_POSTGRES_URL"), reason="needs isolated PostgreSQL")
def test_concurrent_photos_use_three_slots_and_guard_retake():
    url = make_url(os.environ["INSPECTION_TEST_POSTGRES_URL"])
    assert url.database == "inspection_test" and url.host in {"localhost", "127.0.0.1"}
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        key = uuid.uuid4().hex[:12]
        store = Store(store_code=key, name="Synthetic", address="Synthetic")
        db.add(store)
        db.flush()
        manager = Staff(store_id=store.id, username=key, name="Synthetic", password_hash="unused", role="manager")
        db.add(manager)
        db.flush()
        media = [_media(db, store.id, manager.id) for _ in range(6)]
        ids = {"manager": manager.id, "store": store.id}
        headers = {"Authorization": "Bearer " + create_staff_token(manager.id, manager.role)}
        db.commit()

    def override():
        with factory() as db:
            yield db

    # An uncommitted first creator must still allow foreign keys to its store.
    with factory() as creator, factory() as uploader:
        _checkin(creator, store.id, manager.id, _today(), create=True)
        uploader.execute(text("SET LOCAL lock_timeout = '2s'"))
        _media(uploader, store.id, manager.id)
        uploader.commit()
        creator.rollback()

    def race(client, bodies):
        ready = Barrier(len(bodies))
        def post(body):
            ready.wait(timeout=20)
            return client.post(BASE + "/photos", json={**_frame(ids, "herbal_prep", body["media_id"]), **body}, headers=headers)
        with ThreadPoolExecutor(max_workers=len(bodies)) as workers:
            return list(workers.map(post, bodies))

    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            first = race(client, [{"mode": "append", "media_id": i} for i in media[:4]])
            assert sorted(r.status_code for r in first) == [200, 200, 200, 409]
            state = client.get(BASE, headers=headers).json()["areas"][-1]["photos"]
            assert [p["slot"] for p in state] == [1, 2, 3]
            changes = race(client, [{"mode": "replace", "media_id": i, "photo_id": state[1]["id"],
                                     "expected_media_id": state[1]["media_id"]} for i in media[4:]])
            assert sorted(r.status_code for r in changes) == [200, 409]
            result = client.get(BASE, headers=headers).json()["areas"][-1]["photos"]
            assert result[0] == state[0] and result[2] == state[2] and result[1]["media_id"] in media[4:]
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_team_and_hq_spot_check(daily):
    client, factory, ids, headers = daily
    overview = client.get(BASE + "/team", headers=headers["manager"])
    assert overview.status_code == 200, overview.text
    assert overview.json()["summary"]["staff_count"] == 1
    tech = overview.json()["technicians"][0]
    assert tech["name"] == "技师甲"
    assert tech["progress"] == 50

    confirmed = client.post(BASE + f"/team/{ids['tech_staff']}/assessments", headers=headers["manager"],
                            json={"course_name": "足部精修", "kind": "practical", "result": "passed",
                                  "assignment_id": ids["assignment"], "note": "店长确认"})
    assert confirmed.status_code == 200, confirmed.text
    assessment = confirmed.json()["technicians"][0]["assessment"]
    assert assessment["hq_status"] == "pending"

    with factory() as db:
        row = db.query(TrainingAssessment).one()
        assessment_id = row.id
    queue = client.get("/api/v1/admin/v2/headquarters/assessments?status=pending", headers=headers["admin"])
    assert queue.status_code == 200, queue.text
    assert len(queue.json()["items"]) == 1
    checked = client.post(f"/api/v1/admin/v2/headquarters/assessments/{assessment_id}/spot-check",
                          headers=headers["admin"], json={"hq_status": "passed", "note": "总部抽检通过"})
    assert checked.status_code == 200, checked.text
    assert checked.json()["hq_status"] == "passed"


def test_huafu_named_rooms_are_separate_required_camera_points(daily, monkeypatch):
    from io import BytesIO
    from PIL import Image
    from app.core.config import settings
    from app.models import DailyAreaPhotoReview

    client, factory, ids, headers = daily
    auth = headers["manager"]
    monkeypatch.setattr(settings, "inspection_ai_enabled", True)
    monkeypatch.setattr(settings, "inspection_ai_api_key", "synthetic")
    with factory() as db:
        db.get(Store, ids["store"]).store_code = "hxy-anyang-huafu-002"
        audio = _media(db, ids["store"], ids["manager"], "audio")
        db.commit()
    buf = BytesIO()
    Image.new("RGB", (30, 20), "green").save(buf, format="JPEG")
    files = {"file": ("frame.jpg", buf.getvalue(), "image/jpeg")}
    def capture(area):
        response = client.post(BASE + "/camera-captures", headers=auth, files=files,
                               data={"area": area, "business_date": _today().isoformat()})
        assert response.status_code == 201, response.text
        return response.json()
    def append(area, receipt):
        return client.post(BASE + "/photos", headers=auth, json={"area": area, "mode": "append", **receipt})
    first = capture("spa_banxia")
    assert append("spa_duruo", first).status_code == 409
    assert append("spa_banxia", first).status_code == 200
    assert append("spa_banxia", first).status_code == 200
    view = client.get(BASE, headers=auth).json()
    assert view["completion"]["areas_total"] == 12
    rooms = {a["key"]: a["label"] for a in view["areas"] if a.get("group") == "spa_rooms"}
    assert rooms == {"spa_banxia": "半夏", "spa_rendong": "忍冬", "spa_duruo": "杜若", "spa_qingdai": "青黛"}
    for _ in range(2):
        assert append("spa_banxia", capture("spa_banxia")).status_code == 200
    assert append("spa_banxia", capture("spa_banxia")).status_code == 409
    for point in view["areas"]:
        if point["key"] not in {"spa_banxia", "spa_qingdai"}:
            assert append(point["key"], capture(point["key"])).status_code == 200
    assert client.post(BASE + "/meeting", headers=auth, json={"media_id": audio, "duration_seconds": 60}).is_success
    missing = client.post(BASE + "/submit", headers=auth)
    assert missing.status_code == 409
    assert missing.json()["detail"]["message"] == "请补齐SPA 房·青黛"
    assert missing.json()["detail"]["areas_done"] == 11
    assert append("spa_qingdai", capture("spa_qingdai")).is_success
    submitted = client.post(BASE + "/submit", headers=auth).json()
    assert submitted["status"] == "submitted" and submitted["completion"]["areas_done"] == 12
    assert client.post(BASE + "/submit", headers=auth).json()["submitted_at"] == submitted["submitted_at"]
    with factory() as db:
        assert db.query(DailyStoreCheckin).one().checklist_version == 3
        assert db.query(DailyAreaPhoto).count() == db.query(DailyAreaPhotoReview).count() == 14


def test_huafu_checklist_is_store_scoped_and_frozen_per_day(daily):
    client, factory, ids, headers = daily
    auth = headers["manager"]
    today = _today()
    yesterday = today - timedelta(days=1)
    with factory() as db:
        db.get(Store, ids["store"]).store_code = "hxy-anyang-ziwei-001"
        db.commit()
    assert len(client.get(BASE, headers=auth).json()["areas"]) == 6
    assert client.post(BASE + "/photos", headers=auth, json={"area": "warehouse", "media_id": 99}).status_code == 422
    with factory() as db:
        db.get(Store, ids["store"]).store_code = "hxy-anyang-huafu-002"
        db.add(DailyStoreCheckin(store_id=ids["store"], manager_staff_id=ids["manager"],
                                 business_date=yesterday, checklist_version=2, status="submitted"))
        db.commit()
    assert len(client.get(BASE, headers=auth).json()["areas"]) == 6
    past = client.get(BASE, headers=auth, params={"date": yesterday.isoformat()}).json()
    assert past["status"] == "submitted" and len(past["areas"]) == 6
    assert all("group" not in area for area in past["areas"])
