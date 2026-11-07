from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import PageContent, PriceBook, Project, Room, Staff, Store, Technician
from app.services.store_lifecycle import build_store_opening_check


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as session:
        yield session


def _ready_store(db) -> Store:
    store = Store(
        store_code="opening-ready",
        name="即将开业门店",
        city="安阳",
        address="测试路 1 号",
        business_hours="10:00-22:00",
        phone="0372-0000000",
        status="preparing",
    )
    db.add(store)
    db.flush()
    technician = Technician(store_id=store.id, code="tech-01", name="技师一", status="available")
    db.add(technician)
    db.flush()
    db.add(Staff(
        username="manager-01", password_hash="x", name="店长", role="manager",
        store_id=store.id, technician_id=technician.id, status="active",
    ))
    db.add(Room(
        store_id=store.id, code="sofa-01", name="1号沙发", room_type="sofa",
        is_space_container=False, is_service_position=True, operational_status="active",
    ))
    project = Project(
        store_id=store.id, code="hxy-a", category="bath", name="项目A",
        publication_status="published", duration_min=60,
    )
    db.add(project)
    db.flush()
    db.add(PriceBook(project_id=project.id, price_type="store", amount_cents=10000))
    db.add(PageContent(store_id=store.id, page_key="diy-home", title="首页", published=True))
    db.commit()
    return store


def test_ready_store_passes_all_checks(db):
    store = _ready_store(db)
    result = build_store_opening_check(db, store)
    assert result["ready"] is True
    assert {item["key"] for item in result["checks"]} == {
        "store_profile", "manager", "technician", "service_position",
        "published_project", "project_price", "published_page",
    }


def test_missing_price_blocks_opening(db):
    store = _ready_store(db)
    project = db.query(Project).filter(Project.store_id == store.id).one()
    db.query(PriceBook).filter(PriceBook.project_id == project.id).delete()
    db.commit()
    result = build_store_opening_check(db, store)
    assert result["ready"] is False
    assert "project_price" in {item["key"] for item in result["checks"] if not item["passed"]}


def test_missing_manager_blocks_opening(db):
    store = _ready_store(db)
    db.query(Staff).filter(Staff.store_id == store.id).delete()
    db.commit()
    result = build_store_opening_check(db, store)
    assert result["ready"] is False
    assert "manager" in {item["key"] for item in result["checks"] if not item["passed"]}
    assert "technician" not in {item["key"] for item in result["checks"] if not item["passed"]}
