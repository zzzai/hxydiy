import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models import Project, Staff, Store, Technician
from app.services.public_technicians import ProfileCard


@pytest.fixture
def directory_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for code, status in (("showcase-one", "open"), ("hxy-anyang-huafu-002", "trial_open"), ("closed", "closed")):
            db.add(Store(store_code=code, name=code, address="门店地址", status=status))
        db.flush()
        for pid, sid, status, visible in ((11, 1, "published", True), (12, 2, "published", True),
                                          (13, 1, "draft", True), (14, 1, "published", False)):
            db.add(Project(id=pid, store_id=sid, category="bath", code=f"bath-{pid}", name="草本泡",
                           publication_status=status, independently_visible=visible))
        rows = ((1, 1, "一号", "busy", "technician", "active"), (2, 1, "二号", "off", "technician", "active"),
                (3, 1, "模拟技师", "available", "technician", "active"), (4, 1, "未启用", "available", "technician", "disabled"),
                (5, 1, "店长", "available", "manager", "active"), (6, 1, "已离职", "resigned", "technician", "active"),
                (7, 2, "门店经理", "available", "manager", "active"))
        for tid, sid, name, status, role, account in rows:
            db.add(Technician(id=tid, store_id=sid, code=f"t-{tid}", name=name, status=status,
                              phone="internal-only", intro="private staff note", avatar_url="/private-photo",
                              skills=["11", 12, 13, 14, True]))
            db.flush()
            db.add(Staff(store_id=sid, technician_id=tid, username=f"private-staff-{tid}", password_hash="fixture",
                         role=role, status=account, name=name))
        db.commit()

    def scoped_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = scoped_db
    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_public_roster_visibility_and_request_qualification(directory_client):
    client, _ = directory_client
    response = client.get("/api/v1/stores/1/technicians")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    items = response.json()["items"]
    assert [p["label"] for p in items] == ["一号", "二号"]
    assert [p["project_ids"] for p in items] == [[11], [11]]
    assert [p["requestable_project_ids"] for p in items] == [[11], []]
    assert all(p["experience"] == p["portrait_url"] == p["introduction"] == "" and not p["tags"] for p in items)
    assert all(value not in response.text for value in ("internal-only", "private", "commission", "username", "hire_date"))
    assert client.get("/api/v1/stores/3/technicians").status_code == 404
    assert client.get("/api/v1/stores/999/technicians").status_code == 404


def test_phone_shaped_names_are_redacted_on_both_public_routes(directory_client):
    client, engine = directory_client
    with Session(engine) as db:
        db.get(Technician, 1).name = "130-0000-0123"
        db.commit()
    assert client.get("/api/v1/stores/1/technicians").json()["items"][0]["label"] == "技师 1"
    eligible = client.get("/api/v1/stores/1/projects/11/selectable-technicians").json()["items"]
    assert eligible[0]["label"] == "技师 1"


def test_display_only_numbers_are_not_accounts(directory_client):
    client, engine = directory_client
    with Session(engine) as db:
        before = db.execute(select(Technician.id, Technician.skills, Technician.updated_at)).all()
    for _ in range(2):
        response = client.get("/api/v1/stores/2/technicians")
        cards = response.json()["items"]
        assert [(p["label"], p["experience"]) for p in cards] == [
            ("1 号技师", "2 年"), ("6 号技师", "10 年"), ("03 号技师", ""), ("08 号技师", "新入行"),
            ("09 号技师", "10 年以上"), ("18 号技师", "10 年"), ("19 号技师", "10 年")]
        assert all(p["technician_id"] is None and p["project_ids"] == p["requestable_project_ids"] == [] for p in cards)
        assert not any(p["photos"] or p["tags"] or p["introduction"] for p in cards)
        photos = {p["key"]: p["portrait_url"] for p in cards if p["portrait_url"]}
        numbers = {"number-03": "03", "number-8": "08", "number-09": "09", "number-18": "18", "number-19": "19"}
        assert photos.keys() == numbers.keys()
        for key, url in photos.items():
            assert re.fullmatch(rf"/assets/technicians/hxy-anyang-huafu-002/portrait-{numbers[key]}-[a-f0-9]{{12}}\.webp", url)
        assert client.get("/api/v1/stores/2/technicians").json() == response.json()
    with Session(engine) as db:
        assert db.execute(select(Technician.id, Technician.skills, Technician.updated_at)).all() == before


def test_ziwei_portrait_numbers_do_not_become_account_ids(directory_client):
    client, engine = directory_client
    with Session(engine) as db:
        db.get(Store, 1).store_code = "hxy-anyang-ziwei-001"
        db.commit()

    items = client.get("/api/v1/stores/1/technicians").json()["items"]
    assert len(items) == 6
    for card, number in zip(items[:4], ("01", "03", "09", "10"), strict=True):
        assert (card["key"], card["label"]) == (f"number-{number}", f"{number} 号技师")
        assert re.fullmatch(rf"/assets/technicians/hxy-anyang-ziwei-001/portrait-{number}-[a-f0-9]{{12}}\.webp", card["portrait_url"])
        assert card["technician_id"] is None
        assert card["project_ids"] == card["requestable_project_ids"] == []
    named = items[4:]
    assert [(p["key"], p["label"], p["portrait_url"]) for p in named] == [
        ("staff-1", "一号", ""), ("staff-2", "二号", ""),
    ]
    assert [p["requestable_project_ids"] for p in named] == [[11], []]


def test_editorial_binding_is_store_scoped_and_does_not_duplicate_people(directory_client):
    client, _ = directory_client
    profile = ProfileCard(key="number-42", technician_id=1, label="42 号技师", experience="3 年",
                          introduction="按您的习惯交流", tags=["安静型"], portrait_url="/assets/technicians/showcase-one/portrait.webp",
                          photos=[{"url": "/assets/technicians/showcase-one/work.webp", "caption": "服务现场"}])
    hidden = ProfileCard(key="retired", technician_id=6, label="离职")
    with patch("app.services.public_technicians.published_cards", return_value={
        "showcase-one": [profile, hidden], "hxy-anyang-huafu-002": [profile]}):
        cards = client.get("/api/v1/stores/1/technicians").json()["items"]
        assert [p["key"] for p in cards] == ["number-42", "staff-2"]
        assert cards[0]["tags"] == ["安静型"] and len(cards[0]["photos"]) == 1
        assert cards[0]["requestable_project_ids"] == [11]
        assert client.get("/api/v1/stores/2/technicians").json()["items"] == []
