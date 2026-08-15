"""目录草稿校验、发布与已发布配置解析。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    OptionChoicePrice,
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


class CatalogDraftNotFoundError(CatalogDomainError):
    def __init__(self, project_id: int):
        super().__init__(f"项目没有可发布的目录草稿: {project_id}")
        self.project_id = project_id


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
    seen_linked_projects: set[int] = set()

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

            if choice.choice_type == "preference" and choice.charge_mode != "free":
                errors.append(_error(
                    "preference_must_be_free",
                    f"{choice_path}.charge_mode",
                    "偏好选项必须免费",
                ))
            if choice.choice_type == "linked_project" and choice.charge_mode != "inherit_linked_price":
                errors.append(_error(
                    "linked_project_must_inherit_linked_price",
                    f"{choice_path}.charge_mode",
                    "项目引用选项必须继承引用项目价格",
                ))
            if choice.choice_type == "dedicated_charge":
                if choice.charge_mode != "custom_price":
                    errors.append(_error(
                        "dedicated_charge_must_use_custom_price",
                        f"{choice_path}.charge_mode",
                        "独立收费选项必须使用自定义价格",
                    ))
                if choice.linked_project_id is not None:
                    errors.append(_error(
                        "dedicated_charge_cannot_link_project",
                        f"{choice_path}.linked_project_id",
                        "独立收费选项不得指向引用项目",
                    ))

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
            if linked.id in seen_linked_projects:
                errors.append(_error(
                    "duplicate_linked_project",
                    f"{choice_path}.linked_project_id",
                    "缺少明确部位时，同一主项目不得重复引用同一项目",
                ))
            seen_linked_projects.add(linked.id)
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
            if _published_version(db, linked) is None:
                errors.append(_error(
                    "linked_project_catalog_unpublished",
                    f"{choice_path}.linked_project_id",
                    "引用项目必须具有当前已发布目录版本",
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
    prices = list(db.scalars(
        select(OptionChoicePrice)
        .where(OptionChoicePrice.option_choice_id == choice.id)
        .order_by(
            OptionChoicePrice.price_type,
            OptionChoicePrice.effective_from,
            OptionChoicePrice.id,
        )
    ))
    linked_project = db.get(Project, choice.linked_project_id) if choice.linked_project_id else None
    return {
        "code": choice.code,
        "name": choice.name,
        "description": choice.description,
        "choice_type": choice.choice_type,
        "linked_project_id": choice.linked_project_id,
        "linked_project_code": linked_project.code if linked_project else None,
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
    project = db.scalar(
        select(Project).where(Project.id == project_id).with_for_update()
    )
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
    published_at = datetime.now(UTC)
    draft.snapshot_hash = _snapshot_hash(db, draft.id)
    for old_version in old_published:
        old_version.status = "superseded"
    draft.status = "published"
    draft.published_at = published_at
    draft.published_by = staff_id
    project.current_published_version_id = draft.id
    db.flush()
    return draft


def resolve_published_project_config(db: Session, project_id: int) -> dict:
    """仅沿项目当前发布指针解析目录，不回退读取草稿或最新版本。"""
    project = db.get(Project, project_id)
    if project is None:
        raise CatalogProjectNotFoundError(project_id)
    version = _published_version(db, project)
    if version is None:
        raise CatalogPublishedVersionNotFoundError(project_id)
    return {
        "project_id": project.id,
        "project_code": project.code,
        "catalog_version_id": version.id,
        "version": version.version,
        "snapshot_hash": version.snapshot_hash,
        **_version_content(db, version.id),
    }
