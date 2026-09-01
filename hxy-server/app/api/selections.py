"""顾客到店服务选单 API，不创建订单，不涉及支付。"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.automatic_coupon import select_automatic_coupon
from app.domain.occupancy import refresh_hold
from app.domain.membership_pricing import PriceContext
from app.domain.selection_pricing import calculate_selection_pricing, price_type_for_member
from app.domain.selection_options import (
    CatalogSelectionError,
    merge_linked_service_units,
    resolve_catalog_selection,
)
from app.models import Addon, CouponTemplate, PositionOccupancy, Project, ProjectCatalogVersion, SelectionChangeRequest, SelectionRevision, SelectionSession, ServiceFeedback, Store, User
from app.schemas.selection import (
    MySelectionSessionsOut,
    SelectionCreateIn,
    SelectionCreateOut,
    SelectionItemIn,
    SelectionSaveIn,
    SelectionSessionOut,
)

router = APIRouter(prefix="/selection-sessions", tags=["selection-sessions"])
SESSION_TTL_HOURS = 12
SYNTHETIC_SERVICE_IDS = {"local-strength"}
DETAIL_ONLY_PROJECT_CATEGORIES = {"kit"}
# 历史误分类仍为套盒的稳定编码，与 category 判定取并集。
DETAIL_ONLY_PROJECT_CODES = {"hxy-taoke-60"}
SYNTHETIC_PROJECTS = {
    "tea": {"name": "到店茶饮", "category": "tea"},
    "local-strength": {"name": "局部加强", "category": "local-strength"},
}


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    tags: list[str] = Field(default_factory=list, max_length=6)
    note: str = Field(default="", max_length=1000)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _current_user_id(authorization: str | None) -> int | None:
    """从 Bearer token 取用户 ID；未登录返回 None。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    from app.core.security import decode_token
    payload = decode_token(authorization[7:])
    return int(payload["sub"]) if payload else None


def _is_anonymous_customer(user: User | None) -> bool:
    return bool(user and user.openid.startswith("anon_"))


def _get_session(db: Session, session_id: str, access_token: str | None) -> SelectionSession:
    session = db.get(SelectionSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="选单会话不存在")
    if not access_token or not secrets.compare_digest(session.access_token_hash, _hash_token(access_token)):
        raise HTTPException(status_code=403, detail="选单访问凭证无效")
    return session


