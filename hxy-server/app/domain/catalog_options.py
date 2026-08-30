"""目录草稿校验、发布与已发布配置解析。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import unicodedata

from sqlalchemy import or_, select, text, update
from sqlalchemy.orm import Session

from app.models import (
    OptionChoicePrice,
    PriceBook,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
)


@dataclass(frozen=True)
class CatalogValidationError:
    code: str
    path: str
    message: str


class CatalogDomainError(RuntimeError):
    """目录领域操作失败。"""


class CatalogProjectNotFoundError(CatalogDomainError):
    def __init__(self, project_id: int):
        super().__init__(f"项目不存在: {project_id}")
        self.project_id = project_id


_LOCAL_BODY_PARTS = frozenset({"肩颈", "腰臀", "腿部", "腹部", "足部"})


def _local_body_part(
    group: ProjectOptionGroup,
    choice: ProjectOptionChoice,
    linked: Project,
) -> str | None:
    if group.code != "local-strength" or linked.category != "local-strength":
        return None
    normalized = "".join(unicodedata.normalize("NFKC", choice.name or "").split())
    return normalized if normalized in _LOCAL_BODY_PARTS else None


class CatalogDraftNotFoundError(CatalogDomainError):
    def __init__(self, project_id: int):
        super().__init__(f"项目没有可发布的目录草稿: {project_id}")
        self.project_id = project_id


class CatalogPublishedGraphDriftError(CatalogDomainError):
    def __init__(self, project_id: int, version_id: int):
        super().__init__(f"已发布目录快照校验失败: project={project_id}, version={version_id}")
        self.project_id = project_id
        self.version_id = version_id


class CatalogConcurrencyError(CatalogDomainError):
    """目录写入的锁或条件更新未取得预期状态。"""


CATALOG_MUTATION_ADVISORY_LOCK_ID = 1213757763


def acquire_catalog_mutation_lock(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": CATALOG_MUTATION_ADVISORY_LOCK_ID},
        )


def lock_catalog_projects(db: Session, project_ids: list[int] | tuple[int, ...] | set[int]) -> dict[int, Project]:
    """按稳定 Project ID 顺序锁定项目及其目录版本。

    PostgreSQL 以 ``FOR UPDATE`` 提供互斥；后续状态更新仍使用条件更新，
    因而 SQLite focused test 不会被误当作并发正确性的证明。
    """
    acquire_catalog_mutation_lock(db)
    ids = sorted({int(project_id) for project_id in project_ids})
    if not ids:
        return {}
    projects = list(db.scalars(
        select(Project)
        .where(Project.id.in_(ids))
        .order_by(Project.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))
    # 与 Project 锁使用同一顺序，避免跨项目引用的倒序死锁。
    list(db.scalars(
        select(ProjectCatalogVersion)
        .where(ProjectCatalogVersion.project_id.in_(ids))
        .order_by(ProjectCatalogVersion.project_id, ProjectCatalogVersion.version, ProjectCatalogVersion.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))
    return {project.id: project for project in projects}


def copy_catalog_version_graph(
    db: Session,
    source_version_id: int,
    target_version_id: int,
) -> None:
    """Copy every group, choice, and price row between catalog versions."""

    source = db.get(ProjectCatalogVersion, source_version_id)
    if source is None:
        raise CatalogDomainError(f"目录版本不存在: {source_version_id}")
    if source.status == "published":
        verify_published_catalog_hash(db, source)

    groups = list(db.scalars(
        select(ProjectOptionGroup)
        .where(ProjectOptionGroup.catalog_version_id == source_version_id)
        .order_by(ProjectOptionGroup.id)
    ))
    for group in groups:
        copied_group = ProjectOptionGroup(
            catalog_version_id=target_version_id,
            code=group.code,
            name=group.name,
            description=group.description,
            selection_mode=group.selection_mode,
            required=group.required,
            min_select=group.min_select,
            max_select=group.max_select,
            display_order=group.display_order,
        )
        db.add(copied_group)
        db.flush()
        choices = list(db.scalars(
            select(ProjectOptionChoice)
            .where(ProjectOptionChoice.option_group_id == group.id)
            .order_by(ProjectOptionChoice.id)
        ))
        for choice in choices:
            copied_choice = ProjectOptionChoice(
                option_group_id=copied_group.id,
                code=choice.code,
                name=choice.name,
                description=choice.description,
                choice_type=choice.choice_type,
                linked_project_id=choice.linked_project_id,
                pinned_linked_catalog_version_id=choice.pinned_linked_catalog_version_id,
                charge_mode=choice.charge_mode,
                independently_visible=choice.independently_visible,
                coupon_eligible=choice.coupon_eligible,
                annual_gift_eligible=choice.annual_gift_eligible,
                qualifies_for_foot_bath_bundle=choice.qualifies_for_foot_bath_bundle,
                display_order=choice.display_order,
                status=choice.status,
            )
            db.add(copied_choice)
            db.flush()
            prices = list(db.scalars(
                select(OptionChoicePrice)
                .where(OptionChoicePrice.option_choice_id == choice.id)
                .order_by(OptionChoicePrice.id)
            ))
            for price in prices:
                db.add(OptionChoicePrice(
                    option_choice_id=copied_choice.id,
                    price_type=price.price_type,
                    amount_cents=price.amount_cents,
                    effective_from=price.effective_from,
                    effective_to=price.effective_to,
                ))
    db.flush()


class CatalogPublishedVersionNotFoundError(CatalogDomainError):
    def __init__(self, project_id: int):
        super().__init__(f"项目没有当前已发布目录版本: {project_id}")
        self.project_id = project_id


class CatalogPublicationError(CatalogDomainError):
    def __init__(self, errors: list[CatalogValidationError]):
        super().__init__("目录草稿校验失败")
        self.errors = errors


def _error(code: str, path: str, message: str) -> CatalogValidationError:
    return CatalogValidationError(code=code, path=path, message=message)


def _groups(db: Session, version_id: int) -> list[ProjectOptionGroup]:
    return list(db.scalars(
        select(ProjectOptionGroup)
        .where(ProjectOptionGroup.catalog_version_id == version_id)
        .order_by(ProjectOptionGroup.display_order, ProjectOptionGroup.code, ProjectOptionGroup.id)
    ))


def _choices(db: Session, group_id: int) -> list[ProjectOptionChoice]:
    return list(db.scalars(
        select(ProjectOptionChoice)
        .where(ProjectOptionChoice.option_group_id == group_id)
        .order_by(ProjectOptionChoice.display_order, ProjectOptionChoice.code, ProjectOptionChoice.id)
    ))


def _published_version(db: Session, project: Project) -> ProjectCatalogVersion | None:
    if project.current_published_version_id is None:
        return None
    version = db.get(ProjectCatalogVersion, project.current_published_version_id)
    if version is None or version.project_id != project.id or version.status != "published":
        return None
    return version


def verify_published_catalog_hash(db: Session, version: ProjectCatalogVersion) -> None:
    """已冻结目录必须仍等于发布时哈希，漂移时拒绝继续读取或复制。"""
    if version.status not in {"published", "superseded"}:
        raise CatalogPublishedGraphDriftError(version.project_id, version.id)
    expected = version.snapshot_hash
    actual = _snapshot_hash(db, version.id)
    if not expected or expected != actual:
        raise CatalogPublishedGraphDriftError(version.project_id, version.id)


def _has_current_price(db: Session, choice_id: int, price_type: str, now: datetime) -> bool:
    return db.scalar(
        select(OptionChoicePrice.id)
        .where(
            OptionChoicePrice.option_choice_id == choice_id,
            OptionChoicePrice.price_type == price_type,
            OptionChoicePrice.effective_from <= now,
            or_(OptionChoicePrice.effective_to.is_(None), OptionChoicePrice.effective_to > now),
        )
        .limit(1)
    ) is not None


def _has_project_store_price(db: Session, project_id: int) -> bool:
    return db.scalar(
        select(PriceBook.id)
        .where(
            PriceBook.project_id == project_id,
            PriceBook.price_type == "store",
            PriceBook.amount_cents >= 0,
        )
        .limit(1)
    ) is not None


def _choice_prices(db: Session, choice_id: int) -> list[OptionChoicePrice]:
    return list(db.scalars(
        select(OptionChoicePrice)
        .where(OptionChoicePrice.option_choice_id == choice_id)
        .order_by(OptionChoicePrice.price_type, OptionChoicePrice.effective_from, OptionChoicePrice.id)
    ))


def choice_contract_errors(
    choice: ProjectOptionChoice,
    *,
    has_local_prices: bool,
    path: str,
) -> list[CatalogValidationError]:
    """三种选项联合语义的唯一规则来源。"""
    errors: list[CatalogValidationError] = []
    if choice.choice_type == "preference":
        if choice.charge_mode != "free":
            errors.append(_error("preference_must_be_free", f"{path}.charge_mode", "偏好选项必须免费"))
        if choice.linked_project_id is not None:
            errors.append(_error("preference_cannot_link_project", f"{path}.linked_project_id", "免费偏好不得指向正式项目"))
        if has_local_prices:
            errors.append(_error("free_choice_cannot_have_prices", f"{path}.prices", "免费偏好不得配置本地价格"))
        return errors

    if choice.choice_type == "linked_project":
        if choice.charge_mode != "inherit_linked_price":
            errors.append(_error("linked_project_must_inherit_linked_price", f"{path}.charge_mode", "项目引用选项必须继承引用项目价格"))
        if choice.linked_project_id is None:
            errors.append(_error("linked_project_required", f"{path}.linked_project_id", "项目引用选项必须指定引用项目"))
        if has_local_prices:
            errors.append(_error("linked_choice_cannot_have_prices", f"{path}.prices", "项目引用选项不得配置本地价格"))
        return errors

    if choice.choice_type == "dedicated_charge":
        if choice.charge_mode != "custom_price":
            errors.append(_error("dedicated_charge_must_use_custom_price", f"{path}.charge_mode", "独立收费选项必须使用自定义价格"))
        if choice.linked_project_id is not None:
            errors.append(_error("dedicated_charge_cannot_link_project", f"{path}.linked_project_id", "独立收费选项不得指向引用项目"))
        if not has_local_prices:
            errors.append(_error("custom_price_required", f"{path}.prices", "独立收费选项必须配置本地价格"))
        return errors

    return [_error("unknown_choice_type", f"{path}.choice_type", "未知选项类型")]


def _price_interval_errors(
    prices: list[OptionChoicePrice],
    path: str,
) -> list[CatalogValidationError]:
    def utc_value(value: datetime) -> datetime:
        # SQLite 不保留 DateTime(timezone=True) 的 tzinfo；比较时按 UTC 还原。
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    errors: list[CatalogValidationError] = []
    by_type: dict[str, list[OptionChoicePrice]] = {}
    for price in prices:
        price_path = f"{path}.prices.{price.price_type}"
        if price.amount_cents < 0:
            errors.append(_error("negative_option_price", price_path, "选项价格不得为负数"))
        if price.effective_to is not None and utc_value(price.effective_to) <= utc_value(price.effective_from):
            errors.append(_error("invalid_option_price_interval", price_path, "价格结束时间必须晚于开始时间"))
        by_type.setdefault(price.price_type, []).append(price)
    for price_type, rows in by_type.items():
        ordered = sorted(rows, key=lambda row: (utc_value(row.effective_from), row.id))
        for previous, current in zip(ordered, ordered[1:]):
            if previous.effective_to is None or utc_value(previous.effective_to) > utc_value(current.effective_from):
                errors.append(_error(
                    "overlapping_option_price_intervals",
                    f"{path}.prices.{price_type}",
                    "同一价格类型的生效区间不得重叠",
                ))
                break
    return errors


def _linked_choices(db: Session, version_id: int) -> list[tuple[ProjectOptionGroup, ProjectOptionChoice]]:
    rows: list[tuple[ProjectOptionGroup, ProjectOptionChoice]] = []
    for group in _groups(db, version_id):
        for choice in _choices(db, group.id):
            if choice.status == "active" and choice.choice_type == "linked_project":
                rows.append((group, choice))
    return rows


def _validate_link_graph(
    db: Session,
    *,
    root_project_id: int,
    root_version_id: int,
) -> list[CatalogValidationError]:
    errors: list[CatalogValidationError] = []

    def walk(
        version_id: int,
        ancestry: tuple[int, ...],
        depth: int,
        root_path: str | None = None,
    ) -> None:
        for group, choice in _linked_choices(db, version_id):
            path = root_path or f"groups.{group.code}.choices.{choice.code}"
            if choice.linked_project_id is None:
                continue
            if choice.linked_project_id in ancestry:
                errors.append(_error(
                    "project_link_cycle",
                    path,
                    "项目引用形成循环",
                ))
                continue
            if depth >= 2:
                errors.append(_error(
                    "project_link_depth_exceeded",
                    path,
                    "项目引用嵌套最多允许两层",
                ))
                continue
            linked = db.get(Project, choice.linked_project_id)
            if linked is None:
                continue
            published = _published_version(db, linked)
            if published is None:
                continue
            walk(
                published.id,
                (*ancestry, linked.id),
                depth + 1,
                path,
            )

    walk(root_version_id, (root_project_id,), 0)
    return errors


def validate_catalog_version(db: Session, version_id: int) -> list[CatalogValidationError]:
    """返回草稿的全部可证目录错误，不修改数据库状态。"""
    version = db.get(ProjectCatalogVersion, version_id)
    if version is None:
        return [_error("catalog_version_not_found", "version", "目录版本不存在")]
    project = db.get(Project, version.project_id)
    if project is None:
        return [_error("project_not_found", "project", "目录所属项目不存在")]

    errors: list[CatalogValidationError] = []
    now = datetime.now(UTC)
    seen_group_codes: set[str] = set()
    seen_linked_units: dict[int, set[str | None]] = {}

    for group in _groups(db, version.id):
        group_path = f"groups.{group.code}"
        if group.code in seen_group_codes:
            errors.append(_error("duplicate_group_code", f"{group_path}.code", "选项组编码重复"))
        seen_group_codes.add(group.code)

        choices = _choices(db, group.id)
        active_choices = [choice for choice in choices if choice.status == "active"]
        if group.required and not active_choices:
            errors.append(_error("required_group_empty", group_path, "必选组必须至少有一个可用选项"))
        if group.min_select < 0:
            errors.append(_error(
                "min_select_negative",
                f"{group_path}.min_select",
                "最少选择数不得小于 0",
            ))
        if group.max_select < 0:
            errors.append(_error(
                "max_select_negative",
                f"{group_path}.max_select",
                "最多选择数不得小于 0",
            ))
        if group.required and group.max_select == 0:
            errors.append(_error(
                "required_group_max_zero",
                f"{group_path}.max_select",
                "必选组的最多选择数必须大于 0",
            ))
        if group.selection_mode == "single" and group.max_select > 1:
            errors.append(_error(
                "single_group_max_exceeds_one",
                f"{group_path}.max_select",
                "单选组的最多选择数不得大于 1",
            ))
        if group.min_select > group.max_select:
            errors.append(_error(
                "min_select_exceeds_max",
                f"{group_path}.min_select",
                "最少选择数不得大于最多选择数",
            ))
        if group.min_select > len(active_choices):
            errors.append(_error(
                "min_select_exceeds_available",
                f"{group_path}.min_select",
                "最少选择数不得大于可用选项数",
            ))
        if group.max_select > len(active_choices):
            errors.append(_error(
                "max_select_exceeds_available",
                f"{group_path}.max_select",
                "最多选择数不得大于可用选项数",
            ))

        for choice in choices:
            choice_path = f"{group_path}.choices.{choice.code}"
            if choice.status != "active":
                continue
            prices = _choice_prices(db, choice.id)
            errors.extend(choice_contract_errors(
                choice,
                has_local_prices=bool(prices),
                path=choice_path,
            ))
            errors.extend(_price_interval_errors(prices, choice_path))

            if choice.charge_mode == "custom_price" and not _has_current_price(
                db, choice.id, "store", now
            ):
                errors.append(_error(
                    "store_price_required",
                    f"{choice_path}.prices.store",
                    "收费选项必须配置当前有效的门店价",
                ))

            if (
                choice.qualifies_for_foot_bath_bundle
                and choice.choice_type == "preference"
                and choice.charge_mode == "free"
            ):
                errors.append(_error(
                    "bundle_qualification_requires_charge",
                    f"{choice_path}.qualifies_for_foot_bath_bundle",
                    "免费偏好不得配置泡脚组合资格",
                ))

            if choice.choice_type != "linked_project":
                continue
            if choice.linked_project_id is None:
                errors.append(_error(
                    "linked_project_required",
                    f"{choice_path}.linked_project_id",
                    "项目引用选项必须指定引用项目",
                ))
                continue
            linked = db.get(Project, choice.linked_project_id)
            if linked is None:
                errors.append(_error(
                    "linked_project_not_found",
                    f"{choice_path}.linked_project_id",
                    "引用项目不存在",
                ))
                continue
            body_part = _local_body_part(group, choice, linked)
            seen_parts = seen_linked_units.setdefault(linked.id, set())
            duplicate_link = (
                bool(seen_parts)
                if body_part is None
                else body_part in seen_parts or None in seen_parts
            )
            if duplicate_link:
                errors.append(_error(
                    "duplicate_linked_project",
                    f"{choice_path}.linked_project_id",
                    "缺少明确部位时，同一主项目不得重复引用同一项目",
                ))
            seen_parts.add(body_part)
            if linked.store_id != project.store_id:
                errors.append(_error(
                    "linked_project_cross_store",
                    f"{choice_path}.linked_project_id",
                    "引用项目必须与主项目属于同一门店",
                ))
            if linked.publication_status == "archived":
                errors.append(_error(
                    "linked_project_archived",
                    f"{choice_path}.linked_project_id",
                    "归档项目不得被当前目录引用",
                ))
            elif linked.publication_status != "published":
                errors.append(_error(
                    "linked_project_unpublished",
                    f"{choice_path}.linked_project_id",
                    "引用项目必须已发布且可用",
                ))
            if linked.current_published_version_id is not None and _published_version(db, linked) is None:
                errors.append(_error(
                    "linked_project_catalog_unpublished",
                    f"{choice_path}.linked_project_id",
                    "引用项目必须具有当前已发布目录版本",
                ))
            if not _has_project_store_price(db, linked.id):
                errors.append(_error(
                    "linked_project_store_price_required",
                    f"{choice_path}.linked_project_id",
                    "引用项目必须配置当前有效的门店价",
                ))

    errors.extend(_validate_link_graph(
        db,
        root_project_id=project.id,
        root_version_id=version.id,
    ))
    return errors


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _price_config(price: OptionChoicePrice) -> dict:
    return {
        "price_type": price.price_type,
        "amount_cents": price.amount_cents,
        "effective_from": _isoformat(price.effective_from),
        "effective_to": _isoformat(price.effective_to),
    }


def _choice_config(db: Session, choice: ProjectOptionChoice) -> dict:
    prices = _choice_prices(db, choice.id)
    linked_project = db.get(Project, choice.linked_project_id) if choice.linked_project_id else None
    linked_catalog_version_id: int | None = None
    if choice.choice_type == "linked_project":
        pinned = choice.pinned_linked_catalog_version_id
        if pinned is not None:
            linked_version = db.get(ProjectCatalogVersion, pinned)
            if (
                linked_project is None
                or linked_version is None
                or linked_version.project_id != linked_project.id
                or linked_version.status not in {"published", "superseded"}
            ):
                raise CatalogPublishedGraphDriftError(
                    linked_project.id if linked_project else -1,
                    pinned,
                )
            verify_published_catalog_hash(db, linked_version)
            linked_catalog_version_id = linked_version.id
    return {
        "code": choice.code,
        "name": choice.name,
        "description": choice.description,
        "choice_type": choice.choice_type,
        "linked_project_id": choice.linked_project_id,
        "linked_project_code": linked_project.code if linked_project else None,
        "pinned_linked_catalog_version_id": choice.pinned_linked_catalog_version_id,
        "linked_catalog_version_id": linked_catalog_version_id,
        "charge_mode": choice.charge_mode,
        "independently_visible": choice.independently_visible,
        "coupon_eligible": choice.coupon_eligible,
        "annual_gift_eligible": choice.annual_gift_eligible,
        "qualifies_for_foot_bath_bundle": choice.qualifies_for_foot_bath_bundle,
        "display_order": choice.display_order,
        "status": choice.status,
        "prices": [_price_config(price) for price in prices],
    }


def _group_config(db: Session, group: ProjectOptionGroup) -> dict:
    return {
        "code": group.code,
        "name": group.name,
        "description": group.description,
        "selection_mode": group.selection_mode,
        "required": group.required,
        "min_select": group.min_select,
        "max_select": group.max_select,
        "display_order": group.display_order,
        "choices": [_choice_config(db, choice) for choice in _choices(db, group.id)],
    }


def _version_content(db: Session, version_id: int) -> dict:
    return {
        "groups": [_group_config(db, group) for group in _groups(db, version_id)],
    }


def _snapshot_hash(db: Session, version_id: int) -> str:
    content = _version_content(db, version_id)
    encoded = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def publish_catalog_version(
    db: Session,
    project_id: int,
    staff_id: int,
) -> ProjectCatalogVersion:
    """校验并发布最新草稿；提交或回滚由调用方统一控制。"""
    projects = lock_catalog_projects(db, [project_id])
    project = projects.get(project_id)
    if project is None:
        raise CatalogProjectNotFoundError(project_id)

    draft = db.scalar(
        select(ProjectCatalogVersion)
        .where(
            ProjectCatalogVersion.project_id == project_id,
            ProjectCatalogVersion.status == "draft",
        )
        .order_by(ProjectCatalogVersion.version.desc(), ProjectCatalogVersion.id.desc())
        .limit(1)
    )
    if draft is None:
        raise CatalogDraftNotFoundError(project_id)

    linked_ids = [choice.linked_project_id for _, choice in _linked_choices(db, draft.id) if choice.linked_project_id is not None]
    projects = lock_catalog_projects(db, [project_id, *linked_ids])
    project = projects.get(project_id)
    if project is None:
        raise CatalogProjectNotFoundError(project_id)
    # 取得所有锁之后重新读取草稿，避免使用锁前的状态。
    draft = db.scalar(
        select(ProjectCatalogVersion)
        .where(
            ProjectCatalogVersion.project_id == project_id,
            ProjectCatalogVersion.status == "draft",
        )
        .order_by(ProjectCatalogVersion.version.desc(), ProjectCatalogVersion.id.desc())
        .limit(1)
    )
    if draft is None:
        raise CatalogDraftNotFoundError(project_id)

    errors = validate_catalog_version(db, draft.id)
    if errors:
        raise CatalogPublicationError(errors)

    old_published = list(db.scalars(
        select(ProjectCatalogVersion).where(
            ProjectCatalogVersion.project_id == project_id,
            ProjectCatalogVersion.status == "published",
            ProjectCatalogVersion.id != draft.id,
        )
    ))
    highest_published_version = max((version.version for version in old_published), default=0)
    if draft.version <= highest_published_version:
        raise CatalogPublicationError([_error(
            "catalog_version_not_monotonic",
            "version",
            "待发布目录版本必须高于当前已发布版本",
        )])

    for _, choice in _linked_choices(db, draft.id):
        if choice.linked_project_id is None:
            continue
        linked = projects.get(choice.linked_project_id)
        if linked is None:
            continue
        # null 是发布时确认的无目录叶子，而不是稍后追随当前目录的占位符。
        linked_version = _published_version(db, linked)
        choice.pinned_linked_catalog_version_id = linked_version.id if linked_version else None
    db.flush()
    published_at = datetime.now(UTC)
    snapshot_hash = _snapshot_hash(db, draft.id)
    expected_pointer = project.current_published_version_id
    if old_published:
        db.execute(
            update(ProjectCatalogVersion)
            .where(
                ProjectCatalogVersion.project_id == project_id,
                ProjectCatalogVersion.status == "published",
                ProjectCatalogVersion.id != draft.id,
            )
            .values(status="superseded")
            .execution_options(synchronize_session="fetch")
        )
    published_result = db.execute(
        update(ProjectCatalogVersion)
        .where(
            ProjectCatalogVersion.id == draft.id,
            ProjectCatalogVersion.status == "draft",
            ProjectCatalogVersion.version > highest_published_version,
        )
        .values(
            status="published",
            snapshot_hash=snapshot_hash,
            published_at=published_at,
            published_by=staff_id,
        )
        .execution_options(synchronize_session="fetch")
    )
    if published_result.rowcount != 1:
        raise CatalogConcurrencyError("目录草稿状态已变化，请刷新后重试")
    pointer_stmt = update(Project).where(Project.id == project_id)
    if expected_pointer is None:
        pointer_stmt = pointer_stmt.where(Project.current_published_version_id.is_(None))
    else:
        pointer_stmt = pointer_stmt.where(Project.current_published_version_id == expected_pointer)
    pointer_result = db.execute(
        pointer_stmt.values(current_published_version_id=draft.id)
        .execution_options(synchronize_session="fetch")
    )
    if pointer_result.rowcount != 1:
        raise CatalogConcurrencyError("当前发布目录已变化，请刷新后重试")
    db.flush()
    db.refresh(draft)
    return draft


def resolve_published_project_config(db: Session, project_id: int) -> dict:
    """仅沿项目当前发布指针解析目录，不回退读取草稿或最新版本。"""
    project = db.get(Project, project_id)
    if project is None:
        raise CatalogProjectNotFoundError(project_id)
    version = _published_version(db, project)
    if version is None:
        raise CatalogPublishedVersionNotFoundError(project_id)
    verify_published_catalog_hash(db, version)
    return {
        "project_id": project.id,
        "project_code": project.code,
        "catalog_version_id": version.id,
        "version": version.version,
        "snapshot_hash": version.snapshot_hash,
        **_version_content(db, version.id),
    }
