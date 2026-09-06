from app.domain.wellness_profile import (
    V3_PROFILE_PROJECTION_SPECS,
    extract_confirmed_v3_profile,
)


def test_projection_specs_are_unique_and_exclude_sensitive_paths():
    codes = [item.profile_code for item in V3_PROFILE_PROJECTION_SPECS]

    assert len(codes) == len(set(codes))
    assert all("service_related_context" not in item.source_path for item in V3_PROFILE_PROJECTION_SPECS)
    assert all("technician_observed" not in item.source_path for item in V3_PROFILE_PROJECTION_SPECS)


def test_confirmed_v3_profile_projects_only_safe_customer_reported_values():
    groups = extract_confirmed_v3_profile({
        "schema_version": 3,
        "taxonomy_version": "service_reference_v2",
        "customer_reported": {
            "force_preference": "medium",
            "focus_areas": ["neck_shoulder", "legs"],
            "personal_context": {"age_band": "35_44"},
            "service_related_context": {
                "contexts": ["medication_mentioned"],
                "quote": "顾客自述正在用药",
            },
        },
        "technician_observed": {"service_feedback": "suitable"},
    })

    values = [item for group in groups.values() for item in group]

    assert {(item.profile_code, item.value) for item in values} == {
        ("force_preference", "medium"),
        ("focus_area", "neck_shoulder"),
        ("focus_area", "legs"),
        ("age_band", "35_44"),
    }