def _get_locked_session(db: Session, session_id: str, access_token: str | None) -> SelectionSession:
    """锁定选单并在锁释放后读取最新状态，保护提交动作的幂等性。"""
    session = db.scalar(
        select(SelectionSession)
        .where(SelectionSession.id == session_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not session:
        raise HTTPException(status_code=404, detail="选单会话不存在")
    if not access_token or not secrets.compare_digest(session.access_token_hash, _hash_token(access_token)):
        raise HTTPException(status_code=403, detail="选单访问凭证无效")
    return session


def _latest_service_occupancy(db: Session, session_id: str) -> PositionOccupancy | None:
    return db.scalar(select(PositionOccupancy).where(
        PositionOccupancy.selection_session_id == session_id,
    ).order_by(PositionOccupancy.id.desc()))


def _session_price_type(
    db: Session,
    session: SelectionSession,
    confirmed_at: datetime | None = None,
) -> str:
    user = db.get(User, session.customer_id) if session.customer_id else None
    return price_type_for_member(
        bool(user and user.is_member),
        member_expire_at=user.member_expire_at if user else None,
        confirmed_at=confirmed_at,
        member_type=user.member_type if user else None,
    )


def refresh_session_pricing(
    db: Session,
    session: SelectionSession,
    *,
    confirmed_at: datetime | None = None,
) -> dict:
    price_context = None
    if confirmed_at is not None:
        if confirmed_at.tzinfo is None:
            raise ValueError("confirmed_at must be timezone-aware")
        confirmed_at = confirmed_at.astimezone(timezone.utc)
        user = db.get(User, session.customer_id) if session.customer_id else None
        member_expire_at = user.member_expire_at if user else None
        if member_expire_at is not None and member_expire_at.tzinfo is None:
            member_expire_at = member_expire_at.replace(tzinfo=timezone.utc)
        price_context = PriceContext(
            is_member=bool(user and user.is_member),
            member_type=user.member_type if user else None,
            member_expire_at=member_expire_at,
            confirmed_at=confirmed_at,
            store_timezone="Asia/Shanghai",
            store_id=session.store_id,
        )
    pricing = calculate_selection_pricing(
        db,
        session.items or [],
        _session_price_type(db, session, confirmed_at=confirmed_at),
        price_context=price_context,
    )
    session.pricing_snapshot = pricing
    session.store_total_cents = pricing["store_total_cents"]
    session.member_total_cents = pricing["member_total_cents"]
    return pricing


@router.get("/{session_id}/service-status")
def service_status(session_id: str, x_selection_token: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    session = _get_session(db, session_id, x_selection_token)
    occupancy = _latest_service_occupancy(db, session.id)
    return {
        "selection_session_id": session.id,
        "occupancy_status": occupancy.status if occupancy else None,
        "service_ended_at": occupancy.actual_service_end_at if occupancy else None,
        "can_evaluate": bool(occupancy and occupancy.actual_service_end_at),
        "evaluated": bool(db.scalar(select(ServiceFeedback).where(ServiceFeedback.selection_session_id == session.id))),
    }


@router.post("/{session_id}/feedback")
def submit_feedback(session_id: str, body: FeedbackIn, x_selection_token: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    session = _get_session(db, session_id, x_selection_token)
    occupancy = _latest_service_occupancy(db, session.id)
    if not occupancy or not occupancy.actual_service_end_at:
        raise HTTPException(status_code=409, detail="服务完成后才可以评价")
    existing = db.scalar(select(ServiceFeedback).where(ServiceFeedback.selection_session_id == session.id))
    if existing:
        return {"id": existing.id, "rating": existing.rating, "tags": existing.tags or [], "note": existing.note, "submitted": True}
    feedback = ServiceFeedback(
        store_id=session.store_id,
        selection_session_id=session.id,
        customer_id=session.customer_id,
        rating=body.rating,
        tags=body.tags,
        note=body.note.strip(),
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return {"id": feedback.id, "rating": feedback.rating, "tags": feedback.tags or [], "note": feedback.note, "submitted": True}


def _expire_if_needed(session: SelectionSession) -> bool:
    if session.status == "draft" and session.expires_at:
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expires_at:
            session.status = "expired"
            return True
    return False


def _validate_items(db: Session, store_id: int, items: list[SelectionItemIn]) -> list[dict]:
    normalized = []
    linked_items = []
    dedicated_items = []
    for item in items:
        if item.item_type not in {"service", "preference"}:
            raise HTTPException(status_code=400, detail="选单项目类型无效")
        if item.addon_id is not None:
            if item.project_id is not None or item.addon_ids or item.item_type != "service":
                raise HTTPException(status_code=400, detail="独立加项不能同时关联主项目或附加项")
            addon = db.get(Addon, item.addon_id)
            if not addon or addon.store_id != store_id or addon.publication_status != "published":
                raise HTTPException(status_code=400, detail="存在不可用的加项")
            if not addon.independently_sellable:
                raise HTTPException(status_code=400, detail="当前加项不支持单独选购")
            normalized.append({
                "project_id": None,
                "addon_id": addon.id,
                "item_kind": "standalone_addon",
                "name": addon.name,
                "category": "addon",
                "code": addon.code,
                "quantity": item.quantity,
                "addon_ids": [],
                "diy_preferences": item.diy_preferences,
                "item_type": "service",
                "chargeable": addon.chargeable,
            })
            continue
        if item.project_id is None:
            raise HTTPException(status_code=400, detail="请选择项目或可单独售卖的加项")
        if item.item_type == "preference" and item.project_id != "tea":
            raise HTTPException(status_code=400, detail="仅茶饮可作为免费偏好提交")

        project = db.get(Project, item.project_id) if isinstance(item.project_id, int) else None
        if project is None and not (
            isinstance(item.project_id, str)
            and item.project_id in {"tea", *SYNTHETIC_SERVICE_IDS}
        ):
            raise HTTPException(status_code=404, detail=f"项目 {item.project_id} 不存在")
        if isinstance(item.project_id, str) and item.project_id in SYNTHETIC_SERVICE_IDS and item.item_type != "service":
            raise HTTPException(status_code=400, detail="加强项必须按服务项目提交")
        if project and (project.store_id != store_id or project.publication_status != "published"):
            raise HTTPException(status_code=404, detail="项目不存在或未在该门店发布")
        if project and (
            project.category in DETAIL_ONLY_PROJECT_CATEGORIES
            or project.code in DETAIL_ONLY_PROJECT_CODES
        ):
            raise HTTPException(status_code=400, detail={
                "code": "DETAIL_ONLY_PROJECT",
                "message": "套盒仅供查看详情，不支持加入顾客选单",
            })

        for addon_id in item.addon_ids:
            addon = db.get(Addon, addon_id)
            if not addon or addon.store_id != store_id or addon.publication_status != "published":
                raise HTTPException(status_code=400, detail="存在不可用的加项")
            if project and addon.parent_project_id and addon.parent_project_id != project.id:
                raise HTTPException(status_code=400, detail="加项不适用于当前主项目")
            if project and not addon.can_attach_to_parent:
                raise HTTPException(status_code=400, detail="当前加项不可随主项目选择")

        snapshot = (
            {"name": project.name, "category": project.category, "code": project.code}
            if project else SYNTHETIC_PROJECTS[item.project_id]
        )
        normalized_item = {
            "project_id": item.project_id,
            "item_kind": "project",
            "name": snapshot["name"],
            "category": snapshot["category"],
            "code": snapshot.get("code", str(item.project_id)),
            "quantity": item.quantity,
            "addon_ids": item.addon_ids,
            "diy_preferences": item.diy_preferences,
            "item_type": item.item_type,
            # 收费属性由目录与项目类型决定，不能相信顾客端传入的 chargeable。
            "chargeable": item.item_type != "preference",
        }
        if item.catalog_version_id is None:
            current_catalog = (
                db.get(ProjectCatalogVersion, project.current_published_version_id)
                if project and project.current_published_version_id is not None
                else None
            )
            if item.option_choice_ids or (
                current_catalog is not None
                and current_catalog.project_id == project.id
                and current_catalog.status == "published"
            ):
                raise HTTPException(status_code=409, detail={
                    "code": "CATALOG_VERSION_REQUIRED",
                    "message": "提交目录选择项时必须指定目录版本",
                })
        else:
            if project is None:
                raise HTTPException(status_code=409, detail={
                    "code": "CATALOG_PROJECT_UNAVAILABLE",
                    "message": "当前项目不支持目录选择",
                })
            try:
                resolved = resolve_catalog_selection(
                    db,
                    store_id=store_id,
                    project_id=project.id,
                    catalog_version_id=item.catalog_version_id,
                    choice_ids=item.option_choice_ids,
                )
            except CatalogSelectionError as exc:
                raise HTTPException(status_code=409, detail={
                    "code": exc.code,
                    "message": exc.message,
                }) from exc
            for linked_item in resolved.linked_items:
                linked_item["source_project_id"] = project.id
                linked_item["source_catalog_version_id"] = resolved.catalog_version_id
            for dedicated_item in resolved.dedicated_items:
                dedicated_item["source_project_id"] = project.id
                dedicated_item["source_catalog_version_id"] = resolved.catalog_version_id
            normalized_item["catalog_version_id"] = resolved.catalog_version_id
            normalized_item["option_choice_ids"] = [
                *item.option_choice_ids,
            ]
            normalized_item["catalog_selection"] = {
                "catalog_version_id": resolved.catalog_version_id,
                "option_choice_ids": [*item.option_choice_ids],
                "preference_snapshots": resolved.preference_snapshots,
                "linked_snapshots": [
                    linked_item["choice_snapshot"]
                    for linked_item in resolved.linked_items
                ],
                "dedicated_snapshots": [
                    dedicated_item["choice_snapshot"]
                    for dedicated_item in resolved.dedicated_items
                ],
            }
            linked_items.extend(resolved.linked_items)
            dedicated_items.extend(resolved.dedicated_items)
        normalized.append(normalized_item)
    try:
        merged = merge_linked_service_units(normalized, linked_items)
    except CatalogSelectionError as exc:
        raise HTTPException(status_code=409, detail={
            "code": exc.code,
            "message": exc.message,
        }) from exc
    return [
        *merged,
        *dedicated_items,
    ]


def _saving_hint(db: Session, store_id: int, pricing: dict, customer: User | None) -> dict | None:
    """匿名浏览器身份不等于手机号身份，仍可显示可跳过的登录引导。"""
    if customer and customer.phone:
        return None
    # 登录引导与顾客当前预计金额保持同一口径：比较本次门店预计应付与会员价。
    saving = max(0, int(pricing["payable_total_cents"]) - int(pricing["member_total_cents"]))
    if saving:
        return {"kind": "member", "estimated_saving_cents": saving, "login_required": True}
    claimable = list(db.scalars(select(CouponTemplate).where(
        CouponTemplate.is_claimable.is_(True),
        CouponTemplate.status == "published",
    )))
    if any(int(template.min_spend_cents or 0) <= int(pricing["store_total_cents"]) for template in claimable):
        return {"kind": "coupon", "login_required": True}
    return None


def _revision_view(revision: SelectionRevision) -> dict:
    return {
        "id": revision.id,
        "selection_session_id": revision.selection_session_id,
        "revision_no": revision.revision_no,
        "state": revision.state,
        "snapshot": revision.snapshot or {},
        "created_at": revision.created_at.isoformat() if revision.created_at else None,
    }


def _item_identity(item: dict) -> tuple:
    return (
        str(item.get("project_id")),
        str(item.get("addon_id")),
        tuple(sorted(str(value) for value in item.get("addon_ids", []))),
        tuple(str(value) for value in item.get("diy_preferences", [])),
        item.get("item_type"),
    )


def _added_items(previous_items: list[dict], current_items: list[dict]) -> list[dict]:
    """保留重复服务行的计数语义，只输出当前版本相对上一版的新增行。"""
    remaining = [_item_identity(item) for item in previous_items]
    added = []
    for item in current_items:
        identity = _item_identity(item)
        if identity in remaining:
            remaining.remove(identity)
        else:
            added.append(item)
    return added


@router.post("/{session_id}/quote")
def quote_selection_session(
    session_id: str,
    body: SelectionSaveIn,
    x_selection_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    session = _get_session(db, session_id, x_selection_token)
    normalized = _validate_items(db, session.store_id, body.items)
    customer = db.get(User, session.customer_id) if session.customer_id else None
    pricing = calculate_selection_pricing(
        db,
        normalized,
        price_type_for_member(
            bool(customer and customer.is_member),
            member_expire_at=customer.member_expire_at if customer else None,
            member_type=customer.member_type if customer else None,
        ),
    )
    automatic_coupon = select_automatic_coupon(
        db,
        customer_id=session.customer_id,
        pricing=pricing,
        now=datetime.now(timezone.utc),
    )
    return {
        "items": normalized,
        "pricing": pricing,
        "automatic_coupon": automatic_coupon.as_dict(),
        "saving_hint": _saving_hint(db, session.store_id, pricing, customer),
    }


@router.post("/{session_id}/bind-customer")
def bind_selection_customer(
    session_id: str,
    x_selection_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """将当前匿名选单绑定到已登录账号，避免登录态与选单身份脱节。"""
    session = db.scalar(
        select(SelectionSession)
        .where(SelectionSession.id == session_id)
        .with_for_update()
    )
    if not session:
        raise HTTPException(status_code=404, detail="选单会话不存在")
    if not x_selection_token or not secrets.compare_digest(session.access_token_hash, _hash_token(x_selection_token)):
        raise HTTPException(status_code=403, detail="选单访问凭证无效")
    user_id = _current_user_id(authorization)
    user = db.get(User, user_id) if user_id else None
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    current = db.get(User, session.customer_id) if session.customer_id else None
    if session.customer_id and current and not _is_anonymous_customer(current) and session.customer_id != user.id:
        raise HTTPException(status_code=409, detail="当前选单已绑定其他账号")
    if session.customer_id != user.id:
        session.customer_id = user.id
        refresh_session_pricing(db, session)
        db.commit()
    return {"selection_session_id": session.id, "customer_id": session.customer_id}


@router.post("/{session_id}/revisions")
def submit_selection_revision(
    session_id: str,
    body: SelectionSaveIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_selection_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    if not idempotency_key or len(idempotency_key) > 96:
        raise HTTPException(status_code=400, detail="请提供有效的幂等键")
    session = _get_locked_session(db, session_id, x_selection_token)
    existing = db.scalar(select(SelectionRevision).where(
        SelectionRevision.selection_session_id == session.id,
        SelectionRevision.idempotency_key == idempotency_key,
    ))
    if existing:
        return _revision_view(existing)
    if session.status in {"cancelled", "expired"}:
        raise HTTPException(status_code=409, detail="当前服务状态不能继续加选")
    normalized = _validate_items(db, session.store_id, body.items)
    if not normalized:
        raise HTTPException(status_code=400, detail="请至少选择一个项目")
    pricing = calculate_selection_pricing(db, normalized, _session_price_type(db, session))
    previous = db.scalar(select(SelectionRevision).where(
        SelectionRevision.selection_session_id == session.id,
    ).order_by(SelectionRevision.revision_no.desc()))
    occupancy = _latest_service_occupancy(db, session.id)
    if occupancy and occupancy.status in {"post_service_present", "cleaning", "released"}:
        raise HTTPException(status_code=409, detail="当前服务已结束，不能继续加选")
    if session.status == "confirmed" and (not occupancy or occupancy.status != "in_service"):
        raise HTTPException(status_code=409, detail="当前服务状态不能继续加选")
    is_in_service = bool(occupancy and occupancy.status == "in_service")
    previous_items = (previous.snapshot or {}).get("items", []) if previous else []
    revision = SelectionRevision(
        id=str(uuid.uuid4()),
        selection_session_id=session.id,
        revision_no=(previous.revision_no if previous else 0) + 1,
        state="awaiting_staff_confirmation" if is_in_service else "submitted",
        idempotency_key=idempotency_key,
        snapshot={
            "items": normalized,
            "added_items": _added_items(previous_items, normalized),
            "pricing": pricing,
            "diy_preferences": body.diy_preferences,
            "member_confirmed": bool((db.get(User, session.customer_id).phone) if session.customer_id and db.get(User, session.customer_id) else False),
        },
    )
    # During service, the revision is only a request. Keep the confirmed
    # selection and its frozen price untouched until front-desk approval.
    if not is_in_service:
        session.items = normalized
        session.diy_preferences = body.diy_preferences
        session.pricing_snapshot = pricing
        session.store_total_cents = pricing["store_total_cents"]
        session.member_total_cents = pricing["member_total_cents"]
        if session.status != "confirmed":
            session.status = "submitted"
            session.submitted_at = datetime.now(timezone.utc)
        if occupancy and occupancy.status == "held":
            occupancy.status = "waiting_service"
            occupancy.hold_expires_at = None
            occupancy.version += 1
    db.add(revision)
    # PostgreSQL enforces the FK from selection_change_requests to the
    # revision row; flush the parent before adding the dependent request.
    if is_in_service:
        db.flush()
    if is_in_service:
        db.add(SelectionChangeRequest(
            id=str(uuid.uuid4()),
            selection_session_id=session.id,
            selection_revision_id=revision.id,
            state="awaiting_staff_confirmation",
        ))
    db.commit()
    db.refresh(revision)
    return _revision_view(revision)


@router.post("", response_model=SelectionCreateOut)
def create_selection_session(body: SelectionCreateIn, db: Session = Depends(get_db)) -> SelectionCreateOut:
    if not db.get(Store, body.store_id):
        raise HTTPException(status_code=404, detail="门店不存在")
    token = secrets.token_urlsafe(32)
    session = SelectionSession(
        id=str(uuid.uuid4()),
        access_token_hash=_hash_token(token),
        store_id=body.store_id,
        # 当前选单链路支持匿名手机/平板使用，不接受客户端自行绑定顾客账号。
        customer_id=None,
        source=body.source,
        device_label=body.device_label,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS),
        items=[],
        diy_preferences={},
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return SelectionCreateOut(session=session, access_token=token)


@router.get("/mine", response_model=MySelectionSessionsOut)
def my_selection_sessions(
    status: str | None = None,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> MySelectionSessionsOut:
    """个人中心：按 JWT 列出当前顾客的选单（新→旧，最多 50 条）。"""
    user_id = _current_user_id(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    stmt = select(SelectionSession).where(SelectionSession.customer_id == user_id)
    if status:
        stmt = stmt.where(SelectionSession.status == status)
    sessions = list(db.scalars(stmt.order_by(SelectionSession.created_at.desc()).limit(50)))
    return MySelectionSessionsOut(items=sessions, total=len(sessions))


@router.get("/{session_id}", response_model=SelectionSessionOut)
def get_selection_session(
    session_id: str,
    x_selection_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> SelectionSession:
    session = _get_session(db, session_id, x_selection_token)
    if _expire_if_needed(session):
        db.commit()
    return session


@router.patch("/{session_id}", response_model=SelectionSessionOut)
def save_selection_session(
    session_id: str,
    body: SelectionSaveIn,
    x_selection_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> SelectionSession:
    session = _get_session(db, session_id, x_selection_token)
    if _expire_if_needed(session):
        db.commit()
    if session.status != "draft":
        raise HTTPException(status_code=409, detail="当前选单已不能修改")
    normalized = _validate_items(db, session.store_id, body.items)
    changed = session.items != normalized or session.diy_preferences != body.diy_preferences
    session.items = normalized
    session.diy_preferences = body.diy_preferences
    refresh_session_pricing(db, session)
    if body.device_label:
        session.device_label = body.device_label
    if changed:
        refresh_hold(db, session.id)
    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/submit", response_model=SelectionSessionOut)
def submit_selection_session(
    session_id: str,
    body: SelectionSaveIn | None = None,
    x_selection_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> SelectionSession:
    # 同一选单可能被双击或弱网重试并发提交。后到请求会等待行锁释放，
    # 然后读取第一次提交后的状态，避免覆盖提交快照或重复迁移服务位状态。
    session = _get_locked_session(db, session_id, x_selection_token)
    if session.status == "submitted" or session.status == "confirmed":
        return session
    if _expire_if_needed(session):
        db.commit()
    if session.status != "draft":
        raise HTTPException(status_code=409, detail="当前选单不能提交")
    if body is not None:
        session.items = _validate_items(db, session.store_id, body.items)
        session.diy_preferences = body.diy_preferences
    if not session.items:
        raise HTTPException(status_code=400, detail="请至少选择一个项目")
    refresh_session_pricing(db, session)
    session.status = "submitted"
    session.submitted_at = datetime.now(timezone.utc)
    occupancy = db.scalar(select(PositionOccupancy).where(
        PositionOccupancy.active_session_id == session.id,
    ))
    if occupancy and occupancy.status == "held":
        occupancy.status = "waiting_service"
        occupancy.hold_expires_at = None
        occupancy.version += 1
    db.commit()
    db.refresh(session)
    return session
