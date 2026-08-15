from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.admin import _current_staff
from app.api.admin_v2 import _audit, _require_admin, _staff_store_id
from app.db.session import get_db
from app.domain.catalog_options import (
    CatalogDraftNotFoundError,
    CatalogProjectNotFoundError,
    CatalogPublicationError,
    copy_catalog_version_graph,
    publish_catalog_version,
    validate_catalog_version,
)
from app.domain.membership_pricing import (
    PriceContext,
    confirmed_price_for_line,
    price_book_snapshot,
    resolve_option_charge,
)
from app.models import (
    OptionChoicePrice,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    Staff,
)

router = APIRouter(prefix="/admin/v2", tags=["admin-catalog"])


SelectionMode = Literal["single", "multiple"]
ChoiceType = Literal["preference", "linked_project", "dedicated_charge"]
ChargeMode = Literal["free", "inherit_linked_price", "custom_price"]
ChoiceStatus = Literal["active", "inactive"]
PriceType = Literal["store", "group", "member"]


class _CleanTextModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("code", "name", check_fields=False)
    @classmethod
    def _strip_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class OptionChoicePriceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_type: PriceType
    amount_cents: StrictInt = Field(ge=0)
    effective_from: datetime = Field(default_factory=lambda: datetime.now(UTC))
    effective_to: datetime | None = None

    @field_validator("effective_from", "effective_to")
    @classmethod
    def _datetime_must_be_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _effective_to_must_be_after_from(self):
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self


class OptionGroupIn(_CleanTextModel):
    code: StrictStr = Field(min_length=1, max_length=32)
    name: StrictStr = Field(min_length=1, max_length=64)
    description: StrictStr = Field(default="", max_length=512)
    selection_mode: SelectionMode = "single"
    required: StrictBool = False
    min_select: StrictInt = Field(default=0, ge=0)
    max_select: StrictInt = Field(default=1, ge=0)
    display_order: StrictInt = Field(default=0, ge=0)


class OptionGroupPatch(_CleanTextModel):
    code: StrictStr | None = Field(default=None, min_length=1, max_length=32)
    name: StrictStr | None = Field(default=None, min_length=1, max_length=64)
    description: StrictStr | None = Field(default=None, max_length=512)
    selection_mode: SelectionMode | None = None
    required: StrictBool | None = None
    min_select: StrictInt | None = Field(default=None, ge=0)
    max_select: StrictInt | None = Field(default=None, ge=0)
    display_order: StrictInt | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _reject_null_non_nullable_fields(cls, data):
        if isinstance(data, dict):
            for key, value in data.items():
                if value is None:
                    raise ValueError(f"{key} must not be null")
        return data


class OptionChoiceIn(_CleanTextModel):
    code: StrictStr = Field(min_length=1, max_length=32)
    name: StrictStr = Field(min_length=1, max_length=64)
    description: StrictStr = Field(default="", max_length=512)
    choice_type: ChoiceType
    charge_mode: ChargeMode
    linked_project_id: StrictInt | None = Field(default=None, gt=0)
    independently_visible: StrictBool = True
    coupon_eligible: StrictBool = False
    annual_gift_eligible: StrictBool = False
    qualifies_for_foot_bath_bundle: StrictBool = False
    status: ChoiceStatus = "active"
    display_order: StrictInt = Field(default=0, ge=0)
    prices: list[OptionChoicePriceIn] = Field(default_factory=list)


class OptionChoicePatch(_CleanTextModel):
    code: StrictStr | None = Field(default=None, min_length=1, max_length=32)
    name: StrictStr | None = Field(default=None, min_length=1, max_length=64)
    description: StrictStr | None = Field(default=None, max_length=512)
    choice_type: ChoiceType | None = None
    charge_mode: ChargeMode | None = None
    linked_project_id: StrictInt | None = Field(default=None, gt=0)
    independently_visible: StrictBool | None = None
    coupon_eligible: StrictBool | None = None
    annual_gift_eligible: StrictBool | None = None
    qualifies_for_foot_bath_bundle: StrictBool | None = None
    status: ChoiceStatus | None = None
    display_order: StrictInt | None = Field(default=None, ge=0)
    prices: list[OptionChoicePriceIn] | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_null_non_nullable_fields(cls, data):
        if isinstance(data, dict):
            nullable = {"linked_project_id"}
            for key, value in data.items():
                if key not in nullable and value is None:
                    raise ValueError(f"{key} must not be null")
        return data


class PricePreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice_ids: list[StrictInt] = Field(default_factory=list)
    is_member: StrictBool = False
    confirmed_at: datetime
    store_timezone: StrictStr = Field(min_length=1)

    @field_validator("confirmed_at")
    @classmethod
    def _confirmed_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("confirmed_at must be timezone-aware")
        return value

    @field_validator("choice_ids")
    @classmethod
    def _choice_ids_must_be_unique_positive(cls, value: list[int]) -> list[int]:
        if any(choice_id <= 0 for choice_id in value):
            raise ValueError("choice_ids must be positive")
        if len(value) != len(set(value)):
            raise ValueError("choice_ids must be unique")
        return value


def _validation_error_out(error) -> dict:
    return {"code": error.code, "path": error.path, "message": error.message}


def _version_meta(version: ProjectCatalogVersion | None) -> dict | None:
    if version is None:
        return None
    return {"id": version.id, "version": version.version, "status": version.status}


def _price_out(price: OptionChoicePrice) -> dict:
    return {
        "id": price.id,
        "price_type": price.price_type,
        "amount_cents": price.amount_cents,
        "effective_from": price.effective_from.isoformat() if price.effective_from else None,
        "effective_to": price.effective_to.isoformat() if price.effective_to else None,
    }


def _choice_out(db: Session, choice: ProjectOptionChoice) -> dict:
    prices = list(db.scalars(
        select(OptionChoicePrice)
        .where(OptionChoicePrice.option_choice_id == choice.id)
        .order_by(OptionChoicePrice.price_type, OptionChoicePrice.effective_from, OptionChoicePrice.id)
    ))
    return {
        "id": choice.id,
        "option_group_id": choice.option_group_id,
        "code": choice.code,
        "name": choice.name,
        "description": choice.description,
        "choice_type": choice.choice_type,
        "linked_project_id": choice.linked_project_id,
        "charge_mode": choice.charge_mode,
        "independently_visible": choice.independently_visible,
        "coupon_eligible": choice.coupon_eligible,
        "annual_gift_eligible": choice.annual_gift_eligible,
        "qualifies_for_foot_bath_bundle": choice.qualifies_for_foot_bath_bundle,
        "display_order": choice.display_order,
        "status": choice.status,
        "prices": [_price_out(price) for price in prices],
    }


def _group_out(db: Session, group: ProjectOptionGroup) -> dict:
    choices = list(db.scalars(
        select(ProjectOptionChoice)
        .where(ProjectOptionChoice.option_group_id == group.id)
        .order_by(ProjectOptionChoice.display_order, ProjectOptionChoice.code, ProjectOptionChoice.id)
    ))
    return {
        "id": group.id,
        "catalog_version_id": group.catalog_version_id,
        "code": group.code,
        "name": group.name,
        "description": group.description,
        "selection_mode": group.selection_mode,
        "required": group.required,
        "min_select": group.min_select,
        "max_select": group.max_select,
        "display_order": group.display_order,
        "choices": [_choice_out(db, choice) for choice in choices],
    }


def _project_for_staff(db: Session, project_id: int, staff: Staff, *, lock: bool = False) -> Project:
    stmt = select(Project).where(Project.id == project_id)
    if lock:
        stmt = stmt.with_for_update()
    project = db.scalar(stmt)
    if project is None or project.store_id != _staff_store_id(staff):
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def _latest_version(db: Session, project_id: int, status: str | None = None) -> ProjectCatalogVersion | None:
    stmt = select(ProjectCatalogVersion).where(ProjectCatalogVersion.project_id == project_id)
    if status is not None:
        stmt = stmt.where(ProjectCatalogVersion.status == status)
    return db.scalar(stmt.order_by(ProjectCatalogVersion.version.desc(), ProjectCatalogVersion.id.desc()).limit(1))


