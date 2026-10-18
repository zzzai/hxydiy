import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, func, literal, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.technician import current_technician
from app.db.session import get_db
from app.domain.customer_operational_tags import operational_tag_view
from app.models import AuditLog, PositionOccupancy, SelectionSession, User
from app.models.customer_tag_contribution import CustomerTagContribution
from app.models.feedback import ServiceFeedback, VisitFeedback
from app.models.operations import Room
from app.models.scrm import CustomerTag
from app.services.technician_reports import get_technician_report_access, read_service_reports

router = APIRouter(prefix="/technician", tags=["technician-customers"])


def _error(status, code, message):
    return HTTPException(status, detail={"code": code, "message": message})


def _reject_override(request):
    if set(request.query_params) - {"page", "page_size"}:
        raise _error(422, "CUSTOMER_OVERRIDE_FORBIDDEN", "顾客身份只能来自当前服务记录")


def _scope(db, staff, technician, occupancy_id, *, bound=True, lock=False):
    query = select(PositionOccupancy, SelectionSession).join(SelectionSession, PositionOccupancy.selection_session_id == SelectionSession.id).where(
        PositionOccupancy.id == occupancy_id,
        PositionOccupancy.store_id == staff.store_id,
        SelectionSession.store_id == staff.store_id,
        PositionOccupancy.serviced_by_technician_id == technician.id,
        PositionOccupancy.status.in_(["in_service", "post_service_present"]),
        PositionOccupancy.active_room_id == PositionOccupancy.room_id,
        PositionOccupancy.active_session_id == SelectionSession.id,
        PositionOccupancy.departed_at.is_(None), PositionOccupancy.released_at.is_(None),
        SelectionSession.status.in_(["submitted", "confirmed"]),
    )
    if lock:
        query = query.with_for_update()
    row = db.execute(query).first()
    if not row:
        raise _error(404, "CUSTOMER_SERVICE_NOT_FOUND", "当前服务记录不可用")
    occupancy, selection = row
    user = db.get(User, selection.customer_id) if selection.customer_id else None
    if user and user.openid.startswith("anon_"):
        user = None
    if bound and not user:
        raise _error(409, "CUSTOMER_UNBOUND", "当前服务尚未绑定顾客")
    return occupancy, selection, user


def _audit(db, staff, occupancy, user, resource):
    db.add(AuditLog(actor_type="staff", actor_id=str(staff.id), store_id=staff.store_id,
                    action="technician_customer_read", entity_type="position_occupancy", entity_id=str(occupancy.id),
                    detail={"customer_id": user.id if user else None, "occupancy_id": occupancy.id, "resource": resource}))
    db.commit()


def _page(db, query, page, page_size, projector):
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [projector(row) for row in rows], "total": total, "page": page, "page_size": page_size}


def _projects(items):
    result = []
    for item in items or []:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        quantity = item.get("quantity", 1)
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            quantity = 1
        result.append({"name": item["name"], "quantity": quantity})
    return result


def _task_items(items):
    result = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        clean = {}
        for key in ("id", "type", "name", "quantity"):
            value = item.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                clean[key] = value
        if clean:
            result.append(clean)
    return result


@router.get("/my-tasks")
def my_tasks(request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)):
    _reject_override(request)
    staff, technician = current_technician(authorization, db)
    rows = db.execute(select(PositionOccupancy, SelectionSession, Room).join(SelectionSession, PositionOccupancy.selection_session_id == SelectionSession.id).join(Room, PositionOccupancy.room_id == Room.id).where(
        PositionOccupancy.store_id == staff.store_id, SelectionSession.store_id == staff.store_id, Room.store_id == staff.store_id,
        PositionOccupancy.serviced_by_technician_id == technician.id,
        PositionOccupancy.status.in_(["in_service", "post_service_present"]),
        PositionOccupancy.active_room_id == Room.id, PositionOccupancy.active_session_id == SelectionSession.id,
        PositionOccupancy.departed_at.is_(None), PositionOccupancy.released_at.is_(None), SelectionSession.status.in_(["submitted", "confirmed"]),
    ).order_by(PositionOccupancy.id.desc()).limit(100)).all()
    return {"items": [{"occupancy_id": o.id, "user_id": s.customer_id, "selection_session_id": s.id, "occupancy_status": o.status, "room_id": r.id, "room_name": r.name, "items": _task_items(s.items)} for o, s, r in rows]}


@router.get("/occupancies/{occupancy_id}/customer-summary")
def summary(occupancy_id: int, request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)):
    _reject_override(request)
    staff, technician = current_technician(authorization, db)
    occupancy, _, user = _scope(db, staff, technician, occupancy_id, bound=False)
    result = {"occupancy_id": occupancy.id, "customer_id": user.id if user else None, "customer_name": user.nickname or None if user else None, "access": "granted" if user else "unbound", "membership": {"level": user.member_type} if user else None}
    _audit(db, staff, occupancy, user, "summary")
    return result


