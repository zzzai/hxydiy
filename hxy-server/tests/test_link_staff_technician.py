from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import AuditLog, Staff, Store, Technician
from scripts.link_staff_technician import apply_plan, build_plan


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


def _seed(db):
    store = Store(store_code="store-1", name="门店一", address="地址一", status="open")
    other_store = Store(store_code="store-2", name="门店二", address="地址二", status="preparing")
    db.add_all([store, other_store])
    db.flush()
    manager = Staff(username="manager-1", password_hash="x", name="店长一", role="manager", store_id=store.id, status="active")
    other_manager = Staff(username="manager-2", password_hash="x", name="店长二", role="manager", store_id=store.id, status="active")
    db.add_all([manager, other_manager])
    technician = Technician(store_id=store.id, code="tech-manager", name="店长一", status="available")
    other_technician = Technician(store_id=other_store.id, code="tech-other", name="外店技师", status="available")
    db.add_all([technician, other_technician])
    db.commit()
    return {
        "store": store, "other_store": other_store,
        "manager": manager, "other_manager": other_manager,
        "technician": technician, "other_technician": other_technician,
    }


def test_preview_does_not_write(db):
    seeded = _seed(db)
    plan = build_plan(db, staff_id=seeded["manager"].id, technician_code="tech-manager")
    assert plan["action"] == "link"
    assert plan["preview_hash"]
    assert db.get(Staff, seeded["manager"].id).technician_id is None


def test_apply_links_manager_and_audits(db):
    seeded = _seed(db)
    plan = build_plan(db, staff_id=seeded["manager"].id, technician_code="tech-manager")
    result = apply_plan(db, plan)
    db.commit()
    assert result["action"] == "linked"
    assert db.get(Staff, seeded["manager"].id).technician_id == seeded["technician"].id
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "staff_technician_linked"))
    assert audit is not None
    assert audit.store_id == seeded["store"].id
    assert audit.detail["after_technician_id"] == seeded["technician"].id


def test_apply_is_idempotent(db):
    seeded = _seed(db)
    plan = build_plan(db, staff_id=seeded["manager"].id, technician_code="tech-manager")
    apply_plan(db, plan)
    db.commit()
    same_plan = build_plan(db, staff_id=seeded["manager"].id, technician_code="tech-manager")
    assert same_plan["preview_hash"] == plan["preview_hash"]
    assert same_plan["action"] == "unchanged"
    result = apply_plan(db, same_plan)
    db.commit()
    assert result["action"] == "unchanged"
    assert db.get(Staff, seeded["manager"].id).technician_id == seeded["technician"].id


def test_rejects_cross_store_technician(db):
    seeded = _seed(db)
    with pytest.raises(ValueError, match="同一门店"):
        build_plan(db, staff_id=seeded["manager"].id, technician_code="tech-other")


def test_rejects_technician_already_linked(db):
    seeded = _seed(db)
    seeded["other_manager"].technician_id = seeded["technician"].id
    db.commit()
    with pytest.raises(ValueError, match="已被其他员工绑定"):
        build_plan(db, staff_id=seeded["manager"].id, technician_code="tech-manager")


def test_rejects_non_manager_account(db):
    seeded = _seed(db)
    staff = Staff(username="staff-1", password_hash="x", name="店员", role="staff", store_id=seeded["store"].id, status="active")
    db.add(staff)
    db.commit()
    with pytest.raises(ValueError, match="只有店长"):
        build_plan(db, staff_id=staff.id, technician_code="tech-manager")
