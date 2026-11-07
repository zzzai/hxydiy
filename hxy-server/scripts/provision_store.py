"""Preview or apply a controlled clone of one store's operating configuration.

The clone copies the published menu (projects, prices, option catalogs, addons),
the home page, rooms/service positions, and reports which positions need a new
QR code. It never modifies the source store and never deletes data.

Preview is read-only. Apply requires the exact preview hash, an explicit staff
actor, and (on PostgreSQL) a verified custom-format backup reference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import or_, select, text

from app.db.session import SessionLocal
from app.domain.catalog_options import copy_catalog_version_graph, publish_catalog_version
from app.models import (
    Addon,
    AuditLog,
    PageContent,
    PriceBook,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    Room,
    ServicePositionQr,
    Staff,
    Store,
)

PRICE_TYPES = ("store", "group", "member")
PAGE_KEY = "diy-home"
MAX_CODE_LENGTH = 32


def fingerprint(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def plan_hash(plan: dict) -> str:
    """Hash the intended clone, ignoring whether target records already exist.

    Target existence changes after the first successful apply, so it must not
    change the preview identity. Conflicts and warnings stay in the hash.
    """

    normalized = json.loads(json.dumps(plan, ensure_ascii=False))
    normalized.pop("preview_hash", None)
    for key in ("projects", "addons", "rooms"):
        for item in normalized.get(key, []):
            item.pop("existing_target_id", None)
    if normalized.get("page"):
        normalized["page"].pop("existing_target_id", None)
    return fingerprint(normalized)


def _require_store(db, store_id: int) -> Store:
    store = db.get(Store, store_id)
    if store is None:
        raise ValueError(f"门店不存在: {store_id}")
    return store


def _current_prices(db, project_id: int) -> dict[str, int]:
    now = datetime.now(UTC)
    rows = list(db.scalars(
        select(PriceBook)
        .where(
            PriceBook.project_id == project_id,
            or_(PriceBook.effective_to.is_(None), PriceBook.effective_to > now),
        )
        .order_by(PriceBook.id)
    ))
    by_type: dict[str, list[PriceBook]] = {}
    for row in rows:
        by_type.setdefault(row.price_type, []).append(row)
    return by_type


def _price_amounts(by_type: dict[str, list[PriceBook]], conflicts: list[dict], code: str) -> dict[str, int]:
    amounts: dict[str, int] = {}
    for price_type, rows in by_type.items():
        if price_type not in PRICE_TYPES:
            continue
        if len(rows) != 1:
            conflicts.append({
                "kind": "duplicate_active_price",
                "code": code,
                "price_type": price_type,
                "ids": [row.id for row in rows],
            })
            continue
        amounts[price_type] = int(rows[0].amount_cents)
    return amounts


def _catalog_usage(db, version_id: int | None) -> dict | None:
    if version_id is None:
        return None
    version = db.get(ProjectCatalogVersion, version_id)
    if version is None or version.status != "published":
        return {"id": version_id, "status": getattr(version, "status", "missing")}
    group_ids = list(db.scalars(
        select(ProjectOptionGroup.id).where(ProjectOptionGroup.catalog_version_id == version.id)
    ))
    choice_count = 0
    if group_ids:
        choice_count = len(list(db.scalars(
            select(ProjectOptionChoice.id).where(ProjectOptionChoice.option_group_id.in_(group_ids))
        )))
    return {
        "id": version.id,
        "version": version.version,
        "status": version.status,
        "groups": len(group_ids),
        "choices": choice_count,
    }


def build_clone_plan(
    db,
    *,
    source_store_id: int,
    target_store_id: int,
    code_prefix: str,
) -> dict:
    """Build a deterministic, read-only clone plan."""

    source = _require_store(db, source_store_id)
    target = _require_store(db, target_store_id)
    if source.id == target.id:
        raise ValueError("源门店与目标门店不能相同")
    if target.status not in {"draft", "preparing", "trial_open"}:
        raise ValueError(f"目标门店状态为 {target.status}，只允许 draft/preparing/trial_open 复制")
    if not code_prefix or len(code_prefix) > 8 or any(not (char.isalnum() or char in "-_") for char in code_prefix):
        raise ValueError("code_prefix 必须是 1-8 位字母、数字、- 或 _")

    conflicts: list[dict] = []
    warnings: list[dict] = []

    source_projects = list(db.scalars(
        select(Project)
        .where(Project.store_id == source.id, Project.publication_status == "published")
        .order_by(Project.display_order, Project.id)
    ))
    if not source_projects:
        raise ValueError("源门店没有已发布项目")

    project_items: list[dict] = []
    source_project_ids = {project.id for project in source_projects}
    for project in source_projects:
        target_code = f"{code_prefix}{project.code}"
        if len(target_code) > MAX_CODE_LENGTH:
            conflicts.append({"kind": "target_code_too_long", "code": target_code, "source_code": project.code})
            continue
        existing = db.scalar(select(Project).where(
            Project.store_id == target.id, Project.code == target_code,
        ))
        other_store = db.scalar(select(Project).where(
            Project.code == target_code, Project.store_id != target.id,
        ))
        if other_store is not None:
            conflicts.append({
                "kind": "project_code_used_by_other_store",
                "code": target_code,
                "other_store_id": other_store.store_id,
            })
        prices = _price_amounts(_current_prices(db, project.id), conflicts, project.code)
        if "store" not in prices:
            conflicts.append({"kind": "missing_store_price", "code": project.code})
        version_usage = _catalog_usage(db, project.current_published_version_id)
        if version_usage and version_usage.get("status") != "published":
            conflicts.append({
                "kind": "source_catalog_not_published",
                "code": project.code,
                "catalog_version": version_usage,
            })
        project_items.append({
            "source_id": project.id,
            "source_code": project.code,
            "target_code": target_code,
            "name": project.name,
            "category": project.category,
            "category_mark": project.category_mark,
            "duration_min": project.duration_min,
            "summary": project.summary,
            "image_url": project.image_url,
            "tags": list(project.tags or []),
            "detail_modules": list(project.detail_modules or []),
            "diy_options": list(project.diy_options or []),
            "display_order": project.display_order,
            "price_label": project.price_label,
            "content_version": project.content_version,
            "independently_visible": bool(project.independently_visible),
            "prices": prices,
            "catalog_version": version_usage,
            "existing_target_id": existing.id if existing else None,
        })

    # A published project may be linked as an addon choice. Every such link must
    # be in the copied set, otherwise the cloned catalog would reference the
    # source store across the tenant boundary.
    source_project_by_id = {project.id: project for project in source_projects}
    for item in project_items:
        version_id = (item["catalog_version"] or {}).get("id")
        if not version_id:
            continue
        group_ids = list(db.scalars(
            select(ProjectOptionGroup.id).where(ProjectOptionGroup.catalog_version_id == version_id)
        ))
        if not group_ids:
            continue
        linked_ids = set(db.scalars(
            select(ProjectOptionChoice.linked_project_id).where(
                ProjectOptionChoice.option_group_id.in_(group_ids),
                ProjectOptionChoice.linked_project_id.is_not(None),
            )
        ))
        missing = sorted(linked_ids - source_project_ids)
        if missing:
            conflicts.append({
                "kind": "linked_project_outside_clone",
                "source_code": item["source_code"],
                "linked_project_ids": missing,
            })

    source_addons = list(db.scalars(
        select(Addon)
        .where(Addon.store_id == source.id, Addon.publication_status == "published")
        .order_by(Addon.display_order, Addon.id)
    ))
    addon_items: list[dict] = []
    cloned_source_ids = {item["source_id"] for item in project_items}
    for addon in source_addons:
        target_code = f"{code_prefix}{addon.code}"
        if len(target_code) > MAX_CODE_LENGTH:
            conflicts.append({"kind": "target_code_too_long", "code": target_code, "source_code": addon.code})
            continue
        existing = db.scalar(select(Addon).where(Addon.store_id == target.id, Addon.code == target_code))
        other_store = db.scalar(select(Addon).where(Addon.code == target_code, Addon.store_id != target.id))
        if other_store is not None:
            conflicts.append({
                "kind": "addon_code_used_by_other_store",
                "code": target_code,
                "other_store_id": other_store.store_id,
            })
        parent = source_project_by_id.get(addon.parent_project_id) if addon.parent_project_id else None
        if addon.parent_project_id and (parent is None or parent.id not in cloned_source_ids):
            conflicts.append({
                "kind": "addon_parent_not_cloneable",
                "code": addon.code,
                "parent_project_id": addon.parent_project_id,
            })
        addon_items.append({
            "source_id": addon.id,
            "source_code": addon.code,
            "target_code": target_code,
            "name": addon.name,
            "parent_source_id": addon.parent_project_id,
            "target_parent_code": f"{code_prefix}{parent.code}" if parent else None,
            "duration_min": addon.duration_min,
            "summary": addon.summary,
            "image_url": addon.image_url,
            "display_order": addon.display_order,
            "chargeable": bool(addon.chargeable),
            "store_price_cents": addon.store_price_cents,
            "member_price_cents": addon.member_price_cents,
            "member_price_enabled": bool(addon.member_price_enabled),
            "independently_sellable": bool(addon.independently_sellable),
            "can_attach_to_parent": bool(addon.can_attach_to_parent),
            "price_cents": addon.price_cents,
            "existing_target_id": existing.id if existing else None,
        })

    source_page = db.scalar(select(PageContent).where(
        PageContent.store_id == source.id, PageContent.page_key == PAGE_KEY,
    ))
    if source_page is None:
        conflicts.append({"kind": "source_page_missing", "page_key": PAGE_KEY})
        page_item = None
    else:
        existing_page = db.scalar(select(PageContent).where(
            PageContent.store_id == target.id, PageContent.page_key == PAGE_KEY,
        ))
        page_item = {
            "page_key": PAGE_KEY,
            "title": source_page.title,
            "subtitle": source_page.subtitle,
            "promo_banners": list(source_page.promo_banners or []),
            "tea_options": list(source_page.tea_options or []),
            "coupon_prompt": dict(source_page.coupon_prompt or {}),
            "brand_story": dict(source_page.brand_story or {}),
            "source_published": bool(source_page.published),
            "existing_target_id": existing_page.id if existing_page else None,
        }

    source_rooms = list(db.scalars(
        select(Room).where(Room.store_id == source.id).order_by(Room.sort_order, Room.id)
    ))
    room_items: list[dict] = []
    for room in source_rooms:
        target_code = f"{code_prefix}{room.code}"
        if len(target_code) > MAX_CODE_LENGTH:
            conflicts.append({"kind": "room_code_too_long", "code": target_code, "source_code": room.code})
            continue
        existing = db.scalar(select(Room).where(Room.store_id == target.id, Room.code == target_code))
        other_store = db.scalar(select(Room).where(Room.code == target_code, Room.store_id != target.id))
        if other_store is not None:
            conflicts.append({
                "kind": "room_code_used_by_other_store",
                "code": target_code,
                "other_store_id": other_store.store_id,
            })
        room_items.append({
            "source_id": room.id,
            "source_code": room.code,
            "target_code": target_code,
            "name": room.name,
            "parent_source_id": room.parent_room_id,
            "room_type": room.room_type,
            "room_group": room.room_group,
            "floor": room.floor,
            "capacity": room.capacity,
            "note": room.note,
            "sort_order": room.sort_order,
            "customer_label": room.customer_label,
            "map_x": room.map_x,
            "map_y": room.map_y,
            "map_width": room.map_width,
            "map_height": room.map_height,
            "customer_selectable": bool(room.customer_selectable),
            "is_space_container": bool(room.is_space_container),
            "is_service_position": bool(room.is_service_position),
            "operational_status": room.operational_status,
            "existing_target_id": existing.id if existing else None,
        })

    qr_targets = list(db.scalars(
        select(ServicePositionQr)
        .where(ServicePositionQr.store_id == source.id, ServicePositionQr.status == "active")
        .order_by(ServicePositionQr.id)
    ))
    qr_items = []
    for qr in qr_targets:
        room = db.get(Room, qr.room_id)
        if room is None:
            warnings.append({"kind": "qr_room_missing", "qr_id": qr.id})
            continue
        qr_items.append({
            "source_qr_id": qr.id,
            "room_source_code": room.code,
            "room_target_code": f"{code_prefix}{room.code}",
            "source": qr.source,
        })

    counts = {
        "projects": len(project_items),
        "catalog_versions": sum(1 for item in project_items if item["catalog_version"]),
        "option_groups": sum((item["catalog_version"] or {}).get("groups", 0) for item in project_items),
        "option_choices": sum((item["catalog_version"] or {}).get("choices", 0) for item in project_items),
        "addons": len(addon_items),
        "pages": 1 if page_item else 0,
        "rooms": len(room_items),
        "service_positions": sum(1 for item in room_items if item["is_service_position"]),
        "qrs": len(qr_items),
    }
    plan = {
        "source_store": {"id": source.id, "store_code": source.store_code, "name": source.name},
        "target_store": {"id": target.id, "store_code": target.store_code, "name": target.name, "status": target.status},
        "code_prefix": code_prefix,
        "projects": project_items,
        "addons": addon_items,
        "page": page_item,
        "rooms": room_items,
        "qr_targets": qr_items,
        "counts": counts,
        "conflicts": conflicts,
        "warnings": warnings,
    }
    plan["preview_hash"] = plan_hash(plan)
    return plan


def _verify_existing_project(db, existing: Project, item: dict) -> None:
    if existing.name != item["name"]:
        raise ValueError(f"目标项目 {item['target_code']} 已存在但名称不同")
    if existing.publication_status != "published":
        raise ValueError(f"目标项目 {item['target_code']} 已存在但未发布")
    prices = _current_prices(db, existing.id)
    for price_type, amount in item["prices"].items():
        rows = prices.get(price_type, [])
        if len(rows) != 1 or rows[0].amount_cents != amount:
            raise ValueError(f"目标项目 {item['target_code']} 的 {price_type} 价格与源不一致")


def _create_project(db, target: Store, item: dict) -> Project:
    project = Project(
        store_id=target.id,
        code=item["target_code"],
        category=item["category"],
        category_mark=item["category_mark"],
        name=item["name"],
        duration_min=item["duration_min"],
        summary=item["summary"],
        image_url=item["image_url"],
        tags=list(item["tags"]),
        detail_modules=list(item["detail_modules"]),
        diy_options=list(item["diy_options"]),
        display_order=item["display_order"],
        price_label=item["price_label"],
        content_version=item["content_version"],
        independently_visible=item["independently_visible"],
        publication_status="published",
    )
    db.add(project)
    db.flush()
    for price_type, amount in item["prices"].items():
        db.add(PriceBook(
            project_id=project.id,
            price_type=price_type,
            amount_cents=amount,
            version=item["content_version"] or "store-clone",
            publisher="store-clone",
            published_at=datetime.now(UTC),
        ))
    return project


def _publish_order(db, version_items: dict[int, int], project_id_map: dict[int, int]) -> list[int]:
    """Return source project ids in dependency-first order for catalog publishing."""
    dependencies: dict[int, set[int]] = {source_id: set() for source_id in version_items}
    for source_id, target_version_id in version_items.items():
        group_ids = list(db.scalars(
            select(ProjectOptionGroup.id).where(ProjectOptionGroup.catalog_version_id == target_version_id)
        ))
        if not group_ids:
            continue
        linked_target_ids = set(db.scalars(
            select(ProjectOptionChoice.linked_project_id).where(
                ProjectOptionChoice.option_group_id.in_(group_ids),
                ProjectOptionChoice.linked_project_id.is_not(None),
            )
        ))
        target_to_source = {target_id: source for source, target_id in project_id_map.items()}
        for linked_target_id in linked_target_ids:
            linked_source_id = target_to_source.get(linked_target_id)
            if linked_source_id in version_items:
                dependencies[source_id].add(linked_source_id)
    ordered: list[int] = []
    remaining = set(version_items)
    while remaining:
        ready = sorted(source_id for source_id in remaining if not (dependencies[source_id] & remaining))
        if not ready:
            raise ValueError("目录引用存在循环，无法确定发布顺序")
        for source_id in ready:
            ordered.append(source_id)
            remaining.remove(source_id)
    return ordered


def apply_clone_plan(
    db,
    plan: dict,
    *,
    actor_staff_id: int,
    publish_page: bool = False,
) -> dict:
    """Apply a validated clone plan in the caller's transaction."""

    expected_hash = plan.get("preview_hash")
    current = build_clone_plan(
        db,
        source_store_id=plan["source_store"]["id"],
        target_store_id=plan["target_store"]["id"],
        code_prefix=plan["code_prefix"],
    )
    if not expected_hash or current["preview_hash"] != expected_hash:
        raise ValueError("预览已变化，请重新生成预览")
    if current["conflicts"]:
        raise ValueError("预览存在冲突，不能应用")

    actor = db.get(Staff, actor_staff_id)
    if actor is None or actor.status != "active" or actor.role != "admin" or actor.store_id is not None:
        raise ValueError("actor 必须是有效的总部管理员")

    target = _require_store(db, plan["target_store"]["id"])
    created = {"projects": 0, "catalog_versions": 0, "addons": 0, "pages": 0, "rooms": 0}

    project_id_map: dict[int, int] = {}
    for item in plan["projects"]:
        existing = db.scalar(select(Project).where(
            Project.store_id == target.id, Project.code == item["target_code"],
        ))
        if existing is not None:
            _verify_existing_project(db, existing, item)
            project_id_map[item["source_id"]] = existing.id
            continue
        project = _create_project(db, target, item)
        project_id_map[item["source_id"]] = project.id
        created["projects"] += 1
    db.flush()

    version_items: dict[int, int] = {}
    needs_publish: set[int] = set()
    for item in plan["projects"]:
        if not item["catalog_version"]:
            continue
        target_project = db.get(Project, project_id_map[item["source_id"]])
        existing_version = db.scalar(select(ProjectCatalogVersion).where(
            ProjectCatalogVersion.project_id == target_project.id,
        ).order_by(ProjectCatalogVersion.id))
        if existing_version is not None:
            version_items[item["source_id"]] = existing_version.id
            if existing_version.status == "draft":
                needs_publish.add(item["source_id"])
            continue
        source_version = db.get(ProjectCatalogVersion, item["catalog_version"]["id"])
        if source_version is None or source_version.status != "published":
            raise ValueError(f"源目录版本不可用: {item['catalog_version']['id']}")
        draft = ProjectCatalogVersion(project_id=target_project.id, version=1, status="draft")
        db.add(draft)
        db.flush()
        copy_catalog_version_graph(db, source_version.id, draft.id)
        group_ids = list(db.scalars(
            select(ProjectOptionGroup.id).where(ProjectOptionGroup.catalog_version_id == draft.id)
        ))
        if group_ids:
            for choice in db.scalars(
                select(ProjectOptionChoice).where(ProjectOptionChoice.option_group_id.in_(group_ids))
            ):
                if choice.linked_project_id is None:
                    continue
                mapped = project_id_map.get(choice.linked_project_id)
                if mapped is None:
                    raise ValueError(f"选项引用的源项目未复制: {choice.linked_project_id}")
                choice.linked_project_id = mapped
        version_items[item["source_id"]] = draft.id
        needs_publish.add(item["source_id"])
        created["catalog_versions"] += 1
    db.flush()

    order = _publish_order(db, version_items, project_id_map)
    for source_id in order:
        if source_id in needs_publish:
            publish_catalog_version(db, project_id_map[source_id], actor_staff_id)

    for item in plan["addons"]:
        existing = db.scalar(select(Addon).where(
            Addon.store_id == target.id, Addon.code == item["target_code"],
        ))
        if existing is not None:
            if existing.name != item["name"]:
                raise ValueError(f"目标加购 {item['target_code']} 已存在但名称不同")
            continue
        parent_id = project_id_map.get(item["parent_source_id"]) if item["parent_source_id"] else None
        db.add(Addon(
            store_id=target.id,
            code=item["target_code"],
            name=item["name"],
            parent_project_id=parent_id,
            duration_min=item["duration_min"],
            summary=item["summary"],
            image_url=item["image_url"],
            display_order=item["display_order"],
            chargeable=item["chargeable"],
            store_price_cents=item["store_price_cents"],
            member_price_cents=item["member_price_cents"],
            member_price_enabled=item["member_price_enabled"],
            independently_sellable=item["independently_sellable"],
            can_attach_to_parent=item["can_attach_to_parent"],
            price_cents=item["price_cents"],
            publication_status="published",
        ))
        created["addons"] += 1

    page_item = plan["page"]
    if page_item:
        existing_page = db.scalar(select(PageContent).where(
            PageContent.store_id == target.id, PageContent.page_key == PAGE_KEY,
        ))
        if existing_page is None:
            db.add(PageContent(
                store_id=target.id,
                page_key=PAGE_KEY,
                title=page_item["title"],
                subtitle=page_item["subtitle"],
                promo_banners=list(page_item["promo_banners"]),
                tea_options=list(page_item["tea_options"]),
                coupon_prompt=dict(page_item["coupon_prompt"]),
                brand_story=dict(page_item["brand_story"]),
                published=bool(publish_page and page_item["source_published"]),
            ))
            created["pages"] += 1
        elif publish_page and page_item["source_published"] and not existing_page.published:
            existing_page.published = True

    room_id_map: dict[int, int] = {}
    room_items = sorted(plan["rooms"], key=lambda item: (item["parent_source_id"] is not None, item["sort_order"], item["source_id"]))
    for item in room_items:
        existing = db.scalar(select(Room).where(Room.store_id == target.id, Room.code == item["target_code"]))
        if existing is not None:
            room_id_map[item["source_id"]] = existing.id
            continue
        parent_id = room_id_map.get(item["parent_source_id"]) if item["parent_source_id"] else None
        if item["parent_source_id"] and parent_id is None:
            raise ValueError(f"空间父级未创建: {item['parent_source_id']}")
        room = Room(
            store_id=target.id,
            parent_room_id=parent_id,
            code=item["target_code"],
            name=item["name"],
            room_type=item["room_type"],
            room_group=item["room_group"],
            floor=item["floor"],
            capacity=item["capacity"],
            used_count=0,
            current_tech="",
            status="available",
            note=item["note"],
            sort_order=item["sort_order"],
            customer_label=item["customer_label"],
            map_x=item["map_x"],
            map_y=item["map_y"],
            map_width=item["map_width"],
            map_height=item["map_height"],
            customer_selectable=item["customer_selectable"],
            is_space_container=item["is_space_container"],
            is_service_position=item["is_service_position"],
            operational_status=item["operational_status"],
            version=1,
        )
        db.add(room)
        db.flush()
        room_id_map[item["source_id"]] = room.id
        created["rooms"] += 1

    db.add(AuditLog(
        actor_type="staff",
        actor_id=str(actor.id),
        action="store_provisioned_from_template",
        entity_type="store",
        entity_id=str(target.id),
        store_id=target.id,
        detail={
            "source_store_id": plan["source_store"]["id"],
            "preview_hash": expected_hash,
            "created": created,
            "counts": plan["counts"],
        },
    ))
    db.flush()
    return {"preview_hash": expected_hash, "created": created, "counts": plan["counts"]}


