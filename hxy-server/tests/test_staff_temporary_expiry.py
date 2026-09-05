from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import Staff, Store, Technician


def test_expired_temporary_staff_cannot_login():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        store = Store(store_code="expiry-store", name="测试门店", address="测试地址")
        db.add(store)
        db.flush()
        technician = Technician(store_id=store.id, code="temporary-tech", name="临时技师")
        db.add(technician)
        db.flush()
        db.add(Staff(
            username="temporary-tech",
            password_hash=hash_password("pass"),
            name="临时技师",
            role="technician",
            status="active",
            store_id=store.id,
            technician_id=technician.id,
            temporary_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        ))
        db.commit()

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).post(
            "/api/v1/admin/login",
            json={"username": "temporary-tech", "password": "pass"},
        )
        assert response.status_code == 401
        assert "过期" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_active_temporary_staff_can_login_and_receives_store_context():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        store = Store(store_code="active-store", name="有效门店", address="测试地址")
        db.add(store)
        db.flush()
        technician = Technician(store_id=store.id, code="active-temporary-tech", name="有效临时技师")
        db.add(technician)
        db.flush()
        db.add(Staff(
            username="active-temporary-tech",
            password_hash=hash_password("pass"),
            name="有效临时技师",
            role="technician",
            status="active",
            store_id=store.id,
            technician_id=technician.id,
            temporary_expires_at=datetime.now(timezone.utc) + timedelta(days=15),
        ))
        db.commit()

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).post(
            "/api/v1/admin/login",
            json={"username": "active-temporary-tech", "password": "pass"},
        )
        assert response.status_code == 200
        assert response.json()["staff"]["store_id"] == store.id
        assert response.json()["staff"]["role"] == "technician"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
