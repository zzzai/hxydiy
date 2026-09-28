from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import MembershipCard, Staff, Store, User


def test_entitlement_explanation_is_scoped_and_masked():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with sessions() as db:
        db.add_all([Store(id=1, store_code="card-one", name="One", address="Test"),
                    Store(id=2, store_code="card-two", name="Two", address="Test"),
                    User(id=1, openid="card-person", phone="13800138000")])
        db.flush()
        for identifier, role, store in [(1, "manager", 1), (2, "manager", 2), (3, "technician", 1), (4, "admin", None)]:
            db.add(Staff(id=identifier, username=f"card-staff-{identifier}", name="Test", role=role, store_id=store,
                         status="active", password_hash=hash_password("test")))
        db.add(MembershipCard(user_id=1, store_id=1, source="legacy_export", source_card_key="private-card-key",
                              card_type="stored", balance_cents=100, status="active",
                              started_at=datetime.now(UTC) - timedelta(days=1)))
        db.commit()

    def override():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            def read(identifier, role, suffix=""):
                return client.get("/api/v1/admin/v2/users/1/membership-entitlements" + suffix,
                                  headers={"Authorization": "Bearer " + create_staff_token(identifier, role)})
            response = read(1, "manager")
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["active"] is True
            assert data["cards"][0]["balance_cents"] == 100
            assert data["cards"][0]["balance_realtime"] is False
            assert data["cards"][0]["recorded_at"]
            assert len(data["cards"]) == 1
            assert "13800138000" not in response.text
            assert "private-card-key" not in response.text
            assert read(2, "manager").status_code == 404
            assert read(3, "technician").status_code == 403
            assert read(1, "manager", "?store_id=2").status_code == 403
            assert read(4, "admin", "?store_id=1").status_code == 200
            assert read(4, "admin").status_code == 422
            assert read(4, "admin", "?store_id=2").status_code == 404
            listed = client.get("/api/v1/admin/v2/users", headers={"Authorization": "Bearer " + create_staff_token(1, "manager")})
            assert [row["id"] for row in listed.json()["items"]] == [1]
            assert listed.json()["items"][0]["has_store_membership"] is True
            assert listed.json()["items"][0]["is_member"] is False
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