def _check_backup(path: Path | None, sha256: str | None) -> None:
    if path is None or not path.is_file() or path.is_symlink():
        raise ValueError("apply 需要真实备份文件")
    with path.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise ValueError("需要 PostgreSQL custom-format 备份")
        stream.seek(0)
        if hashlib.file_digest(stream, "sha256").hexdigest() != sha256:
            raise ValueError("备份摘要不匹配")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-store-id", type=int, default=1)
    parser.add_argument("--target-store-id", type=int, required=True)
    parser.add_argument("--code-prefix", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-hash")
    parser.add_argument("--actor-staff-id", type=int)
    parser.add_argument("--publish-page", action="store_true")
    parser.add_argument("--backup-reference", type=Path)
    parser.add_argument("--backup-sha256")
    args = parser.parse_args()

    if args.apply:
        if not args.expected_hash or args.actor_staff_id is None:
            parser.error("apply requires --expected-hash and --actor-staff-id")
        _check_backup(args.backup_reference, args.backup_sha256)

    with SessionLocal() as db:
        try:
            if db.bind.dialect.name == "postgresql":
                if not args.apply:
                    db.execute(text("SET TRANSACTION READ ONLY"))
                db.execute(text("SET LOCAL lock_timeout = '5s'"))
                db.execute(text("SET LOCAL statement_timeout = '60s'"))
            plan = build_clone_plan(
                db,
                source_store_id=args.source_store_id,
                target_store_id=args.target_store_id,
                code_prefix=args.code_prefix,
            )
            if args.apply:
                result = apply_clone_plan(
                    db,
                    plan,
                    actor_staff_id=args.actor_staff_id,
                    publish_page=args.publish_page,
                )
                db.commit()
                print(json.dumps(result, ensure_ascii=False))
            else:
                db.rollback()
                print(json.dumps(plan, ensure_ascii=False))
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()
