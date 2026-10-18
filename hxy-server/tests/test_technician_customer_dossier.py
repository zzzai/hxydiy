from datetime import datetime, timedelta, timezone
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, PositionOccupancy, SelectionSession, Staff, Store, User
from app.models.operations import Room, Technician


@pytest.fixture
def dossier():
    url = os.environ.get("WECOM_TEST_DATABASE_URL")
    schema = "dossier_" + uuid.uuid4().hex
    if url:
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine.dispose()
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as db:
        stores = [Store(store_code=f"dossier-{n}", name="Synthetic", address="Synthetic") for n in range(2)]
        db.add_all(stores)
        db.flush()
        user = User(openid="synthetic-dossier", nickname="Synthetic", phone="13800000000", is_member=True, member_type="annual")
        technicians = [Technician(store_id=stores[n // 2].id, code=f"D{n}", name="Synthetic", status="available") for n in range(3)]
        db.add_all([user, *technicians])
        db.flush()
        staff = [Staff(username=f"dossier-{n}", password_hash="unused", role="technician", name="Synthetic", store_id=t.store_id, technician_id=t.id) for n, t in enumerate(technicians)]
        manager = Staff(username="dossier-manager", password_hash="unused", role="manager", store_id=stores[0].id)
        db.add_all([*staff, manager])
        db.flush()
        occupancies = []
        for n, tech in enumerate([technicians[0], technicians[1], technicians[2], technicians[0], technicians[0], technicians[0]]):
            room = Room(store_id=tech.store_id, code=f"R{n}", name=f"Room {n}", room_type="sofa")
            session = SelectionSession(id=f"dossier-session-{n}", store_id=tech.store_id, customer_id=None if n == 4 else user.id, access_token_hash="synthetic", status="submitted", items=[{"id": 7, "type": "project", "name": "Synthetic service", "quantity": 1, "price_cents": 9999, "customer_phone": "secret", "nested": {"secret": True}}])
            db.add_all([room, session])
            db.flush()
            occ = PositionOccupancy(store_id=tech.store_id, room_id=room.id, selection_session_id=session.id, serviced_by_technician_id=tech.id, active_room_id=room.id, active_session_id=session.id, status="in_service")
            if n == 3:
                occ.departed_at = datetime.now(timezone.utc)
            if n == 5:
                occ.status = "post_service_present"
                occ.actual_service_end_at = datetime.now(timezone.utc)
            db.add(occ)
            db.flush()
            occupancies.append(occ.id)
        db.commit()
        ids = dict(occupancies=occupancies, user_id=user.id, store_id=stores[0].id, other_store_id=stores[1].id, staff_id=staff[0].id, technician_id=technicians[0].id, manager_id=manager.id)
        headers = {"Authorization": f"Bearer {create_staff_token(staff[0].id, 'technician')}"}
        other_headers = {"Authorization": f"Bearer {create_staff_token(staff[1].id, 'technician')}"}
        manager_headers = {"Authorization": f"Bearer {create_staff_token(manager.id, 'manager')}"}
    def get_test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = get_test_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, factory, ids, headers, other_headers, manager_headers
    app.dependency_overrides.clear()
    engine.dispose()
    if url:
        cleanup = create_engine(url)
        with cleanup.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        cleanup.dispose()


def test_my_tasks_only_owned_present_and_minimal_items(dossier):
    client, _, ids, headers, *_ = dossier
    result = client.get("/api/v1/technician/my-tasks", headers=headers)
    assert result.status_code == 200, result.text
    assert [row["occupancy_id"] for row in result.json()["items"]] == [ids["occupancies"][5], ids["occupancies"][4], ids["occupancies"][0]]
    assert result.json()["items"][0]["items"] == [{"id": 7, "type": "project", "name": "Synthetic service", "quantity": 1}]


@pytest.mark.parametrize("suffix", ["customer-summary", "customer-history", "customer-reviews", "customer-reports", "customer-reports/x", "customer-tags"])
@pytest.mark.parametrize("index", [1, 2, 3])
def test_every_read_rechecks_owner_store_and_departure(dossier, suffix, index):
    client, _, ids, headers, *_ = dossier
    result = client.get(f"/api/v1/technician/occupancies/{ids['occupancies'][index]}/{suffix}", headers=headers)
    assert result.status_code == 404, result.text


def test_unbound_summary_and_details_are_distinct(dossier):
    client, _, ids, headers, *_ = dossier
    prefix = f"/api/v1/technician/occupancies/{ids['occupancies'][4]}"
    result = client.get(prefix + "/customer-summary", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["access"] == "unbound"
    for suffix in ["customer-history", "customer-reviews", "customer-reports", "customer-tags"]:
        response = client.get(prefix + "/" + suffix, headers=headers)
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "CUSTOMER_UNBOUND"


def test_summary_rejects_identity_override_and_audits_without_content(dossier):
    client, factory, ids, headers, *_ = dossier
    url = f"/api/v1/technician/occupancies/{ids['occupancies'][0]}/customer-summary"
    assert client.get(url + "?customer_id=999&phone=13800000000", headers=headers).status_code == 422
    result = client.get(url, headers=headers)
    assert result.status_code == 200, result.text
    assert set(result.json()) == {"occupancy_id", "customer_id", "customer_name", "access", "membership"}
    with factory() as db:
        logs = db.scalars(select(AuditLog).where(AuditLog.action == "technician_customer_read")).all()
        assert len(logs) == 1
        assert logs[0].detail == {"customer_id": ids["user_id"], "occupancy_id": ids["occupancies"][0], "resource": "summary"}


def test_report_gate_defaults_closed(dossier):
    client, _, ids, headers, *_ = dossier
    result = client.get(f"/api/v1/technician/occupancies/{ids['occupancies'][0]}/customer-reports", headers=headers)
    assert result.status_code == 403, result.text
    assert result.json()["detail"]["code"] == "REPORT_ACCESS_UNAVAILABLE"


def test_reviews_only_customer_submitted_service_feedback_without_internal_notes(dossier):
    from app.models.feedback import ServiceFeedback
    client, factory, ids, headers, *_ = dossier
    with factory() as db:
        db.add_all([
            ServiceFeedback(store_id=ids["store_id"], selection_session_id="dossier-session-5", customer_id=ids["user_id"], rating=5, note="Synthetic customer feedback", follow_up_note="PRIVATE INTERNAL"),
            ServiceFeedback(store_id=ids["other_store_id"], selection_session_id="dossier-session-2", customer_id=ids["user_id"], rating=1, note="Other store"),
            ServiceFeedback(store_id=ids["store_id"], selection_session_id="dossier-session-4", customer_id=None, rating=2, note="Anonymous"),
        ])
        db.commit()
    result = client.get(f"/api/v1/technician/occupancies/{ids['occupancies'][0]}/customer-reviews", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["total"] == 1
    assert result.json()["items"][0]["rating"] == 5
    assert result.json()["items"][0]["content"] == "Synthetic customer feedback"
    assert result.json()["items"][0]["feedback_type"] == "service"
    assert result.json()["items"][0]["source"] == "completed_service"
    assert result.json()["items"][0]["projects"] == [{"name": "Synthetic service", "quantity": 1}]
    assert "PRIVATE INTERNAL" not in result.text


def test_authenticated_visit_feedback_is_customer_store_bound_without_inferred_service(dossier):
    from app.models.feedback import VisitFeedback
    client, factory, ids, headers, *_ = dossier
    with factory() as db:
        own_room = db.get(PositionOccupancy, ids["occupancies"][0]).room_id
        other_room = db.get(PositionOccupancy, ids["occupancies"][2]).room_id
        for n, (customer, store, room) in enumerate([
            (ids["user_id"], ids["store_id"], own_room),
            (None, ids["store_id"], own_room),
            (ids["user_id"], ids["other_store_id"], other_room),
        ]):
            db.add(VisitFeedback(customer_id=customer, store_id=store, room_id=room, source="store_qr", identity_hash=f"PRIVATE-ID-{n}", idempotency_key_hash=f"PRIVATE-KEY-{n}", request_fingerprint=f"PRIVATE-FP-{n}", rating=4, tags=["Synthetic visit"], note=f"Visit {n}", follow_up_note="PRIVATE INTERNAL"))
        db.commit()
    result = client.get(f"/api/v1/technician/occupancies/{ids['occupancies'][0]}/customer-reviews", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["total"] == 1
    row = result.json()["items"][0]
    assert row["feedback_type"] == "visit"
    assert row["source"] == "store_qr"
    assert row["tags"] == ["Synthetic visit"]
    assert row["content"] == "Visit 0"
    assert row["projects"] == []
    assert "PRIVATE" not in result.text


def test_history_is_customer_store_linked_and_does_not_expose_private_profiles(dossier):
    client, factory, ids, headers, *_ = dossier
    with factory() as db:
        for index in (0, 1, 2, 5):
            db.get(PositionOccupancy, ids["occupancies"][index]).actual_start_at = datetime.now(timezone.utc)
        db.commit()
    result = client.get(f"/api/v1/technician/occupancies/{ids['occupancies'][0]}/customer-history?page_size=2", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["total"] == 3
    assert [item["id"] for item in result.json()["items"]] == [ids["occupancies"][5], ids["occupancies"][1]]
    assert result.json()["items"][0]["projects"] == [{"name": "Synthetic service", "quantity": 1}]
    assert "price_cents" not in result.text


@pytest.mark.parametrize("change", ["released", "selection_cancelled", "active_room_cleared", "active_session_cleared", "owner_changed"])
def test_dossier_revalidates_scope_after_previous_success(dossier, change):
    client, factory, ids, headers, *_ = dossier
    url = f"/api/v1/technician/occupancies/{ids['occupancies'][0]}/customer-summary"
    assert client.get(url, headers=headers).status_code == 200
    with factory() as db:
        occupancy = db.get(PositionOccupancy, ids["occupancies"][0])
        if change == "released":
            occupancy.released_at = datetime.now(timezone.utc)
        elif change == "selection_cancelled":
            db.get(SelectionSession, occupancy.selection_session_id).status = "cancelled"
        elif change == "active_room_cleared":
            occupancy.active_room_id = None
        elif change == "active_session_cleared":
            occupancy.active_session_id = None
        else:
            occupancy.serviced_by_technician_id = None
        db.commit()
    assert client.get(url, headers=headers).status_code == 404


def test_reports_require_explicit_service_purpose_evidence_and_project_only_normalized_sections(dossier):
    from app.services.technician_reports import ServicePurposeEvidence, TechnicianReportAccess, get_technician_report_access
    client, _, ids, headers, *_ = dossier
    url = f"/api/v1/technician/occupancies/{ids['occupancies'][0]}/customer-reports"
    row = {"id": "synthetic-report", "title": "Synthetic report", "created_at": None, "store_id": ids["store_id"], "customer_id": ids["user_id"], "sections": [{"title": "Synthetic only", "content": "Synthetic content", "face_url": "https://example.invalid/private"}], "original_url": "https://example.invalid/private"}
    def evidence(**context):
        return ServicePurposeEvidence(**context, purpose="current_service", expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))
    app.dependency_overrides[get_technician_report_access] = lambda: TechnicianReportAccess(True, evidence, lambda **_: [row])
    listed = client.get(url, headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == [{"id": "synthetic-report", "created_at": None, "title": "Synthetic report"}]
    detail = client.get(url + "/synthetic-report", headers=headers)
    assert detail.json() == {"id": "synthetic-report", "created_at": None, "title": "Synthetic report", "sections": [{"title": "Synthetic only", "content": "Synthetic content"}]}
    assert "url" not in detail.text
    app.dependency_overrides[get_technician_report_access] = lambda: TechnicianReportAccess(True, lambda **_: None, lambda **_: [row])
    assert client.get(url, headers=headers).status_code == 403
    app.dependency_overrides[get_technician_report_access] = lambda: TechnicianReportAccess(True, evidence, lambda **_: [{**row, "customer_id": 999}])
    assert client.get(url, headers=headers).status_code == 403


def test_my_tasks_has_hard_limit_of_one_hundred(dossier):
    client, factory, ids, headers, *_ = dossier
    with factory() as db:
        for n in range(101):
            room = Room(store_id=ids["store_id"], code=f"LIMIT-{n}", name="Synthetic", room_type="sofa")
            session = SelectionSession(id=f"limit-session-{n}", store_id=ids["store_id"], customer_id=ids["user_id"], access_token_hash="synthetic", status="confirmed", items=[])
            db.add_all([room, session])
            db.flush()
            db.add(PositionOccupancy(store_id=ids["store_id"], room_id=room.id, active_room_id=room.id, active_session_id=session.id, selection_session_id=session.id, serviced_by_technician_id=ids["technician_id"], status="in_service"))
        db.commit()
    result = client.get("/api/v1/technician/my-tasks", headers=headers)
    assert result.status_code == 200, result.text
    assert len(result.json()["items"]) == 100
