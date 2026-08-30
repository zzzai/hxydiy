from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from datetime import UTC, datetime
import unicodedata

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.catalog_options import CatalogDomainError, verify_published_catalog_hash
from app.models import Addon, OptionChoicePrice, PageContent, PriceBook, Product, Project, ProjectCatalogVersion, ProjectOptionChoice, ProjectOptionGroup, Store
from app.schemas.catalog import ProjectListResponse, ProjectOut, StoreOut

router = APIRouter(tags=["catalog"])


def _contains_placeholder(value: object) -> bool:
    """Detect the literal question-mark placeholders produced by a bad content import."""
    if isinstance(value, str):
        return "?" in value
    if isinstance(value, list):
        return any(_contains_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_placeholder(item) for item in value.values())
    return False

DEFAULT_PAGE_CONTENT = {
    "title": "到店服务选单",
    "subtitle": "按需要，自由搭配",
    "promo_banners": [],
    "tea_options": [
        {"name": "老姜茶", "note": "辛香温润", "description": "姜香温润，适合偏爱暖香口感。"},
        {"name": "陈皮茶", "note": "清香顺口", "description": "陈皮清香，入口顺和，适合日常慢饮。"},
        {"name": "玫瑰茶", "note": "柔和花香", "description": "花香柔和，口感清雅。"},
    ],
    "coupon_prompt": {"title": "登录领取到店礼", "body": "手机号登录后保存到账号，符合条件后预计自动抵扣"},
    "brand_story": {"title": "把服务做到身边", "body": "从真实需求出发，用好服务赢得信任。"},
}


def _upgrade_legacy_customer_copy(key: str, value: object) -> object:
    if key == "title" and value == "到店选项目":
        return "到店服务选单"
    if key == "coupon_prompt" and isinstance(value, dict):
        upgraded = dict(value)
        if upgraded.get("body") == "手机号登录后领取，优惠券保存到账号":
            upgraded["body"] = "手机号登录后保存到账号，符合条件后预计自动抵扣"
        return upgraded
    return value

_LOCAL_BODY_PARTS = frozenset({"肩颈", "腰臀", "腿部", "腹部", "足部"})


def _catalog_body_part(choice: ProjectOptionChoice, linked_project: Project | None) -> str | None:
    if linked_project is None or linked_project.category != "local-strength":
        return None
    value = "".join(unicodedata.normalize("NFKC", choice.name or "").split())
    return value if value in _LOCAL_BODY_PARTS else None


class AddonOut(BaseModel):
    id: int
    code: str
    name: str
    parent_project_id: int | None = None
    duration_min: int | None = None
    summary: str = ""
    image_url: str = ""
    display_order: int = 0
    chargeable: bool
    independently_sellable: bool
    can_attach_to_parent: bool
    prices: dict[str, int]


class ProductOut(BaseModel):
    id: int
    name: str
    desc: str = ""
    spec: str = ""
    product_type: str
    price_cents: int
    image_url: str = ""

    model_config = {"from_attributes": True}


def _published_option_groups(db: Session, project: Project) -> tuple[int | None, int | None, list[dict]]:
    if project.current_published_version_id is None:
        return None, None, []
    version = db.get(ProjectCatalogVersion, project.current_published_version_id)
    if version is None or version.project_id != project.id or version.status != "published":
        raise HTTPException(status_code=409, detail="当前发布目录指针异常")
    try:
        verify_published_catalog_hash(db, version)
    except CatalogDomainError as exc:
        raise HTTPException(status_code=409, detail="当前发布目录快照校验失败") from exc
    return version.version, version.id, _catalog_option_groups(db, version, datetime.now(UTC), visited=frozenset())


