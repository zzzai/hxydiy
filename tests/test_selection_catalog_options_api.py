from catalog_selection_fixtures import CatalogSelectionScenario, scenario


def test_public_catalog_returns_stable_group_and_choice_ids(scenario: CatalogSelectionScenario):
    response = scenario.client.get(f"/api/v1/projects?store_id={scenario.store_id}")

    assert response.status_code == 200
    project = next(item for item in response.json()["items"] if item["id"] == scenario.qiqing_id)
    assert project["option_groups"][0]["id"] == scenario.qiqing_small_group_id
    assert project["option_groups"][0]["choices"][0]["id"] == scenario.qiqing_cupping_choice_id


def test_selection_rejects_duplicate_option_choice_ids(scenario: CatalogSelectionScenario):
    response = scenario.client.post(
        f"/api/v1/selection-sessions/{scenario.session_id}/revisions",
        headers=scenario.customer_headers,
        json={"items": [{
            "project_id": scenario.qiqing_id,
            "catalog_version_id": scenario.qiqing_version_id,
            "option_choice_ids": [scenario.qiqing_cupping_choice_id, scenario.qiqing_cupping_choice_id],
        }]},
    )

    assert response.status_code == 422
