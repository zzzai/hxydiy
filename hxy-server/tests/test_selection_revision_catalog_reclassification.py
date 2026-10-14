"""Catalog provenance changes must not duplicate existing physical units."""

from copy import deepcopy

import pytest
from sqlalchemy import select

from app.api.admin import create_staff_token
from app.api.selections import _added_items
from app.db.session import get_db
from app.main import app
from app.models import PositionOccupancy, Room, SelectionChangeRequest, SelectionSession, ServiceLine, Staff
from catalog_selection_fixtures import scenario  # noqa: F401


@pytest.mark.parametrize("linked_first", [True, False])
def test_source_reclassification_subtracts_the_same_physical_service(linked_first):
    linked = {"project_id": 4, "item_type": "service", "quantity": 1,
              "item_kind": "catalog_linked_project", "source_project_id": 1,
              "source_catalog_version_id": 7, "addon_ids": [], "diy_preferences": []}
    independent = {"project_id": 4, "item_type": "service", "quantity": 1,
                   "item_kind": "project", "addon_ids": [], "diy_preferences": []}
    previous, current = (linked, independent) if linked_first else (independent, linked)
    target = {**current, "quantity": 2}
    assert _added_items([previous], [target]) == [{**target, "quantity": 1}]
    assert previous["quantity"] == 1 and target["quantity"] == 2


@pytest.mark.parametrize("configuration", [{"addon_ids": [3]}, {"diy_preferences": ["肩颈"]}])
def test_provenance_alias_does_not_merge_different_service_configuration(configuration):
    previous = {"project_id": 4, "item_type": "service", "quantity": 1,
                "source_project_id": 1, "source_catalog_version_id": 7,
                "addon_ids": [], "diy_preferences": []}
    current = {"project_id": 4, "item_type": "service", "quantity": 2,
               "addon_ids": [], "diy_preferences": [], **configuration}
    assert _added_items([previous], [current]) == [current]


def _sessions():
    return app.dependency_overrides[get_db].__closure__[0].cell_contents


def _submit(scenario, items, key):
    response = scenario.client.post(
        f"/api/v1/selection-sessions/{scenario.session_id}/revisions",
        headers={**scenario.customer_headers, "Idempotency-Key": key}, json={"items": items})
    assert response.status_code == 200, response.text
    return response.json()


def _state(scenario):
    with _sessions()() as db:
        session = db.get(SelectionSession, scenario.session_id)
        return deepcopy(session.items), deepcopy(session.pricing_snapshot)


def _approve(scenario, revision, headers):
    with _sessions()() as db:
        request_id = db.scalar(select(SelectionChangeRequest.id).where(
            SelectionChangeRequest.selection_revision_id == revision["id"]))
    response = scenario.client.post(
        f"/api/v1/admin/v2/selection-change-requests/{request_id}/approve", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("in_service", [False, True])
def test_http_linked_b_then_independent_b_target_two_adds_one(scenario, in_service):
    parent = {"project_id": scenario.qiqing_id, "quantity": 1,
              "catalog_version_id": scenario.qiqing_version_id,
              "option_choice_ids": [scenario.qiqing_linked_choice_id]}
    initial = _submit(scenario, [parent], "initial-linked")
    baseline_b = next(item for item in initial["snapshot"]["items"]
                      if item["project_id"] == scenario.referenced_small_project_id)
    assert baseline_b["quantity"] == 1
    assert baseline_b["source_project_id"] == scenario.qiqing_id
    headers = None
    if in_service:
        with _sessions().begin() as db:
            staff = Staff(username="reclassification-manager", name="Fixture manager", role="manager",
                          store_id=scenario.store_id, password_hash="unused-fixture", status="active")
            room = Room(store_id=scenario.store_id, code="RECLASSIFICATION", name="Fixture seat", room_type="sofa")
            db.add_all([staff, room])
            db.flush()
            db.add(PositionOccupancy(store_id=scenario.store_id, room_id=room.id, active_room_id=room.id,
                                     selection_session_id=scenario.session_id, active_session_id=scenario.session_id,
                                     status="waiting_service", source="tablet"))
            headers = {"Authorization": "Bearer " + create_staff_token(staff.id, "manager")}
        confirmed = scenario.client.post(
            f"/api/v1/admin/v2/selection-sessions/{scenario.session_id}/confirm", headers=headers)
        assert confirmed.status_code == 200, confirmed.text
        with _sessions().begin() as db:
            db.scalar(select(PositionOccupancy).where(
                PositionOccupancy.selection_session_id == scenario.session_id)).status = "in_service"

    parent_growth = _submit(scenario, [{**parent, "quantity": 2}], "parent-two")
    assert [(item["project_id"], item["quantity"]) for item in parent_growth["snapshot"]["added_items"]] == [
        (scenario.qiqing_id, 1)]
    if in_service:
        _approve(scenario, parent_growth, headers)
    baseline = _state(scenario)
    baseline_snapshots = None
    if in_service:
        with _sessions()() as db:
            baseline_snapshots = {line.id: deepcopy(line.snapshot) for line in db.scalars(select(ServiceLine).where(
                ServiceLine.selection_session_id == scenario.session_id))}

    target = [{**parent, "quantity": 2},
              {"project_id": scenario.referenced_small_project_id, "quantity": 2}]
    addition = _submit(scenario, target, "independent-b-two")
    target_b = next(item for item in addition["snapshot"]["items"]
                    if item["project_id"] == scenario.referenced_small_project_id)
    assert target_b["quantity"] == 2
    assert target_b["item_kind"] == "project"
    assert "source_project_id" not in target_b
    assert target_b["source_option_choice_ids"] == [scenario.qiqing_linked_choice_id]
    assert [(item["project_id"], item["quantity"]) for item in addition["snapshot"]["added_items"]] == [
        (scenario.referenced_small_project_id, 1)]
    if in_service:
        assert _state(scenario) == baseline
        approved = _approve(scenario, addition, headers)
        assert sum(line["snapshot"]["quantity"] for line in approved["service_lines"]) == 1
        assert _approve(scenario, addition, headers) == approved
        with _sessions()() as db:
            for line_id, snapshot in baseline_snapshots.items():
                assert db.get(ServiceLine, line_id).snapshot == snapshot
    items, pricing = _state(scenario)
    assert sum(item["quantity"] for item in items if item["project_id"] == scenario.referenced_small_project_id) == 2
    assert pricing["payable_total_cents"] == 4000