def _read_version(db: Session, project: Project) -> ProjectCatalogVersion | None:
    draft = _latest_version(db, project.id, "draft")
    if draft is not None:
        return draft
    if project.current_published_version_id is None:
        return None
    version = db.get(ProjectCatalogVersion, project.current_published_version_id)
    if version is None or version.project_id != project.id or version.status != "published":
        raise HTTPException(status_code=409, detail="当前发布目录指针异常")
    return version


def _next_version_number(db: Session, project_id: int) -> int:
    current = db.scalar(
        select(func.max(ProjectCatalogVersion.version)).where(ProjectCatalogVersion.project_id == project_id)
    )
    return int(current or 0) + 1


def _create_draft_from_published(db: Session, project: Project) -> ProjectCatalogVersion:
    draft = ProjectCatalogVersion(
        project_id=project.id,
        version=_next_version_number(db, project.id),
        status="draft",
    )
    db.add(draft)
    _flush_or_conflict(db)
    if project.current_published_version_id is None:
        return draft
    published = db.get(ProjectCatalogVersion, project.current_published_version_id)
    if published is None or published.project_id != project.id or published.status != "published":
        raise HTTPException(status_code=409, detail="当前发布目录指针异常")
    copy_catalog_version_graph(db, published.id, draft.id)
    return draft


def _editable_draft(db: Session, project_id: int, staff: Staff) -> tuple[Project, ProjectCatalogVersion]:
    project = _project_for_staff(db, project_id, staff, lock=True)
    if project.publication_status == "archived":
        raise HTTPException(status_code=409, detail="归档项目不可编辑目录")
    draft = _latest_version(db, project.id, "draft")
    if draft is not None:
        return project, draft
    return project, _create_draft_from_published(db, project)


def _group_for_project(db: Session, project_id: int, group_id: int, staff: Staff) -> tuple[Project, ProjectCatalogVersion, ProjectOptionGroup]:
    group = db.get(ProjectOptionGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="选项组不存在")
    version = db.get(ProjectCatalogVersion, group.catalog_version_id)
    project = db.get(Project, version.project_id) if version else None
    if version is None or project is None or project.id != project_id or project.store_id != _staff_store_id(staff):
        raise HTTPException(status_code=404, detail="选项组不存在")
    return project, version, group


def _draft_group_for_project(db: Session, project_id: int, group_id: int, staff: Staff) -> tuple[Project, ProjectCatalogVersion, ProjectOptionGroup]:
    project, version, group = _group_for_project(db, project_id, group_id, staff)
    if version.status != "draft":
        raise HTTPException(status_code=409, detail="已发布或已废弃目录不可修改")
    latest_draft = _latest_version(db, project.id, "draft")
    if latest_draft is None or latest_draft.id != version.id:
        raise HTTPException(status_code=409, detail="只能修改最新目录草稿")
    return project, version, group


def _choice_for_project(
    db: Session,
    project_id: int,
    group_id: int,
    choice_id: int,
    staff: Staff,
) -> tuple[Project, ProjectCatalogVersion, ProjectOptionGroup, ProjectOptionChoice]:
    project, version, group = _group_for_project(db, project_id, group_id, staff)
    choice = db.get(ProjectOptionChoice, choice_id)
    if choice is None or choice.option_group_id != group.id:
        raise HTTPException(status_code=404, detail="选项不存在")
    return project, version, group, choice


