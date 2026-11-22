import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token
from app.api.manager_daily import _today
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
        response = client.post(BASE + "/photos", headers=headers["manager"], json={"area": area, "media_id": media_id})
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
                           json={"area": area, "media_id": media_id, "mode": "append", **kwargs})

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
    result = legacy.json()["areas"][-1]["photos"]
    assert result[0]["media_id"] == media[5] and result[1:] == updated[1:]


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
        headers = {"Authorization": "Bearer " + create_staff_token(manager.id, manager.role)}
        db.commit()

    def override():
        with factory() as db:
            yield db

    def race(client, bodies):
        ready = Barrier(len(bodies))
        def post(body):
            ready.wait(timeout=20)
            return client.post(BASE + "/photos", json={"area": "herbal_prep", **body}, headers=headers)
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
