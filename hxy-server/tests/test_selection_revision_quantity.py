"""Cumulative revisions add only newly requested units after approval."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token
from app.api.selections import _added_items
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    PositionOccupancy, PriceBook, Project, Room, SelectionChangeRequest,
    SelectionRevision, SelectionSession, ServiceLine, Staff, Store,
)


@pytest.mark.parametrize("previous,current,want", [
    ([1], [2], [1]),
    ([2], [3], [1]),
    ([1, 2], [4], [1]),
    ([2], [1, 3], [2]),
    ([3], [2], []),
    ([2], [2], []),
])
def test_quantity_delta_consumes_previous_units_not_rows(previous, current, want):
    before = [{"project_id": 7, "quantity": qty} for qty in previous]
    after = [{"project_id": 7, "quantity": qty} for qty in current]
    original = deepcopy(after)
    assert [item["quantity"] for item in _added_items(before, after)] == want
    assert after == original


@pytest.mark.parametrize("changed", [
    {"option_choice_ids": [12]},
    {"catalog_version_id": 9},
    {"option_choice_id": 12},
])
def test_different_catalog_configuration_remains_an_addition(changed):
    before = {"project_id": 7, "quantity": 1, "catalog_version_id": 8,
              "option_choice_ids": [11], "option_choice_id": 11}
    after = {**before, **changed}
    assert _added_items([before], [after]) == [after]


@pytest.fixture
def flow():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_db():
        with sessions() as db:
            yield db

    prior_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_db
    with sessions.begin() as db:
        store = Store(store_code="revision-quantity", name="Fixture store", address="Fixture address")
        other_store = Store(store_code="revision-quantity-other", name="Other fixture", address="Other address")
        db.add_all([store, other_store])
        db.flush()
        project = Project(store_id=store.id, code="REV-QTY", name="Fixture service",
                          category="care", publication_status="published")
        room = Room(store_id=store.id, code="REV-QTY-ROOM", name="Fixture seat", room_type="sofa")
        staff = Staff(username="revision-manager", name="Fixture manager", role="manager",
                      store_id=store.id, password_hash="unused-fixture", status="active")
        other = Staff(username="revision-other", name="Other manager", role="manager",
                      store_id=other_store.id, password_hash="unused-fixture", status="active")
        employee = Staff(username="revision-staff", name="Fixture employee", role="staff",
                         store_id=store.id, password_hash="unused-fixture", status="active")
        db.add_all([project, room, staff, other, employee])
        db.flush()
        db.add(PriceBook(project_id=project.id, price_type="store", amount_cents=1000))
        data = SimpleNamespace(sessions=sessions, store_id=store.id, project_id=project.id, room_id=room.id,
                               staff_headers={"Authorization": "Bearer " + create_staff_token(staff.id, "manager")},
                               other_headers={"Authorization": "Bearer " + create_staff_token(other.id, "manager")},
                               employee_headers={"Authorization": "Bearer " + create_staff_token(employee.id, "staff")})
    try:
        with TestClient(app) as client:
            data.client = client
            created = client.post("/api/v1/selection-sessions", json={"store_id": data.store_id, "source": "tablet"})
            assert created.status_code == 200, created.text
            data.session_id = created.json()["session"]["id"]
            data.customer_headers = {"X-Selection-Token": created.json()["access_token"]}
            yield data
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(prior_overrides)
        engine.dispose()


def submit(flow, quantity, key, preferences=None):
    response = flow.client.post(
        f"/api/v1/selection-sessions/{flow.session_id}/revisions",
        headers={**flow.customer_headers, "Idempotency-Key": key},
        json={"items": [{"project_id": flow.project_id, "quantity": quantity,
                          "diy_preferences": preferences or []}]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def start_service(flow, quantity=1):
    initial = submit(flow, quantity, "initial")
    with flow.sessions.begin() as db:
        db.add(PositionOccupancy(store_id=flow.store_id, room_id=flow.room_id,
                                 active_room_id=flow.room_id, selection_session_id=flow.session_id,
                                 active_session_id=flow.session_id, status="waiting_service", source="tablet"))
    confirmed = flow.client.post(f"/api/v1/admin/v2/selection-sessions/{flow.session_id}/confirm",
                                 headers=flow.staff_headers)
    assert confirmed.status_code == 200, confirmed.text
    with flow.sessions.begin() as db:
        occupancy = db.scalar(select(PositionOccupancy).where(PositionOccupancy.selection_session_id == flow.session_id))
        occupancy.status = "in_service"
        line = db.scalar(select(ServiceLine).where(ServiceLine.selection_session_id == flow.session_id))
        line.state = "in_service"
    return initial


def change_id(flow, revision):
    with flow.sessions() as db:
        return db.scalar(select(SelectionChangeRequest.id).where(
            SelectionChangeRequest.selection_revision_id == revision["id"]))


def approve(flow, revision, headers=None):
    return flow.client.post(f"/api/v1/admin/v2/selection-change-requests/{change_id(flow, revision)}/approve",
                             headers=flow.staff_headers if headers is None else headers)


def state(flow):
    with flow.sessions() as db:
        session = db.get(SelectionSession, flow.session_id)
        return deepcopy(session.items), deepcopy(session.pricing_snapshot)


def test_http_submitted_revisions_are_full_targets_with_quantity_deltas(flow):
    submit(flow, 1, "one")
    second = submit(flow, 2, "two")
    third = submit(flow, 3, "three")
    assert second["snapshot"]["items"][0]["quantity"] == 2
    assert third["snapshot"]["items"][0]["quantity"] == 3
    assert [item["quantity"] for item in second["snapshot"]["added_items"]] == [1]
    assert [item["quantity"] for item in third["snapshot"]["added_items"]] == [1]
    assert state(flow)[0][0]["quantity"] == 3


def test_http_confirmed_quantity_growth_waits_for_approval_and_is_idempotent(flow):
    initial = start_service(flow)
    baseline = state(flow)
    with flow.sessions() as db:
        frozen_revision = deepcopy(db.get(SelectionRevision, initial["id"]).snapshot)
        frozen_line = deepcopy(db.scalar(select(ServiceLine).where(ServiceLine.selection_session_id == flow.session_id)).snapshot)
    second = submit(flow, 2, "two")
    assert state(flow) == baseline
    assert submit(flow, 2, "two")["id"] == second["id"]
    assert [item["quantity"] for item in second["snapshot"]["added_items"]] == [1]
    first_approval = approve(flow, second)
    assert first_approval.status_code == 200, first_approval.text
    assert [line["snapshot"]["quantity"] for line in first_approval.json()["service_lines"]] == [1]
    replay = approve(flow, second)
    assert replay.status_code == 200 and replay.json() == first_approval.json()
    third = submit(flow, 3, "three")
    assert approve(flow, third).status_code == 200
    items, pricing = state(flow)
    assert sum(item["quantity"] for item in items) == 3
    assert pricing["payable_total_cents"] == 3000
    with flow.sessions() as db:
        assert db.get(SelectionRevision, initial["id"]).snapshot == frozen_revision
        assert db.get(ServiceLine, baseline[0][0]["service_line_id"]).snapshot == frozen_line
        assert db.query(ServiceLine).filter_by(selection_session_id=flow.session_id).count() == 3


@pytest.mark.parametrize("reject_first,want_preview", [(False, 2), (True, 2)])
def test_pending_targets_are_rebased_on_actual_confirmed_units_at_approval(flow, reject_first, want_preview):
    start_service(flow)
    baseline = state(flow)
    second = submit(flow, 2, "two")
    third = submit(flow, 3, "three")
    assert state(flow) == baseline
    assert sum(item["quantity"] for item in third["snapshot"]["added_items"]) == want_preview
    blocked = approve(flow, third)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "SELECTION_REVISION_OUT_OF_ORDER"
    if reject_first:
        rejected = flow.client.post(
            f"/api/v1/admin/v2/selection-change-requests/{change_id(flow, second)}/reject",
            headers=flow.staff_headers, json={"reason": "Fixture rejection"})
        assert rejected.status_code == 200, rejected.text
        assert state(flow) == baseline
    else:
        assert approve(flow, second).status_code == 200
    accepted = approve(flow, third)
    assert accepted.status_code == 200, accepted.text
    assert sum(item["quantity"] for item in state(flow)[0]) == 3
    assert sum(line["snapshot"]["quantity"] for line in accepted.json()["service_lines"]) == (2 if reject_first else 1)
    assert approve(flow, third).json() == accepted.json()
    assert sum(item["quantity"] for item in state(flow)[0]) == 3


def test_rejected_target_can_be_resubmitted_without_losing_its_added_unit(flow):
    start_service(flow)
    baseline = state(flow)
    rejected = submit(flow, 2, "rejected")
    response = flow.client.post(
        f"/api/v1/admin/v2/selection-change-requests/{change_id(flow, rejected)}/reject",
        headers=flow.staff_headers, json={"reason": "Fixture rejection"})
    assert response.status_code == 200
    assert state(flow) == baseline
    retry = submit(flow, 2, "retry")
    assert [item["quantity"] for item in retry["snapshot"]["added_items"]] == [1]
    assert approve(flow, retry).status_code == 200
    assert sum(item["quantity"] for item in state(flow)[0]) == 2


def test_failed_approval_rolls_back_and_retry_adds_once(flow):
    start_service(flow)
    baseline = state(flow)
    requested = submit(flow, 2, "two")
    with flow.sessions.begin() as db:
        db.get(Project, flow.project_id).publication_status = "inactive"
    response = approve(flow, requested)
    assert response.status_code == 409, response.text
    assert state(flow) == baseline
    with flow.sessions.begin() as db:
        assert db.get(SelectionChangeRequest, change_id(flow, requested)).state == "awaiting_staff_confirmation"
        assert db.query(ServiceLine).filter_by(selection_session_id=flow.session_id).count() == 1
        db.get(Project, flow.project_id).publication_status = "published"
    response = approve(flow, requested)
    assert response.status_code == 200, response.text
    assert approve(flow, requested).json() == response.json()
    assert sum(item["quantity"] for item in state(flow)[0]) == 2


@pytest.mark.parametrize("actor", ["other_headers", "employee_headers", "anonymous"])
def test_addition_approval_keeps_store_and_staff_permission_boundaries(flow, actor):
    start_service(flow)
    baseline = state(flow)
    requested = submit(flow, 2, "two")
    response = approve(flow, requested, {} if actor == "anonymous" else getattr(flow, actor))
    assert response.status_code in {401, 403, 404}, response.text
    assert state(flow) == baseline


def test_different_configuration_is_added_without_replacing_confirmed_service(flow):
    start_service(flow)
    baseline = state(flow)
    requested = submit(flow, 1, "different", preferences=["different preference"])
    assert state(flow) == baseline
    assert approve(flow, requested).status_code == 200
    assert sum(item["quantity"] for item in state(flow)[0]) == 2
    assert state(flow)[0][0] == baseline[0][0]