def _draft_choice_for_project(
    db: Session,
    project_id: int,
    group_id: int,
    choice_id: int,
    staff: Staff,
) -> tuple[Project, ProjectCatalogVersion, ProjectOptionGroup, ProjectOptionChoice]:
    project, version, group, choice = _choice_for_project(db, project_id, group_id, choice_id, staff)
    if version.status != "draft":
        raise HTTPException(status_code=409, detail="已发布或已废弃目录不可修改")
    latest_draft = _latest_version(db, project.id, "draft")
    if latest_draft is None or latest_draft.id != version.id:
        raise HTTPException(status_code=409, detail="只能修改最新目录草稿")
    return project, version, group, choice


def _apply_prices(db: Session, choice_id: int, prices: list[OptionChoicePriceIn]) -> None:
    db.execute(delete(OptionChoicePrice).where(OptionChoicePrice.option_choice_id == choice_id))
    for price in prices:
        db.add(OptionChoicePrice(
            option_choice_id=choice_id,
            price_type=price.price_type,
            amount_cents=price.amount_cents,
            effective_from=price.effective_from,
            effective_to=price.effective_to,
        ))


def _require_linked_project_allowed_for_write(
    db: Session,
    project: Project,
    linked_project_id: int | None,
    *,
    choice_type: str | None = None,
    charge_mode: str | None = None,
) -> None:
    requires_linked_project = choice_type == "linked_project" or charge_mode == "inherit_linked_price"
    if linked_project_id is None:
        if requires_linked_project:
            raise HTTPException(status_code=422, detail={"code": "linked_project_required", "path": "linked_project_id", "message": "项目引用选项必须指定引用项目"})
        return
    linked = db.get(Project, linked_project_id)
    if linked is None or linked.store_id != project.store_id:
        raise HTTPException(status_code=404, detail="引用项目不存在")
    if not requires_linked_project:
        return
    if linked.publication_status != "published":
        raise HTTPException(status_code=422, detail={"code": "linked_project_unpublished", "path": "linked_project_id", "message": "引用项目必须已发布"})
    if linked.current_published_version_id is None:
        raise HTTPException(status_code=422, detail={"code": "linked_project_catalog_unpublished", "path": "linked_project_id", "message": "引用项目必须具有当前已发布目录版本"})
    linked_version = db.get(ProjectCatalogVersion, linked.current_published_version_id)
    if linked_version is None or linked_version.project_id != linked.id or linked_version.status != "published":
        raise HTTPException(status_code=422, detail={"code": "linked_project_catalog_unpublished", "path": "linked_project_id", "message": "引用项目必须具有当前已发布目录版本"})


def _require_linked_project_allowed_for_preview(
    db: Session,
    project: Project,
    choice: ProjectOptionChoice,
) -> None:
    if choice.choice_type != "linked_project" and choice.charge_mode != "inherit_linked_price":
        return
    if choice.linked_project_id is None:
        raise HTTPException(status_code=422, detail={"code": "linked_project_required", "path": f"choices.{choice.code}.linked_project_id", "message": "项目引用选项必须指定引用项目"})
    linked = db.get(Project, choice.linked_project_id)
    if linked is None or linked.store_id != project.store_id:
        raise HTTPException(status_code=404, detail="引用项目不存在")
    if linked.publication_status != "published":
        raise HTTPException(status_code=422, detail={"code": "linked_project_unpublished", "path": f"choices.{choice.code}.linked_project_id", "message": "引用项目必须已发布"})
    if linked.current_published_version_id is None:
        raise HTTPException(status_code=422, detail={"code": "linked_project_catalog_unpublished", "path": f"choices.{choice.code}.linked_project_id", "message": "引用项目必须具有当前已发布目录版本"})
    linked_version = db.get(ProjectCatalogVersion, linked.current_published_version_id)
    if linked_version is None or linked_version.project_id != linked.id or linked_version.status != "published":
        raise HTTPException(status_code=422, detail={"code": "linked_project_catalog_unpublished", "path": f"choices.{choice.code}.linked_project_id", "message": "引用项目必须具有当前已发布目录版本"})


