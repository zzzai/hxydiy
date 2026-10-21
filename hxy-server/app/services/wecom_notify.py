"""Best-effort WeCom notifications for the store manager chat.

Notifications are scheduled after the customer-facing write is committed. They
never change order state and failures are intentionally swallowed so that a
WeCom outage cannot break customer submission or feedback.
"""

from datetime import datetime
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import AuditLog, SelectionSession, ServiceFeedback, Staff, Store
from app.models.staff_access import StaffScopeAssignment
from app.models.staff_external_identity import StaffExternalIdentity
from app.services.wecom_staff import WecomProviderError, get_wecom_provider


SOURCE_LABELS = {
    "in_store": "到店选单",
    "mini_program": "顾客手机",
    "personal_qr": "顾客扫码",
    "room_qr": "座位扫码",
    "store_qr": "门店扫码",
    "bound_qr": "座位扫码",
    "tablet": "门店平板",
    "kiosk": "门店平板",
}


def _money(cents: int | None) -> str:
    if not isinstance(cents, int) or cents < 0:
        return "金额待核实"
    return "¥" + (str(cents // 100) if cents % 100 == 0 else f"{cents / 100:.2f}")


def _items_text(items: list[dict] | None) -> str:
    names = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        quantity = item.get("quantity")
        names.append(f"{name}×{quantity}" if isinstance(quantity, int) and quantity > 1 else name)
    return "、".join(names) or "未填写项目"


def manager_userids(db: Session, store_id: int) -> list[str]:
    """Active store managers with a verified WeCom binding and exactly one store grant."""
    active_grant = select(StaffScopeAssignment.id).where(
        StaffScopeAssignment.staff_id == Staff.id,
        StaffScopeAssignment.role == "store_manager",
        StaffScopeAssignment.scope_type == "store",
        StaffScopeAssignment.scope_id == store_id,
        StaffScopeAssignment.status == "active",
    ).exists()
    rows = db.execute(
        select(StaffExternalIdentity.userid)
        .join(Staff, Staff.id == StaffExternalIdentity.staff_id)
        .where(
            StaffExternalIdentity.provider == "wecom",
            StaffExternalIdentity.corp_id == settings.wecom_corp_id,
            StaffExternalIdentity.store_id == store_id,
            StaffExternalIdentity.status == "active",
            Staff.store_id == store_id,
            Staff.status == "active",
            Staff.role == "manager",
            active_grant,
        )
        .order_by(StaffExternalIdentity.userid)
    ).scalars().all()
    userids = sorted({str(userid).lower() for userid in rows if userid})
    configured = [value.strip().lower() for value in settings.wecom_order_notify_userids.split(",") if value.strip()]
    return [userid for userid in userids if not configured or userid in configured]


def _send(store_id: int, title: str, description: str, query: str, button_label: str) -> None:
    db = SessionLocal()
    try:
        userids = manager_userids(db, store_id)
    finally:
        db.close()
    if not userids:
        return
    url = settings.h5_public_base_url.rstrip("/") + "/technician/store/wecom?" + query
    try:
        get_wecom_provider().send_textcard(userids, title, description, url, button_label)
    except WecomProviderError:
        # Best-effort only. The order/feedback remains authoritative.
        return


def notify_new_selection(session_id: str) -> None:
    if not settings.wecom_staff_enabled:
        return
    db = SessionLocal()
    try:
        session = db.get(SelectionSession, session_id)
        store = db.get(Store, session.store_id) if session else None
        if not session or not store or session.status not in {"submitted", "confirmed"}:
            return
        store_id = store.id
        order_id = session.id
        pricing = session.pricing_snapshot if isinstance(session.pricing_snapshot, dict) else {}
        description = "\n".join([
            f"门店：{store.name}",
            f"项目：{_items_text(session.items)}",
            f"金额：{_money(pricing.get('payable_total_cents'))}",
            f"来源：{SOURCE_LABELS.get(session.source, '门店入口')}",
            f"时间：{datetime.now().strftime('%m-%d %H:%M')}",
            f"订单：{session.id[-8:]}",
        ])
        db.add(AuditLog(
            actor_type="system",
            actor_id="wecom-order-notify",
            action="wecom_order_notify",
            entity_type="selection_session",
            entity_id=session.id,
            store_id=session.store_id,
            detail={"kind": "new_order"},
        ))
        db.commit()
    finally:
        db.close()
    _send(store_id, "荷小悦 · 新订单", description, urlencode({"order": order_id}), "查看订单")


def notify_feedback(feedback_id: int) -> None:
    if not settings.wecom_staff_enabled:
        return
    db = SessionLocal()
    try:
        feedback = db.get(ServiceFeedback, feedback_id)
        session = db.get(SelectionSession, feedback.selection_session_id) if feedback else None
        store = db.get(Store, feedback.store_id) if feedback else None
        if not feedback or not session or not store:
            return
        store_id = store.id
        tags = "、".join(str(tag) for tag in (feedback.tags or []) if tag)
        note = (feedback.note or "").strip()
        description = "\n".join([
            f"门店：{store.name}",
            f"评分：{feedback.rating} 星",
            f"标签：{tags or '未选择'}",
            f"说明：{note[:120] or '未填写'}",
            f"订单：{session.id[-8:]}",
        ])
        db.add(AuditLog(
            actor_type="system",
            actor_id="wecom-order-notify",
            action="wecom_order_notify",
            entity_type="service_feedback",
            entity_id=str(feedback.id),
            store_id=feedback.store_id,
            detail={"kind": "feedback"},
        ))
        db.commit()
    finally:
        db.close()
    _send(store_id, "荷小悦 · 顾客评价", description, urlencode({"review": f"service_review:{feedback.id}"}), "查看评价")