@router.get("/occupancies/{occupancy_id}/customer-history")
def history(occupancy_id: int, request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), authorization: str | None = Header(None), db: Session = Depends(get_db)):
    _reject_override(request)
    staff, technician = current_technician(authorization, db)
    occupancy, _, user = _scope(db, staff, technician, occupancy_id)
    query = select(PositionOccupancy, SelectionSession).join(SelectionSession, PositionOccupancy.selection_session_id == SelectionSession.id).where(PositionOccupancy.store_id == staff.store_id, SelectionSession.store_id == staff.store_id, SelectionSession.customer_id == user.id, PositionOccupancy.actual_start_at.is_not(None)).order_by(PositionOccupancy.id.desc())
    result = _page(db, query, page, page_size, lambda row: {"id": row[0].id, "selection_session_id": row[1].id, "service_started_at": row[0].actual_start_at, "service_finished_at": row[0].actual_service_end_at, "projects": _projects(row[1].items)})
    _audit(db, staff, occupancy, user, "history")
    return result


@router.get("/occupancies/{occupancy_id}/customer-reviews")
def reviews(occupancy_id: int, request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), authorization: str | None = Header(None), db: Session = Depends(get_db)):
    _reject_override(request)
    staff, technician = current_technician(authorization, db)
    occupancy, _, user = _scope(db, staff, technician, occupancy_id)
    completed = select(PositionOccupancy.id).where(PositionOccupancy.selection_session_id == ServiceFeedback.selection_session_id, PositionOccupancy.store_id == staff.store_id, PositionOccupancy.actual_service_end_at.is_not(None)).exists()
    service = select(
        ServiceFeedback.id.label("id"), ServiceFeedback.rating.label("rating"), ServiceFeedback.note.label("content"), ServiceFeedback.created_at.label("created_at"),
        literal("service").label("feedback_type"), literal("completed_service").label("source"), ServiceFeedback.tags.label("tags"), SelectionSession.items.label("projects"),
    ).join(SelectionSession, ServiceFeedback.selection_session_id == SelectionSession.id).where(ServiceFeedback.store_id == staff.store_id, SelectionSession.store_id == staff.store_id, ServiceFeedback.customer_id == user.id, SelectionSession.customer_id == user.id, completed)
    visit = select(
        VisitFeedback.id.label("id"), VisitFeedback.rating.label("rating"), VisitFeedback.note.label("content"), VisitFeedback.created_at.label("created_at"),
        literal("visit").label("feedback_type"), VisitFeedback.source.label("source"), VisitFeedback.tags.label("tags"), literal([], type_=JSON).label("projects"),
    ).join(Room, Room.id == VisitFeedback.room_id).where(VisitFeedback.store_id == staff.store_id, Room.store_id == staff.store_id, VisitFeedback.customer_id == user.id)
    combined = union_all(service, visit).subquery()
    query = select(combined).order_by(combined.c.created_at.desc(), combined.c.feedback_type, combined.c.id.desc())
    result = _page(db, query, page, page_size, lambda row: {"id": row.id, "rating": row.rating, "content": row.content, "created_at": row.created_at, "feedback_type": row.feedback_type, "source": row.source, "tags": [tag for tag in (row.tags or []) if isinstance(tag, str)], "projects": _projects(row.projects)})
    _audit(db, staff, occupancy, user, "reviews")
    return result


@router.get("/occupancies/{occupancy_id}/customer-reports")
@router.get("/occupancies/{occupancy_id}/customer-reports/{report_id}")
def reports(occupancy_id: int, request: Request, report_id: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), authorization: str | None = Header(None), db: Session = Depends(get_db), access=Depends(get_technician_report_access)):
    _reject_override(request)
    staff, technician = current_technician(authorization, db)
    occupancy, _, user = _scope(db, staff, technician, occupancy_id)
    rows = read_service_reports(access, staff_id=staff.id, store_id=staff.store_id, customer_id=user.id, occupancy_id=occupancy.id)
    if report_id is not None:
        result = next((row for row in rows if row["id"] == report_id), None)
        if result is None:
            raise _error(404, "REPORT_NOT_FOUND", "报告不存在")
    else:
        result = {"items": [{key: row[key] for key in ("id", "created_at", "title")} for row in rows[(page - 1) * page_size:page * page_size]], "total": len(rows), "page": page, "page_size": page_size}
    _audit(db, staff, occupancy, user, "report_detail" if report_id else "reports")
    return result


class TagContributionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag_id: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=128)


class TagRevokeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=256)