def _selection_error(code: str, path: str, message: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": code, "path": path, "message": message})


def _validate_preview_selection_counts(
    db: Session,
    version: ProjectCatalogVersion,
    selected_choice_ids: list[int],
) -> None:
    selected = set(selected_choice_ids)
    version_choice_ids = set(db.scalars(
        select(ProjectOptionChoice.id)
        .join(ProjectOptionGroup, ProjectOptionGroup.id == ProjectOptionChoice.option_group_id)
        .where(ProjectOptionGroup.catalog_version_id == version.id)
    ))
    if not selected.issubset(version_choice_ids):
        raise HTTPException(status_code=404, detail="选项不存在")
    groups = list(db.scalars(
        select(ProjectOptionGroup)
        .where(ProjectOptionGroup.catalog_version_id == version.id)
        .order_by(ProjectOptionGroup.display_order, ProjectOptionGroup.code, ProjectOptionGroup.id)
    ))
    for group in groups:
        active_choice_ids = set(db.scalars(
            select(ProjectOptionChoice.id).where(
                ProjectOptionChoice.option_group_id == group.id,
                ProjectOptionChoice.status == "active",
            )
        ))
        count = len(selected.intersection(active_choice_ids))
        path = f"groups.{group.code}"
        if group.required and count == 0:
            raise _selection_error("required_group_missing", path, "必选组至少选择一项")
        if count == 0:
            continue
        if group.selection_mode == "single" and count > 1:
            raise _selection_error("single_group_multiple_selected", path, "单选组只能选择一项")
        if count < group.min_select:
            raise _selection_error("min_select_not_met", path, "选择数量少于最少选择数")
        if count > group.max_select:
            raise _selection_error("max_select_exceeded", path, "选择数量超过最多选择数")


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="目录编码或价格生效时间重复") from exc


def _flush_or_conflict(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="目录编码或价格生效时间重复") from exc


