from datetime import UTC, datetime
import inspect

import pytest

from app.db.session import get_db
from app.domain.catalog_options import _snapshot_hash
from app.main import app
from app.models import (
    OptionChoicePrice,
    PriceBook,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    Store,
)
from catalog_selection_fixtures import CatalogSelectionScenario, scenario


def _session_local():
    override = app.dependency_overrides[get_db]
    return inspect.getclosurevars(override).nonlocals["session_local"]


@pytest.fixture
def expanded_scenario(scenario: CatalogSelectionScenario) -> CatalogSelectionScenario:
    with _session_local()() as db:
        qiqing_group = db.get(ProjectOptionGroup, scenario.qiqing_small_group_id)

        dedicated = ProjectOptionChoice(
            option_group_id=qiqing_group.id,
            code="herbal-upgrade",
            name="草本升级",
            choice_type="dedicated_charge",
            charge_mode="custom_price",
            display_order=3,
        )
        inactive = ProjectOptionChoice(
            option_group_id=qiqing_group.id,
            code="inactive-choice",
            name="已停用选项",
            choice_type="preference",
            charge_mode="free",
            status="inactive",
            display_order=4,
        )
        db.add_all([dedicated, inactive])
        db.flush()
        db.add_all([
            OptionChoicePrice(
                option_choice_id=dedicated.id,
                price_type="store",
                amount_cents=600,
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            OptionChoicePrice(
                option_choice_id=dedicated.id,
                price_type="group",
                amount_cents=500,
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            OptionChoicePrice(
                option_choice_id=dedicated.id,
                price_type="member",
                amount_cents=400,
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ])

        other_store = Store(store_code="catalog-selection-other", name="其他门店", address="测试地址")
        db.add(other_store)
        db.flush()
        cross_store_project = Project(
            store_id=other_store.id,
            code="hxy-cross-store-small",
            category="small",
            name="跨门店小项",
            publication_status="published",
        )
        unpublished_project = Project(
            store_id=scenario.store_id,
            code="hxy-unpublished-small",
            category="small",
            name="未发布小项",
            publication_status="draft",
        )
        db.add_all([cross_store_project, unpublished_project])
        db.flush()
        db.add_all([
            PriceBook(project_id=cross_store_project.id, price_type="store", amount_cents=1000),
            PriceBook(project_id=unpublished_project.id, price_type="store", amount_cents=1000),
        ])
        cross_store_choice = ProjectOptionChoice(
            option_group_id=qiqing_group.id,
            code="cross-store",
            name="跨门店引用",
            choice_type="linked_project",
            linked_project_id=cross_store_project.id,
            charge_mode="inherit_linked_price",
            display_order=5,
        )
        unpublished_choice = ProjectOptionChoice(
            option_group_id=qiqing_group.id,
            code="unpublished",
            name="未发布引用",
            choice_type="linked_project",
            linked_project_id=unpublished_project.id,
            charge_mode="inherit_linked_price",
            display_order=6,
        )
        db.add_all([cross_store_choice, unpublished_choice])

        xiaoqi_version = ProjectCatalogVersion(
            project_id=scenario.xiaoqi_id,
            version=1,
            status="published",
        )
        db.add(xiaoqi_version)
        db.flush()
        db.get(Project, scenario.xiaoqi_id).current_published_version_id = xiaoqi_version.id
        xiaoqi_group = ProjectOptionGroup(
            catalog_version_id=xiaoqi_version.id,
            code="small",
            name="小项",
            selection_mode="multiple",
            max_select=2,
        )
        db.add(xiaoqi_group)
        db.flush()
        xiaoqi_cupping = ProjectOptionChoice(
            option_group_id=xiaoqi_group.id,
            code="cupping",
            name="走竹罐",
            choice_type="linked_project",
            linked_project_id=scenario.referenced_small_project_id,
            charge_mode="inherit_linked_price",
        )
        db.add(xiaoqi_cupping)

        xiangxiang_version = ProjectCatalogVersion(
            project_id=scenario.xiangxiang_id,
            version=1,
            status="published",
        )
        db.add(xiangxiang_version)
        db.flush()
        db.get(Project, scenario.xiangxiang_id).current_published_version_id = xiangxiang_version.id
        local_group = ProjectOptionGroup(
            catalog_version_id=xiangxiang_version.id,
            code="local",
            name="局部加强",
            selection_mode="multiple",
            max_select=1,
        )
        db.add(local_group)
        db.flush()
        local_choice = ProjectOptionChoice(
            option_group_id=local_group.id,
            code="local-strength",
            name="局部加强",
            choice_type="linked_project",
            linked_project_id=scenario.local_project_id,
            charge_mode="inherit_linked_price",
            qualifies_for_foot_bath_bundle=True,
        )
        db.add(local_choice)
        db.flush()

        qiqing_version = db.get(ProjectCatalogVersion, scenario.qiqing_version_id)
        qiqing_version.snapshot_hash = _snapshot_hash(db, qiqing_version.id)
        xiaoqi_version.snapshot_hash = _snapshot_hash(db, xiaoqi_version.id)
        xiangxiang_version.snapshot_hash = _snapshot_hash(db, xiangxiang_version.id)
        db.commit()

        scenario.dedicated_choice_id = dedicated.id
        scenario.inactive_choice_id = inactive.id
        scenario.cross_store_choice_id = cross_store_choice.id
        scenario.unpublished_choice_id = unpublished_choice.id
        scenario.xiaoqi_version_id = xiaoqi_version.id
        scenario.xiaoqi_cupping_choice_id = xiaoqi_cupping.id
        scenario.cupping_project_id = scenario.referenced_small_project_id
        scenario.xiangxiang_version_id = xiangxiang_version.id
        scenario.xiangxiang_local_choice_id = local_choice.id
    return scenario


def _post_revision(scenario: CatalogSelectionScenario, items: list[dict]):
    return scenario.client.post(
        f"/api/v1/selection-sessions/{scenario.session_id}/revisions",
        headers=scenario.customer_headers,
        json={"items": items},
    )


def _items(response) -> list[dict]:
    return response.json()["snapshot"]["items"]


def _assert_error_code(response, code: str) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == code


def test_public_catalog_returns_stable_group_and_choice_ids(scenario: CatalogSelectionScenario):
    response = scenario.client.get(f"/api/v1/projects?store_id={scenario.store_id}")

    assert response.status_code == 200
    project = next(item for item in response.json()["items"] if item["id"] == scenario.qiqing_id)
    assert project["option_groups"][0]["id"] == scenario.qiqing_small_group_id
    assert project["option_groups"][0]["choices"][0]["id"] == scenario.qiqing_cupping_choice_id


def test_selection_rejects_duplicate_option_choice_ids(scenario: CatalogSelectionScenario):
    response = _post_revision(scenario, [{
        "project_id": scenario.qiqing_id,
        "catalog_version_id": scenario.qiqing_version_id,
        "option_choice_ids": [scenario.qiqing_cupping_choice_id, scenario.qiqing_cupping_choice_id],
    }])

    assert response.status_code == 422


def test_selection_rejects_catalog_version_from_another_project(expanded_scenario: CatalogSelectionScenario):
    response = _post_revision(expanded_scenario, [{
        "project_id": expanded_scenario.qiqing_id,
        "catalog_version_id": expanded_scenario.xiaoqi_version_id,
        "option_choice_ids": [expanded_scenario.xiaoqi_cupping_choice_id],
    }])

    _assert_error_code(response, "CATALOG_VERSION_PROJECT_MISMATCH")


def test_selection_rejects_choice_from_another_catalog_version(expanded_scenario: CatalogSelectionScenario):
    response = _post_revision(expanded_scenario, [{
        "project_id": expanded_scenario.qiqing_id,
        "catalog_version_id": expanded_scenario.qiqing_version_id,
        "option_choice_ids": [expanded_scenario.xiaoqi_cupping_choice_id],
    }])

    _assert_error_code(response, "OPTION_CHOICE_CATALOG_MISMATCH")


def test_selection_requires_catalog_version_for_project_with_published_catalog(
    expanded_scenario: CatalogSelectionScenario,
):
    response = _post_revision(expanded_scenario, [{
        "project_id": expanded_scenario.qiqing_id,
    }])

    _assert_error_code(response, "CATALOG_VERSION_REQUIRED")


def test_selection_rejects_missing_required_group(expanded_scenario: CatalogSelectionScenario):
    with _session_local()() as db:
        group = db.get(ProjectOptionGroup, expanded_scenario.qiqing_small_group_id)
        group.required = True
        group.min_select = 0
        db.commit()

    response = _post_revision(expanded_scenario, [{
        "project_id": expanded_scenario.qiqing_id,
        "catalog_version_id": expanded_scenario.qiqing_version_id,
        "option_choice_ids": [],
    }])

    _assert_error_code(response, "OPTION_GROUP_REQUIRED")


def test_selection_rejects_group_below_min_select(expanded_scenario: CatalogSelectionScenario):
    with _session_local()() as db:
        group = db.get(ProjectOptionGroup, expanded_scenario.qiqing_small_group_id)
        group.min_select = 2
        db.commit()

    response = _post_revision(expanded_scenario, [{
        "project_id": expanded_scenario.qiqing_id,
        "catalog_version_id": expanded_scenario.qiqing_version_id,
        "option_choice_ids": [expanded_scenario.qiqing_cupping_choice_id],
    }])

    _assert_error_code(response, "OPTION_GROUP_MIN_SELECT")


def test_selection_rejects_group_above_max_select(expanded_scenario: CatalogSelectionScenario):
    with _session_local()() as db:
        group = db.get(ProjectOptionGroup, expanded_scenario.qiqing_small_group_id)
        group.max_select = 1
        db.commit()

    response = _post_revision(expanded_scenario, [{
        "project_id": expanded_scenario.qiqing_id,
        "catalog_version_id": expanded_scenario.qiqing_version_id,
        "option_choice_ids": [
            expanded_scenario.qiqing_cupping_choice_id,
            expanded_scenario.qiqing_linked_choice_id,
        ],
    }])

    _assert_error_code(response, "OPTION_GROUP_MAX_SELECT")


@pytest.mark.parametrize(
    ("choice_attribute", "error_code"),
    [
        ("inactive_choice_id", "OPTION_CHOICE_INACTIVE"),
        ("cross_store_choice_id", "LINKED_PROJECT_CROSS_STORE"),
        ("unpublished_choice_id", "LINKED_PROJECT_UNPUBLISHED"),
    ],
)
def test_selection_rejects_unavailable_choices(
    expanded_scenario: CatalogSelectionScenario,
    choice_attribute: str,
    error_code: str,
):
    response = _post_revision(expanded_scenario, [{
        "project_id": expanded_scenario.qiqing_id,
        "catalog_version_id": expanded_scenario.qiqing_version_id,
        "option_choice_ids": [getattr(expanded_scenario, choice_attribute)],
    }])

    _assert_error_code(response, error_code)


def test_selection_keeps_free_preference_as_snapshot_without_charge_line(expanded_scenario: CatalogSelectionScenario):
    response = _post_revision(expanded_scenario, [{
        "project_id": expanded_scenario.qiqing_id,
        "catalog_version_id": expanded_scenario.qiqing_version_id,
        "option_choice_ids": [expanded_scenario.qiqing_cupping_choice_id],
    }])

    assert response.status_code == 200, response.text
    items = _items(response)
    assert [item["project_id"] for item in items] == [expanded_scenario.qiqing_id]
    preference = items[0]["catalog_selection"]["preference_snapshots"][0]
    assert preference["option_choice_id"] == expanded_scenario.qiqing_cupping_choice_id
    assert preference["name"] == "走竹罐"
    assert preference["choice_type"] == "preference"


def test_selection_keeps_dedicated_charge_choice_id_on_expanded_line(expanded_scenario: CatalogSelectionScenario):
    response = _post_revision(expanded_scenario, [{
        "project_id": expanded_scenario.qiqing_id,
        "catalog_version_id": expanded_scenario.qiqing_version_id,
        "option_choice_ids": [expanded_scenario.dedicated_choice_id],
        "chargeable": False,
    }])

    assert response.status_code == 200, response.text
    items = _items(response)
    dedicated = next(item for item in items if item["item_kind"] == "dedicated_option")
    assert dedicated["project_id"] is None
    assert dedicated["option_choice_id"] == expanded_scenario.dedicated_choice_id
    assert dedicated["name"] == "草本升级"
    pricing_line = next(
        line for line in response.json()["snapshot"]["pricing"]["lines"]
        if line.get("option_choice_id") == expanded_scenario.dedicated_choice_id
    )
    assert pricing_line["unit_store_price_cents"] == 600
    assert pricing_line["unit_group_price_cents"] == 500
    assert pricing_line["unit_member_price_cents"] == 400
    assert pricing_line["resolved_charge"]["source_project_id"] == expanded_scenario.qiqing_id
    assert (
        pricing_line["resolved_charge"]["source_catalog_version_id"]
        == expanded_scenario.qiqing_version_id
    )
    assert response.json()["snapshot"]["pricing"]["store_subtotal_cents"] == 1600


def test_selection_expands_linked_project_once_across_two_parent_entries(expanded_scenario: CatalogSelectionScenario):
    response = _post_revision(expanded_scenario, [
        {
            "project_id": expanded_scenario.qiqing_id,
            "catalog_version_id": expanded_scenario.qiqing_version_id,
            "option_choice_ids": [expanded_scenario.qiqing_linked_choice_id],
        },
        {
            "project_id": expanded_scenario.xiaoqi_id,
            "catalog_version_id": expanded_scenario.xiaoqi_version_id,
            "option_choice_ids": [expanded_scenario.xiaoqi_cupping_choice_id],
        },
    ])

    assert response.status_code == 200, response.text
    items = _items(response)
    assert sum(item["project_id"] == expanded_scenario.cupping_project_id for item in items) == 1
    pricing = response.json()["snapshot"]["pricing"]
    assert sum(
        line["project_id"] == expanded_scenario.cupping_project_id
        for line in pricing["lines"]
    ) == 1
    assert pricing["store_subtotal_cents"] == 3000


def test_explicit_linked_project_quantity_wins_without_adding_catalog_unit(expanded_scenario: CatalogSelectionScenario):
    response = _post_revision(expanded_scenario, [
        {
            "project_id": expanded_scenario.qiqing_id,
            "catalog_version_id": expanded_scenario.qiqing_version_id,
            "option_choice_ids": [expanded_scenario.qiqing_linked_choice_id],
        },
        {"project_id": expanded_scenario.referenced_small_project_id, "quantity": 3},
    ])

    assert response.status_code == 200, response.text
    linked = [
        item for item in _items(response)
        if item["project_id"] == expanded_scenario.referenced_small_project_id
    ]
    assert len(linked) == 1
    assert linked[0]["quantity"] == 3
    assert linked[0]["source_option_choice_ids"] == [expanded_scenario.qiqing_linked_choice_id]


def test_local_reference_does_not_create_a_partless_charge_line(expanded_scenario: CatalogSelectionScenario):
    response = _post_revision(expanded_scenario, [{
        "project_id": expanded_scenario.xiangxiang_id,
        "catalog_version_id": expanded_scenario.xiangxiang_version_id,
        "option_choice_ids": [expanded_scenario.xiangxiang_local_choice_id],
    }])

    assert response.status_code == 200, response.text
    items = _items(response)
    assert [item["project_id"] for item in items] == [expanded_scenario.xiangxiang_id]
    linked_snapshot = items[0]["catalog_selection"]["linked_snapshots"][0]
    assert linked_snapshot["option_choice_id"] == expanded_scenario.xiangxiang_local_choice_id
    assert linked_snapshot["qualifies_for_foot_bath_bundle"] is True


def test_local_reference_rejects_explicit_local_line_without_body_part(
    expanded_scenario: CatalogSelectionScenario,
):
    response = _post_revision(expanded_scenario, [
        {
            "project_id": expanded_scenario.xiangxiang_id,
            "catalog_version_id": expanded_scenario.xiangxiang_version_id,
            "option_choice_ids": [expanded_scenario.xiangxiang_local_choice_id],
        },
        {"project_id": expanded_scenario.local_project_id},
    ])

    _assert_error_code(response, "LOCAL_STRENGTH_BODY_PART_REQUIRED")


def test_explicit_local_project_requires_body_part_without_catalog_source(
    expanded_scenario: CatalogSelectionScenario,
):
    response = _post_revision(expanded_scenario, [{
        "project_id": expanded_scenario.local_project_id,
    }])

    _assert_error_code(response, "LOCAL_STRENGTH_BODY_PART_REQUIRED")


def test_same_local_project_keeps_two_distinct_body_parts(expanded_scenario: CatalogSelectionScenario):
    response = _post_revision(expanded_scenario, [
        {
            "project_id": expanded_scenario.xiangxiang_id,
            "catalog_version_id": expanded_scenario.xiangxiang_version_id,
            "option_choice_ids": [expanded_scenario.xiangxiang_local_choice_id],
        },
        {"project_id": expanded_scenario.local_project_id, "diy_preferences": ["肩颈"]},
        {"project_id": expanded_scenario.local_project_id, "diy_preferences": ["腿部"]},
    ])

    assert response.status_code == 200, response.text
    local_items = [
        item for item in _items(response)
        if item["project_id"] == expanded_scenario.local_project_id
    ]
    assert [item["diy_preferences"] for item in local_items] == [["肩颈"], ["腿部"]]
    assert all(
        item["source_option_choice_ids"] == [expanded_scenario.xiangxiang_local_choice_id]
        for item in local_items
    )


def test_same_local_body_part_is_kept_once_across_explicit_entries(expanded_scenario: CatalogSelectionScenario):
    response = _post_revision(expanded_scenario, [
        {
            "project_id": expanded_scenario.xiangxiang_id,
            "catalog_version_id": expanded_scenario.xiangxiang_version_id,
            "option_choice_ids": [expanded_scenario.xiangxiang_local_choice_id],
        },
        {"project_id": expanded_scenario.local_project_id, "quantity": 2, "diy_preferences": [" 肩颈 "]},
        {"project_id": expanded_scenario.local_project_id, "quantity": 5, "diy_preferences": ["肩颈"]},
    ])

    assert response.status_code == 200, response.text
    local_items = [
        item for item in _items(response)
        if item["project_id"] == expanded_scenario.local_project_id
    ]
    assert len(local_items) == 1
    assert local_items[0]["quantity"] == 2
    assert local_items[0]["diy_preferences"] == ["肩颈"]