@router.get("/occupancies/{occupancy_id}/customer-tags")
def tags(occupancy_id: int, request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)):
    _reject_override(request)
    staff, technician = current_technician(authorization, db)
    occupancy, _, user = _scope(db, staff, technician, occupancy_id)
    result = operational_tag_view(db, staff.store_id, user.id, staff.id)
    _audit(db, staff, occupancy, user, "tags")
    return result


def _contribution_result(row):
    return {"id": row.id, "tag_id": row.tag_id, "version": row.version}


@router.post("/occupancies/{occupancy_id}/customer-tags")
def contribute(occupancy_id: int, body: TagContributionIn, request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)):
    _reject_override(request)
    staff, technician = current_technician(authorization, db)
    occupancy, selection, user = _scope(db, staff, technician, occupancy_id, lock=True)
    fingerprint = hashlib.sha256(json.dumps({"occupancy_id": occupancy.id, "user_id": user.id, "tag_id": body.tag_id}, sort_keys=True).encode()).hexdigest()
    existing_query = select(CustomerTagContribution).where(CustomerTagContribution.store_id == staff.store_id, CustomerTagContribution.created_by_staff_id == staff.id, CustomerTagContribution.idempotency_key == body.idempotency_key)
    existing = db.scalar(existing_query)
    if existing:
        if existing.request_hash != fingerprint:
            raise _error(409, "IDEMPOTENCY_KEY_REUSED", "幂等键已用于其他标签操作")
        return _contribution_result(existing)
    tag = db.scalar(select(CustomerTag).where(CustomerTag.id == body.tag_id, CustomerTag.store_id == staff.store_id, CustomerTag.status == "active", CustomerTag.tag_type == "manual").with_for_update())
    if not tag:
        raise _error(404, "OPERATIONAL_TAG_NOT_FOUND", "可选标签不存在")
    row = CustomerTagContribution(store_id=staff.store_id, user_id=user.id, tag_id=tag.id, created_by_staff_id=staff.id, technician_id=technician.id, selection_session_id=selection.id, occupancy_id=occupancy.id, idempotency_key=body.idempotency_key, request_hash=fingerprint)
    try:
        db.add(row)
        db.flush()
        db.add(AuditLog(actor_type="staff", actor_id=str(staff.id), store_id=staff.store_id, action="technician_tag_contribute", entity_type="tag_contribution", entity_id=str(row.id), detail={"occupancy_id": occupancy.id, "customer_id": user.id, "tag_id": tag.id}))
        db.commit()
    except IntegrityError:
        db.rollback()
        # Recheck service scope after a concurrent writer wins the unique key.
        _scope(db, staff, technician, occupancy_id)
        existing = db.scalar(existing_query)
        if existing and existing.request_hash == fingerprint:
            return _contribution_result(existing)
        raise _error(409, "TAG_CONTRIBUTION_CONFLICT", "该服务中的标签贡献已存在") from None
    return _contribution_result(row)


@router.delete("/occupancies/{occupancy_id}/customer-tags/contributions/{contribution_id}")
def revoke(occupancy_id: int, contribution_id: int, body: TagRevokeIn, request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)):
    _reject_override(request)
    staff, technician = current_technician(authorization, db)
    occupancy, _, user = _scope(db, staff, technician, occupancy_id, lock=True)
    row = db.scalar(select(CustomerTagContribution).where(CustomerTagContribution.id == contribution_id, CustomerTagContribution.store_id == staff.store_id, CustomerTagContribution.user_id == user.id, CustomerTagContribution.created_by_staff_id == staff.id, CustomerTagContribution.technician_id == technician.id, CustomerTagContribution.occupancy_id == occupancy.id).with_for_update())
    if not row:
        raise _error(404, "TAG_CONTRIBUTION_NOT_FOUND", "标签贡献不存在或无权撤销")
    reason = body.reason.strip()
    if not reason:
        raise _error(422, "REVOKE_REASON_REQUIRED", "请填写撤销原因")
    if row.revoked_at:
        if body.expected_version in {row.version, row.version - 1} and row.revoke_reason == reason:
            return {"id": row.id, "version": row.version, "revoked": True}
        raise _error(409, "TAG_VERSION_CONFLICT", "标签贡献已变更")
    if row.version != body.expected_version:
        raise _error(409, "TAG_VERSION_CONFLICT", "标签贡献已变更")
    row.revoked_at = datetime.now(timezone.utc)
    row.revoked_by_staff_id = staff.id
    row.revoke_reason = reason
    row.version += 1
    db.add(AuditLog(actor_type="staff", actor_id=str(staff.id), store_id=staff.store_id, action="technician_tag_revoke", entity_type="tag_contribution", entity_id=str(row.id), detail={"occupancy_id": occupancy.id, "customer_id": user.id, "tag_id": row.tag_id}))
    db.commit()
    return {"id": row.id, "version": row.version, "revoked": True}