@router.get("/projects/{project_id}/option-groups")
def list_option_groups(
    project_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    project = _project_for_staff(db, project_id, staff)
    version = _read_version(db, project)
    groups = []
    if version is not None:
        groups = list(db.scalars(
            select(ProjectOptionGroup)
            .where(ProjectOptionGroup.catalog_version_id == version.id)
            .order_by(ProjectOptionGroup.display_order, ProjectOptionGroup.code, ProjectOptionGroup.id)
        ))
    return {"project_id": project.id, "catalog_version": _version_meta(version), "items": [_group_out(db, group) for group in groups]}


@router.post("/projects/{project_id}/option-groups")
def create_option_group(
    project_id: int,
    body: OptionGroupIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    project, version = _editable_draft(db, project_id, staff)
    group = ProjectOptionGroup(catalog_version_id=version.id, **body.model_dump())
    db.add(group)
    _flush_or_conflict(db)
    _audit(db, staff.name, "create_option_group", "project_option_group", str(group.id), {"project_id": project.id, "catalog_version_id": version.id})
    _commit_or_conflict(db)
    db.refresh(group)
    return {**_group_out(db, group), "catalog_version": _version_meta(version)}


@router.patch("/projects/{project_id}/option-groups/{group_id}")
def patch_option_group(
    project_id: int,
    group_id: int,
    body: OptionGroupPatch,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    project, version, group = _draft_group_for_project(db, project_id, group_id, staff)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(group, key, value)
    _audit(db, staff.name, "update_option_group", "project_option_group", str(group.id), {"project_id": project.id, "catalog_version_id": version.id})
    _commit_or_conflict(db)
    db.refresh(group)
    return {**_group_out(db, group), "catalog_version": _version_meta(version)}


@router.delete("/projects/{project_id}/option-groups/{group_id}")
def delete_option_group(
    project_id: int,
    group_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    project, version, group = _draft_group_for_project(db, project_id, group_id, staff)
    choice_ids = list(db.scalars(select(ProjectOptionChoice.id).where(ProjectOptionChoice.option_group_id == group.id)))
    if choice_ids:
        db.execute(delete(OptionChoicePrice).where(OptionChoicePrice.option_choice_id.in_(choice_ids)))
        db.execute(delete(ProjectOptionChoice).where(ProjectOptionChoice.id.in_(choice_ids)))
    db.delete(group)
    _audit(db, staff.name, "delete_option_group", "project_option_group", str(group.id), {"project_id": project.id, "catalog_version_id": version.id})
    _commit_or_conflict(db)
    return {"ok": True}


@router.post("/projects/{project_id}/option-groups/{group_id}/choices")
def create_option_choice(
    project_id: int,
    group_id: int,
    body: OptionChoiceIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    project, version, group = _draft_group_for_project(db, project_id, group_id, staff)
    _require_linked_project_allowed_for_write(
        db,
        project,
        body.linked_project_id,
        choice_type=body.choice_type,
        charge_mode=body.charge_mode,
    )
    data = body.model_dump(exclude={"prices"})
    choice = ProjectOptionChoice(option_group_id=group.id, **data)
    db.add(choice)
    _flush_or_conflict(db)
    _apply_prices(db, choice.id, body.prices)
    _audit(db, staff.name, "create_option_choice", "project_option_choice", str(choice.id), {"project_id": project.id, "catalog_version_id": version.id, "group_id": group.id})
    _commit_or_conflict(db)
    db.refresh(choice)
    return {**_choice_out(db, choice), "catalog_version": _version_meta(version)}


@router.patch("/projects/{project_id}/option-groups/{group_id}/choices/{choice_id}")
def patch_option_choice(
    project_id: int,
    group_id: int,
    choice_id: int,
    body: OptionChoicePatch,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    project, version, group, choice = _draft_choice_for_project(db, project_id, group_id, choice_id, staff)
    data = body.model_dump(exclude_unset=True, exclude={"prices"})
    prices = body.prices if "prices" in body.model_fields_set else None
    final_choice_type = data.get("choice_type", choice.choice_type)
    final_charge_mode = data.get("charge_mode", choice.charge_mode)
    final_linked_project_id = data.get("linked_project_id", choice.linked_project_id)
    _require_linked_project_allowed_for_write(
        db,
        project,
        final_linked_project_id,
        choice_type=final_choice_type,
        charge_mode=final_charge_mode,
    )
    for key, value in data.items():
        setattr(choice, key, value)
    if prices is not None:
        _apply_prices(db, choice.id, prices)
    _audit(db, staff.name, "update_option_choice", "project_option_choice", str(choice.id), {"project_id": project.id, "catalog_version_id": version.id, "group_id": group.id})
    _commit_or_conflict(db)
    db.refresh(choice)
    return {**_choice_out(db, choice), "catalog_version": _version_meta(version)}


@router.delete("/projects/{project_id}/option-groups/{group_id}/choices/{choice_id}")
def delete_option_choice(
    project_id: int,
    group_id: int,
    choice_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    project, version, group, choice = _draft_choice_for_project(db, project_id, group_id, choice_id, staff)
    db.execute(delete(OptionChoicePrice).where(OptionChoicePrice.option_choice_id == choice.id))
    db.delete(choice)
    _audit(db, staff.name, "delete_option_choice", "project_option_choice", str(choice.id), {"project_id": project.id, "catalog_version_id": version.id, "group_id": group.id})
    _commit_or_conflict(db)
    return {"ok": True}


@router.get("/projects/{project_id}/validate-publication")
@router.post("/projects/{project_id}/validate-publication")
def validate_publication(
    project_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    project = _project_for_staff(db, project_id, staff)
    draft = _latest_version(db, project.id, "draft")
    if draft is None:
        return {"project_id": project.id, "catalog_version": None, "valid": False, "errors": [{"code": "draft_not_found", "path": "version", "message": "项目没有可发布的目录草稿"}]}
    errors = validate_catalog_version(db, draft.id)
    return {"project_id": project.id, "catalog_version": _version_meta(draft), "valid": not errors, "errors": [_validation_error_out(error) for error in errors]}


@router.post("/projects/{project_id}/publish")
def publish_project_catalog(
    project_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    project = _project_for_staff(db, project_id, staff, lock=True)
    if project.publication_status == "archived":
        raise HTTPException(status_code=409, detail="归档项目不可发布目录")
    try:
        published = publish_catalog_version(db, project.id, staff.id)
    except CatalogProjectNotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在")
    except CatalogDraftNotFoundError:
        return JSONResponse(
            status_code=409,
            content={"errors": [{"code": "draft_not_found", "path": "version", "message": "项目没有可发布的目录草稿"}]},
        )
    except CatalogPublicationError as exc:
        return JSONResponse(status_code=409, content={"errors": [_validation_error_out(error) for error in exc.errors]})
    project.publication_status = "published"
    _audit(db, staff.name, "publish_catalog_version", "project", str(project.id), {"catalog_version_id": published.id, "version": published.version})
    _commit_or_conflict(db)
    return {
        "id": published.id,
        "project_id": project.id,
        "version": published.version,
        "status": published.status,
        "snapshot_hash": published.snapshot_hash,
        "published_at": published.published_at.isoformat() if published.published_at else None,
        "published_by": published.published_by,
    }


@router.get("/projects/{project_id}/versions")
def list_project_versions(
    project_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    project = _project_for_staff(db, project_id, staff)
    versions = list(db.scalars(
        select(ProjectCatalogVersion)
        .where(ProjectCatalogVersion.project_id == project.id)
        .order_by(ProjectCatalogVersion.version.desc(), ProjectCatalogVersion.id.desc())
    ))
    return {
        "project_id": project.id,
        "items": [
            {
                "id": version.id,
                "version": version.version,
                "status": version.status,
                "hash": version.snapshot_hash,
                "published_at": version.published_at.isoformat() if version.published_at else None,
                "published_by": version.published_by,
            }
            for version in versions
        ],
    }


def _working_version_for_preview(db: Session, project: Project) -> ProjectCatalogVersion:
    version = _read_version(db, project)
    if version is None:
        raise HTTPException(status_code=409, detail="项目没有可预览的目录版本")
    return version


@router.post("/projects/{project_id}/price-preview")
def preview_project_price(
    project_id: int,
    body: PricePreviewIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    project = _project_for_staff(db, project_id, staff)
    version = _working_version_for_preview(db, project)
    _validate_preview_selection_counts(db, version, body.choice_ids)
    try:
        project_snapshot = price_book_snapshot(db, project.id)
        confirmed = confirmed_price_for_line(
            project_snapshot.prices,
            body.is_member,
            body.confirmed_at,
            body.store_timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    lines = [{
        "line_type": "project",
        "project_id": project.id,
        "amount_cents": confirmed.amount_cents,
        "basis": confirmed.basis,
        "source": "price_book",
    }]
    for choice_id in body.choice_ids:
        row = db.execute(
            select(ProjectOptionChoice, ProjectOptionGroup)
            .join(ProjectOptionGroup, ProjectOptionGroup.id == ProjectOptionChoice.option_group_id)
            .where(
                ProjectOptionChoice.id == choice_id,
                ProjectOptionGroup.catalog_version_id == version.id,
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="选项不存在")
        choice, group = row
        if choice.status != "active":
            raise HTTPException(status_code=400, detail="不可预览停用选项")
        _require_linked_project_allowed_for_preview(db, project, choice)
        try:
            charge = resolve_option_charge(db, choice.id, PriceContext(
                is_member=body.is_member,
                confirmed_at=body.confirmed_at,
                store_timezone=body.store_timezone,
            ))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        lines.append({
            "line_type": "option_choice",
            "group_id": group.id,
            "choice_id": choice.id,
            "amount_cents": charge.amount_cents,
            "basis": charge.basis,
            "source": charge.price_source,
            "source_ref": charge.source_ref,
        })
    return {
        "project_id": project.id,
        "catalog_version": _version_meta(version),
        "lines": lines,
        "total_cents": sum(line["amount_cents"] for line in lines),
    }
