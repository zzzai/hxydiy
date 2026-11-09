import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    DailyAreaPhoto,
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
                     ("restroom", "water_room", "cashier", "rest_area", "foot_area")}
        audio_id = _media(db, ids["store"], ids["manager"], "audio")
        db.commit()
    for area, media_id in media_ids.items():
        response = client.post(BASE + "/photos", headers=headers["manager"], json={"area": area, "media_id": media_id})
        assert response.status_code == 200, response.text
    response = client.post(BASE + "/meeting", headers=headers["manager"],
                           json={"media_id": audio_id, "duration_seconds": 600, "title": "晨会"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["completion"]["areas_done"] == 5
    assert data["completion"]["has_meeting"] is True
    assert data["meetings"][0]["transcript_status"] == "not_configured"

    submitted = client.post(BASE + "/submit", headers=headers["manager"])
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["completion"]["submitted"] is True


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
