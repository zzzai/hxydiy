"""Resolve server-owned catalog choices into normalized selection service units."""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
)


class CatalogSelectionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ResolvedCatalogSelection:
    catalog_version_id: int
    preference_snapshots: list[dict]
    linked_items: list[dict]
    dedicated_items: list[dict]


def _fail(code: str, message: str) -> None:
    raise CatalogSelectionError(code, message)


def require_project_catalog_version(
    db: Session,
    store_id: int,
    project_id: int,
    catalog_version_id: int,
) -> ProjectCatalogVersion:
    project = db.get(Project, project_id)
    version = db.get(ProjectCatalogVersion, catalog_version_id)
    if project is None or project.store_id != store_id:
        _fail("CATALOG_PROJECT_UNAVAILABLE", "目录所属项目在当前门店不可用")
    if version is None or version.project_id != project_id:
        _fail("CATALOG_VERSION_PROJECT_MISMATCH", "目录版本不属于所选项目")
    if version.status not in {"published", "superseded"}:
        _fail("CATALOG_VERSION_UNPUBLISHED", "目录版本尚未发布")
    return version


def require_active_choices(
    db: Session,
    version_id: int,
    choice_ids: list[int],
) -> list[ProjectOptionChoice]:
    if not choice_ids:
        return []
    groups = list(db.scalars(select(ProjectOptionGroup).where(
        ProjectOptionGroup.catalog_version_id == version_id,
    )))
    group_ids = {group.id for group in groups}
    selected: list[ProjectOptionChoice] = []
    for choice_id in choice_ids:
        choice = db.get(ProjectOptionChoice, choice_id)
        if choice is None or choice.option_group_id not in group_ids:
            _fail("OPTION_CHOICE_CATALOG_MISMATCH", "选择项不属于指定目录版本")
        if choice.status != "active":
            _fail("OPTION_CHOICE_INACTIVE", "选择项当前不可用")
        selected.append(choice)
    return selected


def validate_group_selection_counts(
    db: Session,
    version_id: int,
    selected_ids: set[int],
) -> None:
    groups = list(db.scalars(
        select(ProjectOptionGroup)
        .where(ProjectOptionGroup.catalog_version_id == version_id)
        .order_by(ProjectOptionGroup.display_order, ProjectOptionGroup.id)
    ))
    for group in groups:
        choice_ids = set(db.scalars(select(ProjectOptionChoice.id).where(
            ProjectOptionChoice.option_group_id == group.id,
        )))
        count = len(selected_ids & choice_ids)
        if group.required and count == 0:
            _fail("OPTION_GROUP_REQUIRED", f"选项组“{group.name}”必须选择")
        if count < group.min_select:
            _fail("OPTION_GROUP_MIN_SELECT", f"选项组“{group.name}”未达到最少选择数")
        if count > group.max_select:
            _fail("OPTION_GROUP_MAX_SELECT", f"选项组“{group.name}”超过最多选择数")


def _choice_snapshot(
    group: ProjectOptionGroup,
    choice: ProjectOptionChoice,
) -> dict:
    return {
        "option_choice_id": choice.id,
        "option_group_id": group.id,
        "group_code": group.code,
        "group_name": group.name,
        "code": choice.code,
        "name": choice.name,
        "choice_type": choice.choice_type,
        "charge_mode": choice.charge_mode,
        "linked_project_id": choice.linked_project_id,
        "coupon_eligible": choice.coupon_eligible,
        "annual_gift_eligible": choice.annual_gift_eligible,
        "qualifies_for_foot_bath_bundle": choice.qualifies_for_foot_bath_bundle,
    }


def _linked_project_item(
    project: Project,
    choice_snapshot: dict,
) -> dict:
    return {
        "project_id": project.id,
        "item_kind": "catalog_linked_project",
        "name": project.name,
        "category": project.category,
        "code": project.code,
        "quantity": 1,
        "addon_ids": [],
        "diy_preferences": [],
        "item_type": "service",
        "chargeable": True,
        "source_option_choice_ids": [choice_snapshot["option_choice_id"]],
        "choice_snapshot": choice_snapshot,
        "qualifies_for_foot_bath_bundle": choice_snapshot["qualifies_for_foot_bath_bundle"],
        "catalog_reference_only": project.category == "local-strength",
    }


