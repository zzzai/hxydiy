import hashlib
import json
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin import _current_staff, create_staff_token, hash_password, normalize_staff_role
from app.db.session import get_db
from app.models import AuditLog, PositionOccupancy, Staff
from app.models.operations import Room, Technician
from app.models.service import ServiceAssignment, ServiceOrder, StateTransition, Visit
from app.models.technician_portal import TechnicianInvite, TechnicianLeaveRequest

router = APIRouter(prefix="/technician", tags=["technician"])


class ActivateIn(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=8, max_length=128)


class LeaveRequestIn(BaseModel):
    start_date: date
    end_date: date
    reason: str = Field(min_length=1, max_length=500)


class ActionIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=64)
    note: str = Field(default="", max_length=500)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def make_invite_token() -> str:
    return secrets.token_urlsafe(32)


def invite_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=24)


def current_technician(authorization: str | None, db: Session) -> tuple[Staff, Technician]:
    staff = _current_staff(authorization, db)
    if normalize_staff_role(staff.role, staff.technician_id) != "technician" or not staff.technician_id:
        raise HTTPException(status_code=403, detail="当前账号不是技师账号")
    technician = db.get(Technician, staff.technician_id)
    if not technician or technician.store_id != staff.store_id or technician.status == "resigned":
        raise HTTPException(status_code=401, detail="技师账号不可用")
    return staff, technician


@router.post("/activate")
def activate(body: ActivateIn, db: Session = Depends(get_db)) -> dict:
    invite = db.scalar(select(TechnicianInvite).where(TechnicianInvite.token_hash == token_hash(body.token)))
    now = datetime.now(timezone.utc)
    if not invite or invite.used_at is not None:
        raise HTTPException(status_code=400, detail="激活凭证无效")
    expires_at = invite.expires_at if invite.expires_at.tzinfo else invite.expires_at.replace(tzinfo=timezone.utc)
    if now >= expires_at:
        raise HTTPException(status_code=400, detail="激活凭证已过期")
    staff = db.get(Staff, invite.staff_id)
    technician = db.get(Technician, invite.technician_id)
    if not staff or not technician or staff.store_id != invite.store_id or technician.store_id != invite.store_id:
        raise HTTPException(status_code=400, detail="激活凭证关联数据异常")
    staff.password_hash = hash_password(body.password)
    staff.status = "active"
    staff.role = "technician"
    invite.used_at = now
    db.add(AuditLog(actor_type="staff", actor_id=str(staff.id), store_id=staff.store_id, action="activate_technician", entity_type="technician", entity_id=str(technician.id), detail={"staff_id": staff.id, "invite_id": invite.id}))
    db.commit()
    return {"token": create_staff_token(staff.id, staff.role), "staff": {"id": staff.id, "name": staff.name, "role": staff.role, "store_id": staff.store_id, "technician_id": staff.technician_id}}


