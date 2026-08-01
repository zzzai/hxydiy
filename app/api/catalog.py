from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import PriceBook, Project, Store
from app.schemas.catalog import ProjectListResponse, ProjectOut, StoreOut

router = APIRouter(tags=["catalog"])


@router.get("/stores", response_model=list[StoreOut])
def list_stores(db: Session = Depends(get_db)) -> list[Store]:
    return list(db.scalars(select(Store).order_by(Store.id)))


@router.get("/stores/{store_id}", response_model=StoreOut)
def get_store(store_id: int, db: Session = Depends(get_db)) -> Store:
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="门店不存在")
    return store


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
    projects = list(db.scalars(stmt.order_by(Project.id)))

    items: list[ProjectOut] = []
    for p in projects:
        prices = list(
            db.scalars(select(PriceBook).where(PriceBook.project_id == p.id))
        )
        items.append(
            ProjectOut(
                id=p.id, code=p.code, category=p.category, category_mark=p.category_mark,
                name=p.name, duration_min=p.duration_min, summary=p.summary,
                image_url=p.image_url, tags=p.tags, price_label=p.price_label,
                prices=[{"price_type": x.price_type, "amount_cents": x.amount_cents} for x in prices],
            )
        )
    return ProjectListResponse(items=items, total=len(items))