def _dedicated_item(choice_snapshot: dict) -> dict:
    return {
        "project_id": None,
        "option_choice_id": choice_snapshot["option_choice_id"],
        "item_kind": "dedicated_option",
        "name": choice_snapshot["name"],
        "category": "catalog-option",
        "code": choice_snapshot["code"],
        "quantity": 1,
        "addon_ids": [],
        "diy_preferences": [],
        "item_type": "service",
        "chargeable": True,
        "choice_snapshot": choice_snapshot,
        "qualifies_for_foot_bath_bundle": choice_snapshot["qualifies_for_foot_bath_bundle"],
    }


def split_choice_snapshots(
    db: Session,
    version: ProjectCatalogVersion,
    selected: list[ProjectOptionChoice],
) -> ResolvedCatalogSelection:
    parent = db.get(Project, version.project_id)
    preference_snapshots: list[dict] = []
    linked_items: list[dict] = []
    dedicated_items: list[dict] = []
    for choice in selected:
        group = db.get(ProjectOptionGroup, choice.option_group_id)
        snapshot = _choice_snapshot(group, choice)
        if choice.choice_type == "preference":
            preference_snapshots.append(snapshot)
            continue
        if choice.choice_type == "dedicated_charge":
            dedicated_items.append(_dedicated_item(snapshot))
            continue
        if choice.choice_type != "linked_project" or choice.linked_project_id is None:
            _fail("OPTION_CHOICE_INVALID", "目录选择项配置无效")
        linked = db.get(Project, choice.linked_project_id)
        if linked is None:
            _fail("LINKED_PROJECT_UNPUBLISHED", "引用项目不存在或未发布")
        if parent is None or linked.store_id != parent.store_id:
            _fail("LINKED_PROJECT_CROSS_STORE", "引用项目不属于当前门店")
        if linked.publication_status != "published":
            _fail("LINKED_PROJECT_UNPUBLISHED", "引用项目尚未发布")
        linked_items.append(_linked_project_item(linked, snapshot))
    return ResolvedCatalogSelection(
        catalog_version_id=version.id,
        preference_snapshots=preference_snapshots,
        linked_items=linked_items,
        dedicated_items=dedicated_items,
    )


def resolve_catalog_selection(
    db: Session,
    *,
    store_id: int,
    project_id: int,
    catalog_version_id: int,
    choice_ids: list[int],
) -> ResolvedCatalogSelection:
    version = require_project_catalog_version(
        db,
        store_id,
        project_id,
        catalog_version_id,
    )
    selected = require_active_choices(db, version.id, choice_ids)
    validate_group_selection_counts(db, version.id, {choice.id for choice in selected})
    return split_choice_snapshots(db, version, selected)


def _normalized_part(item: dict) -> str | None:
    preferences = item.get("diy_preferences") or []
    if not preferences:
        return None
    value = unicodedata.normalize("NFKC", str(preferences[0]))
    normalized = "".join(value.split()).casefold()
    return normalized or None


def _service_unit_key(item: dict) -> tuple[str, str | None] | None:
    project_id = item.get("project_id")
    if not isinstance(project_id, int):
        return None
    return str(project_id), _normalized_part(item)


def _merge_sources(target: dict, source: dict) -> None:
    combined = [
        *target.get("source_option_choice_ids", []),
        *source.get("source_option_choice_ids", []),
    ]
    target["source_option_choice_ids"] = list(dict.fromkeys(combined))
    if source.get("qualifies_for_foot_bath_bundle"):
        target["qualifies_for_foot_bath_bundle"] = True


def merge_linked_service_units(
    base_items: list[dict],
    linked_items: list[dict],
) -> list[dict]:
    """Merge catalog references without adding quantities from two entry paths."""
    linked_project_ids = {
        item["project_id"] for item in linked_items if isinstance(item.get("project_id"), int)
    }
    merged: list[dict] = []
    by_key: dict[tuple[str, str | None], dict] = {}
    for original in base_items:
        item = dict(original)
        item["diy_preferences"] = [
            str(value).strip()
            for value in item.get("diy_preferences", [])
            if str(value).strip()
        ]
        key = _service_unit_key(item)
        if key is not None and item.get("project_id") in linked_project_ids and key in by_key:
            continue
        merged.append(item)
        if key is not None:
            by_key.setdefault(key, item)

    for linked in linked_items:
        project_id = linked.get("project_id")
        if linked.get("catalog_reference_only"):
            for key, target in by_key.items():
                if key[0] == str(project_id):
                    _merge_sources(target, linked)
            continue
        key = _service_unit_key(linked)
        target = by_key.get(key) if key is not None else None
        if target is not None:
            _merge_sources(target, linked)
            continue
        item = dict(linked)
        merged.append(item)
        if key is not None:
            by_key[key] = item
    return merged