def _catalog_option_groups(
    db: Session,
    version: ProjectCatalogVersion,
    now: datetime,
    *,
    visited: frozenset[int],
) -> list[dict]:
    """返回冻结版本的树；linked choice 内嵌它发布时绑定的目标版本。"""
    if version.id in visited:
        raise HTTPException(status_code=409, detail="引用项目目录快照存在循环")
    try:
        verify_published_catalog_hash(db, version)
    except CatalogDomainError as exc:
        raise HTTPException(status_code=409, detail="引用项目目录快照校验失败") from exc

    groups = []
    next_visited = visited | {version.id}
    for group in db.scalars(
        select(ProjectOptionGroup)
        .where(ProjectOptionGroup.catalog_version_id == version.id)
        .order_by(ProjectOptionGroup.display_order, ProjectOptionGroup.code, ProjectOptionGroup.id)
    ):
        choices = []
        for choice in db.scalars(
            select(ProjectOptionChoice)
            .where(
                ProjectOptionChoice.option_group_id == group.id,
                ProjectOptionChoice.status == "active",
            )
            .order_by(ProjectOptionChoice.display_order, ProjectOptionChoice.code, ProjectOptionChoice.id)
        ):
            linked_project = db.get(Project, choice.linked_project_id) if choice.linked_project_id else None
            linked_catalog_version_id = choice.pinned_linked_catalog_version_id
            linked_catalog_snapshot = None
            if linked_catalog_version_id is not None:
                linked_version = db.get(ProjectCatalogVersion, linked_catalog_version_id)
                if (
                    linked_project is None
                    or linked_version is None
                    or linked_version.project_id != linked_project.id
                    or linked_version.status not in {"published", "superseded"}
                ):
                    raise HTTPException(status_code=409, detail="引用项目目录快照异常")
                linked_catalog_snapshot = {
                    "id": linked_version.id,
                    "version": linked_version.version,
                    "snapshot_hash": linked_version.snapshot_hash,
                    "option_groups": _catalog_option_groups(
                        db,
                        linked_version,
                        now,
                        visited=next_visited,
                    ),
                }
            if choice.choice_type == "preference":
                choice_prices: list[dict] = []
                price_source = "free"
            elif choice.choice_type == "linked_project":
                if linked_project is None:
                    raise HTTPException(status_code=409, detail="引用项目不存在")
                choice_prices = _current_project_prices(db, linked_project.id)
                price_source = "linked_project"
            else:
                choice_prices = _current_option_prices(db, choice.id, now)
                price_source = "option_choice_price"
            choice_out = {
                "id": choice.id,
                "code": choice.code,
                "name": choice.name,
                "description": choice.description,
                "choice_type": choice.choice_type,
                "linked_project_id": choice.linked_project_id,
                "linked_project_code": linked_project.code if linked_project else None,
                "linked_catalog_version_id": linked_catalog_version_id,
                "linked_catalog_snapshot": linked_catalog_snapshot,
                "charge_mode": choice.charge_mode,
                "independently_visible": choice.independently_visible,
                "coupon_eligible": choice.coupon_eligible,
                "annual_gift_eligible": choice.annual_gift_eligible,
                "qualifies_for_foot_bath_bundle": choice.qualifies_for_foot_bath_bundle,
                "display_order": choice.display_order,
                "status": choice.status,
                "price_source": price_source,
                "prices": choice_prices,
            }
            body_part = _catalog_body_part(choice, linked_project)
            if body_part is not None:
                choice_out["body_part"] = body_part
            choices.append(choice_out)
        groups.append({
            "id": group.id,
            "code": group.code,
            "name": group.name,
            "description": group.description,
            "selection_mode": group.selection_mode,
            "required": group.required,
            "min_select": group.min_select,
            "max_select": group.max_select,
            "display_order": group.display_order,
            "choices": choices,
        })
    return groups


def _current_option_prices(db: Session, choice_id: int, now: datetime) -> list[dict]:
    rows = list(db.scalars(
        select(OptionChoicePrice)
        .where(
            OptionChoicePrice.option_choice_id == choice_id,
            OptionChoicePrice.effective_from <= now,
            or_(OptionChoicePrice.effective_to.is_(None), OptionChoicePrice.effective_to > now),
        )
        .order_by(
            OptionChoicePrice.price_type,
            OptionChoicePrice.effective_from.desc(),
            OptionChoicePrice.id.desc(),
        )
    ))
    by_type: dict[str, OptionChoicePrice] = {}
    for row in rows:
        by_type.setdefault(row.price_type, row)
    return [
        {
            "price_type": row.price_type,
            "amount_cents": row.amount_cents,
            "effective_from": row.effective_from.isoformat() if row.effective_from else None,
            "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        }
        for row in by_type.values()
    ]


def _current_project_prices(db: Session, project_id: int) -> list[dict]:
    now = datetime.now(UTC)
    rows = list(db.scalars(
        select(PriceBook)
        .where(
            PriceBook.project_id == project_id,
            or_(PriceBook.effective_to.is_(None), PriceBook.effective_to > now),
        )
        .order_by(PriceBook.price_type, PriceBook.published_at.desc(), PriceBook.id.desc())
    ))
    by_type: dict[str, PriceBook] = {}
    for row in rows:
        by_type.setdefault(row.price_type, row)
    return [
        {"price_type": row.price_type, "amount_cents": row.amount_cents}
        for row in by_type.values()
    ]


def _project_to_out(db: Session, p: Project) -> ProjectOut:
    catalog_version, catalog_version_id, option_groups = _published_option_groups(db, p)
    return ProjectOut(
        id=p.id, code=p.code, category=p.category, category_mark=p.category_mark,
        name=p.name, duration_min=p.duration_min, summary=p.summary,
        image_url=p.image_url, tags=p.tags, detail_modules=p.detail_modules,
        diy_options=p.diy_options, display_order=p.display_order, price_label=p.price_label,
        prices=_current_project_prices(db, p.id),
        catalog_version=catalog_version, catalog_version_id=catalog_version_id, option_groups=option_groups,
    )


@router.get("/stores", response_model=list[StoreOut])
def list_stores(db: Session = Depends(get_db)) -> list[Store]:
    return list(db.scalars(select(Store).order_by(Store.id)))


@router.get("/stores/{store_id}", response_model=StoreOut)
def get_store(store_id: int, db: Session = Depends(get_db)) -> Store:
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="门店不存在")
    return store


