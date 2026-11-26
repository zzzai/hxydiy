"""Deliver store inspection actions and a single private weekly summary per recipient."""
import asyncio
from datetime import UTC, datetime, time, timedelta
from html import escape
import logging

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.session import SessionLocal
from app.domain.inspection_checklist import CHECKLISTS
from app.models import DailyAreaPhotoReview, InspectionDelivery
from app.models.staff_external_identity import StaffExternalIdentity
from app.services.inspection_issues import PROBLEMS, followups_by_root, latest_review, roots_query, verdict
from app.services.inspection_receipts import notice_key
from app.services.inspection_weekly import SHANGHAI, weekly_due, weekly_text
from app.services.wecom_notify import verified_manager_bindings
from app.services.wecom_staff import WecomMessageRejected, WecomProviderError, get_wecom_provider, local_binding

log = logging.getLogger("app.inspection_dispatch")


def enabled():
    return bool(settings.inspection_workflow_from and settings.inspection_wecom_enabled and settings.wecom_staff_enabled
                and settings.inspection_weekly_binding_id and settings.inspection_weekly_binding_version)


def _record(db, key, identity, **scope):
    existing = select(InspectionDelivery.id).where(InspectionDelivery.event_key == key,
                                                  InspectionDelivery.binding_id == identity.id)
    if db.scalar(existing) is not None:
        return
    try:
        with db.begin_nested():
            item = InspectionDelivery(event_key=key, binding_id=identity.id, binding_version=identity.binding_version, **scope)
            db.add(item)
            db.flush()
            if item.week_start:
                item.summary_text = weekly_text(db, item.week_start, as_of=datetime.combine(
                    item.week_start + timedelta(days=7), time.min, SHANGHAI))
    except IntegrityError:
        if db.scalar(existing) is None:
            raise


def enqueue(factory=SessionLocal, *, now=None):
    if not enabled():
        return
    now = now or datetime.now(UTC)
    with factory.begin() as db:
        db.execute(update(InspectionDelivery).where(InspectionDelivery.state == "sending",
            InspectionDelivery.attempted_at < now - timedelta(minutes=10)).values(state="unknown", finished_at=now))
        weekly = db.get(StaffExternalIdentity, settings.inspection_weekly_binding_id)
        if (not weekly or weekly.status != "active" or weekly.provider != "wecom"
                or weekly.corp_id != settings.wecom_corp_id or weekly.binding_version != settings.inspection_weekly_binding_version):
            raise ValueError("Weekly inspection recipient binding is unavailable")
        local_binding(db, weekly)
        start = weekly_due(now)
        if datetime.combine(start + timedelta(days=7), time.min, SHANGHAI) > settings.inspection_workflow_from:
            _record(db, f"weekly/{start.isoformat()}", weekly, week_start=start)
        rows = db.execute(roots_query(now)).all()
        history = followups_by_root(db, [root.id for root, *_ in rows])
        managers = {}
        for root, _, day, _ in rows:
            last = latest_review(root, history[root.id])
            if verdict(last) not in PROBLEMS:
                continue
            if day.store_id not in managers:
                managers[day.store_id] = verified_manager_bindings(db, day.store_id)
            for recipient in managers[day.store_id]:
                if recipient.id != weekly.id:
                    _record(db, f"review/{last.id}", recipient, root_id=root.id, review_id=last.id)


def deliver_next(factory=SessionLocal, *, provider=None, now=None):
    if not enabled():
        return False
    now = now or datetime.now(UTC)
    with factory.begin() as db:
        item = db.scalar(select(InspectionDelivery).where(InspectionDelivery.state == "pending")
                         .order_by(InspectionDelivery.id).limit(1).with_for_update(skip_locked=True))
        if item is None:
            return False
        identity = db.get(StaffExternalIdentity, item.binding_id)
        valid = identity and identity.binding_version == item.binding_version and identity.status == "active"
        valid = valid and identity.provider == "wecom" and identity.corp_id == settings.wecom_corp_id
        entry = f"{settings.h5_public_base_url.rstrip('/')}/technician/store/wecom?notice={notice_key(item)}"
        card = None
        summary = None
        if item.week_start:
            valid = (valid and identity.id == settings.inspection_weekly_binding_id
                     and identity.binding_version == settings.inspection_weekly_binding_version)
            if valid:
                try:
                    local_binding(db, identity)
                except HTTPException:
                    valid = False
                summary = item.summary_text
                valid = valid and bool(summary)
                if summary:
                    link = f"\n\n查看完整周报：{entry}"
                    if len((summary + link).encode("utf-8")) > 2000:
                        summary = summary.splitlines()[0] + "\n两店巡检覆盖、整改和下周重点见完整周报。"
                    summary += link
        elif valid:
            row = db.execute(roots_query(now).where(DailyAreaPhotoReview.id == item.root_id)).one_or_none()
            valid = row is not None and identity.id != settings.inspection_weekly_binding_id
            if valid:
                root, photo, day, _ = row
                last = latest_review(root, followups_by_root(db, [root.id])[root.id])
                valid = (last.id == item.review_id and verdict(last) in PROBLEMS
                         and identity.id in {m.id for m in verified_manager_bindings(db, day.store_id)})
                if valid:
                    action = "需整改" if verdict(last) == "fix" else "需补拍"
                    card = (f"{CHECKLISTS[3][photo.area]} · {action}",
                            f"{day.business_date} 巡检\n{escape(last.result['location'])} · {escape(last.result['evidence'])}"
                            f"\n{escape(last.result['action'])}",
                            f"{entry}&inspection={root.id}")
        if not valid:
            item.state, item.finished_at = "cancelled", now
            return True
        delivery_id, userid = item.id, identity.userid
        item.state, item.attempted_at = "sending", now
    service = provider or get_wecom_provider()
    try:
        receipt = (service.send_text([userid], summary) if summary is not None
                   else service.send_textcard([userid], *card, "处理巡检"))
        status = "accepted" if receipt.accepted_count == 1 else "rejected"
    except WecomMessageRejected:
        status = "rejected"
    except WecomProviderError:
        status = "unknown"
    with factory.begin() as db:
        db.execute(update(InspectionDelivery).where(InspectionDelivery.id == delivery_id,
            InspectionDelivery.state == "sending").values(state=status, finished_at=now))
    if status != "accepted":
        log.warning("inspection_delivery_%s receipt=%s", status, delivery_id)
    return True


async def run_dispatcher():
    while True:
        try:
            await asyncio.to_thread(enqueue)
            for _ in range(50):
                if not await asyncio.to_thread(deliver_next):
                    break
        except Exception as exc:
            log.error("inspection_dispatcher_failed type=%s", type(exc).__name__)
        await asyncio.sleep(60)
