"""Best-effort WeCom notifications for the store manager chat.

Notifications are scheduled after the customer-facing write is committed. They
never change order state and failures are intentionally swallowed so that a
WeCom outage cannot break customer submission or feedback.
"""

from datetime import datetime
from html import escape
import logging
from uuid import uuid4
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import AuditLog, SelectionSession, ServiceFeedback, Staff, Store, VisitFeedback
from app.models.staff_access import StaffScopeAssignment
from app.models.staff_external_identity import StaffExternalIdentity
from app.services.wecom_staff import WecomMessageReceipt, WecomProviderError, get_wecom_provider, local_binding


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
        select(StaffExternalIdentity)
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
    userids = []
    for identity in rows:
        try:
            local_binding(db, identity)
        except Exception:
            # Match the login boundary, including expired or ambiguous grants.
            continue
        userids.append(identity.userid.lower())
    userids = sorted(set(userids))
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


logger = logging.getLogger(__name__)


def _review_audit(store_id: int, entity_type: str, feedback_id: int, attempt: str, status: str, **counts) -> bool:
    try:
        with SessionLocal() as db:
            db.add(AuditLog(
                actor_type="system", actor_id="wecom-feedback-notify",
                action="wecom_feedback_notify", entity_type=entity_type,
                entity_id=str(feedback_id), store_id=store_id,
                detail={"attempt_id": attempt, "status": status, **counts},
            ))
            db.commit()
        return True
    except Exception:
        # Never log upstream URLs, credentials, recipients or feedback content.
        logger.warning("WeCom feedback notification audit unavailable")
        return False


def _notify_review(feedback_id: int, feedback_type: str) -> None:
    if not settings.wecom_staff_enabled:
        return
    attempt = str(uuid4())
    entity_type = "service_feedback" if feedback_type == "service_review" else "visit_feedback"
    try:
        with SessionLocal() as db:
            model = ServiceFeedback if feedback_type == "service_review" else VisitFeedback
            feedback = db.get(model, feedback_id)
            store = db.get(Store, feedback.store_id) if feedback else None
            if not feedback or not store:
                return
            if feedback_type == "service_review":
                session = db.get(SelectionSession, feedback.selection_session_id)
                if not session or session.store_id != feedback.store_id:
                    return
            store_id = store.id
            userids = manager_userids(db, store_id)
            description = "\n".join([
                f"门店：{escape(store.name)}",
                "来源：" + ("服务评价" if feedback_type == "service_review" else "到店扫码评价"),
                f"评分：{feedback.rating} 星",
                "请进入工作台查看评价并记录跟进。",
            ])
        if not userids:
            _review_audit(store_id, entity_type, feedback_id, attempt, "no_recipient", recipient_count=0)
            return
        if not _review_audit(store_id, entity_type, feedback_id, attempt, "started", recipient_count=len(userids)):
            return
        url = settings.h5_public_base_url.rstrip("/") + "/technician/store/wecom?" + urlencode({"review": f"{feedback_type}:{feedback_id}"})
        try:
            receipt = get_wecom_provider().send_textcard(userids, "荷小悦 · 顾客评价", description, url, "查看评价")
            if not isinstance(receipt, WecomMessageReceipt):
                raise WecomProviderError()
        except Exception:
            # A timeout may occur after provider acceptance. Do not blindly retry.
            _review_audit(store_id, entity_type, feedback_id, attempt, "unknown", recipient_count=len(userids))
            return
        _review_audit(store_id, entity_type, feedback_id, attempt, receipt.status,
                      recipient_count=len(userids), accepted_count=receipt.accepted_count,
                      invalid_count=receipt.invalid_count)
    except Exception:
        # The committed customer feedback must not depend on notification health.
        logger.warning("WeCom feedback notification unavailable")


def notify_feedback(feedback_id: int) -> None:
    _notify_review(feedback_id, "service_review")


def notify_visit_feedback(feedback_id: int) -> None:
    if settings.wecom_visit_feedback_notify_enabled:
        _notify_review(feedback_id, "visit_feedback")