@router.get("/stores/{store_id}/page-content")
def get_page_content(store_id: int, page_key: str = Query("diy-home"), db: Session = Depends(get_db)):
    """顾客端页面内容；草稿不可见，缺少配置时返回稳定默认内容。"""
    if not db.get(Store, store_id):
        raise HTTPException(status_code=404, detail="门店不存在")
    content = db.scalar(select(PageContent).where(
        PageContent.store_id == store_id,
        PageContent.page_key == page_key,
        PageContent.published.is_(True),
    ))
    result = {**DEFAULT_PAGE_CONTENT, "store_id": store_id, "page_key": page_key, "published": True}
    if content:
        for key in DEFAULT_PAGE_CONTENT:
            value = getattr(content, key)
            if value not in (None, "", [], {}) and not _contains_placeholder(value):
                result[key] = _upgrade_legacy_customer_copy(key, value)
    return result


@router.get("/projects", response_model=ProjectListResponse)
def list_projects(
    store_id: int = Query(..., description="门店 ID"),
    category: str | None = None,
    db: Session = Depends(get_db),
) -> ProjectListResponse:
    """已发布项目列表（publication_status=published），价格来自 price_book。"""
    stmt = select(Project).where(
        Project.store_id == store_id, Project.publication_status == "published"
    )
    if category:
        stmt = stmt.where(Project.category == category)
    projects = list(db.scalars(stmt.order_by(Project.display_order, Project.id)))
    items = [_project_to_out(db, p) for p in projects]
    return ProjectListResponse(items=items, total=len(items))


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectOut:
    """项目详情（仅 published）。"""
    project = db.get(Project, project_id)
    if not project or project.publication_status != "published":
        raise HTTPException(status_code=404, detail="项目不存在或未发布")
    return _project_to_out(db, project)


@router.get("/addons", response_model=list[AddonOut])
def list_addons(
    store_id: int = Query(..., description="门店 ID"),
    parent_project_id: int | None = Query(None, description="主项目 ID"),
    sale_mode: str | None = Query(None, pattern="^(attach|independent)$"),
    db: Session = Depends(get_db),
) -> list[AddonOut]:
    """顾客端只读已发布加项；可按主项或销售方式筛选。"""
    stmt = select(Addon).where(
        Addon.store_id == store_id, Addon.publication_status == "published"
    )
    if parent_project_id is not None:
        stmt = stmt.where(Addon.parent_project_id == parent_project_id)
    if sale_mode == "attach":
        stmt = stmt.where(Addon.can_attach_to_parent.is_(True))
    elif sale_mode == "independent":
        stmt = stmt.where(Addon.independently_sellable.is_(True))
    addons = list(db.scalars(stmt.order_by(Addon.display_order, Addon.id)))
    return [
        AddonOut(
            id=addon.id,
            code=addon.code,
            name=addon.name,
            parent_project_id=addon.parent_project_id,
            duration_min=addon.duration_min,
            summary=addon.summary,
            image_url=addon.image_url,
            display_order=addon.display_order,
            chargeable=addon.chargeable,
            independently_sellable=addon.independently_sellable,
            can_attach_to_parent=addon.can_attach_to_parent,
            prices={
                "store": int(addon.store_price_cents if addon.store_price_cents is not None else addon.price_cents),
                "member": int(
                    addon.member_price_cents
                    if addon.member_price_enabled and addon.member_price_cents is not None
                    else addon.store_price_cents if addon.store_price_cents is not None else addon.price_cents
                ),
            },
        )
        for addon in addons
    ]


@router.get("/products", response_model=list[ProductOut])
def list_products(
    store_id: int = Query(..., description="门店 ID"),
    product_type: str | None = None,
    db: Session = Depends(get_db),
) -> list[Product]:
    """商城商品（仅 published，到店自提）。"""
    stmt = select(Product).where(
        Product.store_id == store_id, Product.publication_status == "published"
    )
    if product_type:
        stmt = stmt.where(Product.product_type == product_type)
    return list(db.scalars(stmt.order_by(Product.id)))