@router.get("/me")
def me(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    staff, technician = current_technician(authorization, db)
    return {"staff": {"id": staff.id, "name": staff.name, "username": staff.username, "role": "technician", "store_id": staff.store_id, "technician_id": technician.id}, "technician": {"id": technician.id, "name": technician.name, "code": technician.code, "level": technician.level, "skills": technician.skills, "status": technician.status}}


@router.get("/tasks")
def tasks(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    _, technician = current_technician(authorization, db)
    assignments = db.scalars(select(ServiceAssignment).where(ServiceAssignment.store_id == technician.store_id, ServiceAssignment.technician_id == technician.id, ServiceAssignment.status.in_(("assigned", "ready", "in_service"))).order_by(ServiceAssignment.assigned_at, ServiceAssignment.id)).all()
    items = []
    for assignment in assignments:
        order = db.get(ServiceOrder, assignment.service_order_id)
        visit = db.get(Visit, order.visit_id) if order else None
        room = db.get(Room, assignment.room_id)
        occupancy = db.scalar(select(PositionOccupancy).where(PositionOccupancy.store_id == technician.store_id, PositionOccupancy.selection_session_id == visit.selection_session_id)) if visit and visit.selection_session_id else None
        if order and visit and room and occupancy and visit.store_id == technician.store_id:
            items.append({"service_order_id": order.id, "assignment_id": assignment.id, "occupancy_id": occupancy.id, "user_id": visit.user_id, "selection_session_id": visit.selection_session_id, "assignment_status": assignment.status, "service_order_status": order.status, "occupancy_status": occupancy.status, "room_name": room.name, "items": order.items or []})
    return {"items": items}


def _technician_occupancy(db: Session, occupancy_id: int, technician: Technician) -> PositionOccupancy:
    occupancy = db.get(PositionOccupancy, occupancy_id)
    assignment = db.scalar(select(ServiceAssignment).join(ServiceOrder, ServiceOrder.id == ServiceAssignment.service_order_id).join(Visit, Visit.id == ServiceOrder.visit_id).where(ServiceAssignment.technician_id == technician.id, ServiceAssignment.store_id == technician.store_id, Visit.selection_session_id == occupancy.selection_session_id if occupancy else False))
    if not occupancy or not assignment:
        raise HTTPException(status_code=404, detail="服务任务不存在")
    return occupancy


def _occupancy_action(occupancy: PositionOccupancy, action: str) -> None:
    if action == "confirm":
        if occupancy.status == "waiting_service":
            occupancy.status = "in_service"
            occupancy.actual_start_at = datetime.now(timezone.utc)
            occupancy.version += 1
            return
        if occupancy.status == "in_service":
            return
    if action == "finish":
        if occupancy.status in {"waiting_service", "in_service"}:
            occupancy.status = "post_service_present"
            occupancy.actual_service_end_at = datetime.now(timezone.utc)
            occupancy.version += 1
            return
        if occupancy.status == "post_service_present":
            return
    raise HTTPException(status_code=409, detail="服务状态不允许此操作")


def _action(occupancy_id: int, action: str, body: ActionIn, authorization: str | None, db: Session) -> dict:
    staff, technician = current_technician(authorization, db)
    replay = db.scalar(select(StateTransition).where(StateTransition.store_id == technician.store_id, StateTransition.idempotency_key == body.idempotency_key))
    if replay:
        return replay.result_snapshot
    occupancy = _technician_occupancy(db, occupancy_id, technician)
    before = occupancy.status
    _occupancy_action(occupancy, action)
    result = {"occupancy_id": occupancy.id, "status": occupancy.status, "version": occupancy.version}
    db.add(StateTransition(store_id=technician.store_id, entity_type="position_occupancy", entity_id=str(occupancy.id), action=action, from_status=before, to_status=occupancy.status, actor_type="staff", actor_id=str(staff.id), actor_role=staff.role, idempotency_key=body.idempotency_key, request_hash=hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest(), result_snapshot=result))
    db.add(AuditLog(actor_type="staff", actor_id=str(staff.id), store_id=technician.store_id, action=f"technician_{action}_service", entity_type="position_occupancy", entity_id=str(occupancy.id), detail={"from_status": before, "to_status": occupancy.status, "note": body.note}))
    db.commit()
    return result


@router.post("/occupancies/{occupancy_id}/confirm")
def confirm_service(occupancy_id: int, body: ActionIn, authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    return _action(occupancy_id, "confirm", body, authorization, db)


@router.post("/occupancies/{occupancy_id}/finish")
def finish_service(occupancy_id: int, body: ActionIn, authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    return _action(occupancy_id, "finish", body, authorization, db)


@router.post("/leave-requests")
def create_leave_request(body: LeaveRequestIn, authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    _, technician = current_technician(authorization, db)
    if body.end_date < body.start_date:
        raise HTTPException(status_code=422, detail="结束日期不能早于开始日期")
    overlap = db.scalar(select(TechnicianLeaveRequest).where(TechnicianLeaveRequest.technician_id == technician.id, TechnicianLeaveRequest.status.in_(("submitted", "approved")), TechnicianLeaveRequest.start_date <= body.end_date, TechnicianLeaveRequest.end_date >= body.start_date))
    if overlap:
        raise HTTPException(status_code=409, detail="请假时段与已有申请重叠")
    request = TechnicianLeaveRequest(store_id=technician.store_id, technician_id=technician.id, start_date=body.start_date, end_date=body.end_date, reason=body.reason.strip())
    db.add(request)
    db.commit()
    return {"id": request.id, "status": request.status}
