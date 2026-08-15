from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import Addon, PageContent, PriceBook, Product, Project, Store
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
    "title": "到店选项目",
    "subtitle": "按需要，自由搭配",
    "promo_banners": [],
    "tea_options": [
        {"name": "老姜茶", "note": "辛香温润", "description": "姜香温润，适合偏爱暖香口感。"},
        {"name": "陈皮茶", "note": "清香顺口", "description": "陈皮清香，入口顺和，适合日常慢饮。"},
        {"name": "玫瑰茶", "note": "柔和花香", "description": "花香柔和，口感清雅。"},
    ],
    "coupon_prompt": {"title": "登录领取到店礼", "body": "手机号登录后领取，优惠券保存到账号"},
    "brand_story": {"title": "把服务做到身边", "body": "从真实需求出发，用好服务赢得信任。"},
}


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


def _project_to_out(db: Session, p: Project) -> ProjectOut:
    prices = list(db.scalars(select(PriceBook).where(PriceBook.project_id == p.id)))
    return ProjectOut(
        id=p.id, code=p.code, category=p.category, category_mark=p.category_mark,
        name=p.name, duration_min=p.duration_min, summary=p.summary,
        image_url=p.image_url, tags=p.tags, detail_modules=p.detail_modules,
        diy_options=p.diy_options, display_order=p.display_order, price_label=p.price_label,
        prices=[{"price_type": x.price_type, "amount_cents": x.amount_cents} for x in prices],
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
                result[key] = value
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
