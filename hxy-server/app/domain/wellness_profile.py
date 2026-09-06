from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProfileProjectionSpec:
    profile_code: str
    source_path: tuple[str, ...]
    valid_days: int
    sensitivity_level: str = "normal"
    multi_value: bool = False


@dataclass(frozen=True)
class ProjectedProfileValue:
    profile_code: str
    value: str
    valid_days: int
    sensitivity_level: str
    multi_value: bool


V3_PROFILE_PROJECTION_SPECS = (
    ProfileProjectionSpec("focus_area", ("customer_reported", "focus_areas"), 180, multi_value=True),
    ProfileProjectionSpec("avoid_area", ("customer_reported", "avoid_areas"), 180, multi_value=True),
    ProfileProjectionSpec("force_preference", ("customer_reported", "force_preference"), 180),
    ProfileProjectionSpec("temperature_preference", ("customer_reported", "temperature_preference"), 180),
    ProfileProjectionSpec("age_band", ("customer_reported", "personal_context", "age_band"), 365),
    ProfileProjectionSpec("body_build", ("customer_reported", "personal_context", "build"), 365),
    ProfileProjectionSpec("height_band", ("customer_reported", "personal_context", "height_band"), 365),
    ProfileProjectionSpec("work_context", ("customer_reported", "work_lifestyle", "occupation_contexts"), 180, multi_value=True),
    ProfileProjectionSpec("sleep_feeling", ("customer_reported", "work_lifestyle", "sleep_quality"), 30),
    ProfileProjectionSpec("decision_focus", ("customer_reported", "communication_consumption", "decision_priorities"), 180, multi_value=True),
)


_MISSING = object()


def _read_path(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return _MISSING
        value = value[key]
    return value


def extract_confirmed_v3_profile(profile: dict[str, Any]) -> dict[str, list[ProjectedProfileValue]]:
    if profile.get("schema_version") != 3 or profile.get("taxonomy_version") != "service_reference_v2":
        return {}

    result: dict[str, list[ProjectedProfileValue]] = {}
    for spec in V3_PROFILE_PROJECTION_SPECS:
        raw = _read_path(profile, spec.source_path)
        if raw is _MISSING:
            continue
        source_values = raw if spec.multi_value and isinstance(raw, list) else [raw]
        values = [
            ProjectedProfileValue(
                profile_code=spec.profile_code,
                value=value,
                valid_days=spec.valid_days,
                sensitivity_level=spec.sensitivity_level,
                multi_value=spec.multi_value,
            )
            for value in source_values
            if isinstance(value, str) and value
        ]
        result[spec.profile_code] = values
    return result
