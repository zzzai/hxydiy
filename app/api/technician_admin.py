from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin import _current_staff, _staff_store_id, hash_password, normalize_staff_role
from app.db.session import get_db
from app.models import AuditLog, Staff
from app.models.operations import Technician
from app.models.service import ServiceAssignment
from app.models.technician_portal import TechnicianInvite, TechnicianLeaveRequest
from app.api.technician import invite_expiry, make_invite_token, token_hash

router = APIRouter(prefix="/admin/v2", tags=["technician-lifecycle"])


def require_admin(authorization: str | None, db: Session) -> Staff:
    staff = _current_staff(authorization, db)
    if normalize_staff_role(staff.role, staff.technician_id) != "manager":
        raise HTTPException(status_code=403, detail={"code": "MANAGER_REQUIRED", "message": "仅店长可操作"})
    _staff_store_id(staff)
    return staff


def audit(db: Session, staff: Staff, action: str, entity_id: int, detail: dict) -> None:
    db.add(AuditLog(actor_type="staff", actor_id=str(staff.id), store_id=staff.store_id, action=action, entity_type="technician", entity_id=str(entity_id), detail=detail))


@router.post("/technicians/{tech_id}/invite")
def invite_technician(tech_id: int, authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    admin = require_admin(authorization, db)
    technician = db.get(Technician, tech_id)
    if not technician or technician.store_id != admin.store_id:
        raise HTTPException(status_code=404, detail="技师不存在")
    if technician.status == "resigned":
        raise HTTPException(status_code=409, detail="已离职技师不能发送邀请")
    staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
    if staff and staff.status == "active":
        raise HTTPException(status_code=409, detail="该技师已有可用登录账号")
    if staff is None:
        staff = Staff(username=f"tech-{technician.id}", password_hash=hash_password(make_invite_token()), name=technician.name, role="technician", status="invited", store_id=technician.store_id, technician_id=technician.id)
        db.add(staff)
        db.flush()
    else:
        staff.status = "invited"
        staff.name = technician.name
    previous = db.scalar(select(TechnicianInvite).where(TechnicianInvite.technician_id == technician.id))
    if previous:
        db.delete(previous)
        db.flush()
    token = make_invite_token()
    invite = TechnicianInvite(store_id=technician.store_id, technician_id=technician.id, staff_id=staff.id, token_hash=token_hash(token), expires_at=invite_expiry(), created_by_staff_id=admin.id)
    db.add(invite)
    audit(db, admin, "invite_technician", technician.id, {"staff_id": staff.id, "expires_at": invite.expires_at.isoformat()})
    db.commit()
    return {"technician_id": technician.id, "username": staff.username, "token": token, "expires_at": invite.expires_at.isoformat()}


@router.get("/technician-leave-requests")
def list_leave_requests(status: str | None = None, authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    admin = require_admin(authorization, db)
    query = select(TechnicianLeaveRequest).where(TechnicianLeaveRequest.store_id == admin.store_id)
    if status:
        query = query.where(TechnicianLeaveRequest.status == status)
    rows = db.scalars(query.order_by(TechnicianLeaveRequest.created_at.desc(), TechnicianLeaveRequest.id.desc())).all()
    technicians = {t.id: t for t in db.scalars(select(Technician).where(Technician.store_id == admin.store_id)).all()}
    return {"items": [{"id": row.id, "technician_id": row.technician_id, "technician_name": technicians.get(row.technician_id).name if row.technician_id in technicians else "", "start_date": row.start_date.isoformat(), "end_date": row.end_date.isoformat(), "reason": row.reason, "status": row.status, "review_note": row.review_note} for row in rows]}


@router.post("/technician-leave-requests/{request_id}/approve")
def approve_leave_request(request_id: int, body: dict | None = None, authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    admin = require_admin(authorization, db)
    request = db.get(TechnicianLeaveRequest, request_id)
    if not request or request.store_id != admin.store_id:
        raise HTTPException(status_code=404, detail="请假申请不存在")
    if request.status != "submitted":
        raise HTTPException(status_code=409, detail="请假申请状态已变更")
    technician = db.get(Technician, request.technician_id)
    if not technician or technician.status == "resigned":
        raise HTTPException(status_code=409, detail="技师当前不可审批请假")
    request.status = "approved"
    request.reviewed_by_staff_id = admin.id
    request.reviewed_at = datetime.now(timezone.utc)
    request.review_note = str((body or {}).get("review_note") or "").strip()[:500]
    technician.status = "off"
    audit(db, admin, "approve_technician_leave", technician.id, {"request_id": request.id})
    db.commit()
    return {"id": request.id, "status": request.status, "technician_status": technician.status}


@router.post("/technicians/{tech_id}/resign")
def resign_technician(tech_id: int, body: dict | None = None, authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    admin = require_admin(authorization, db)
    technician = db.get(Technician, tech_id)
    if not technician or technician.store_id != admin.store_id:
        raise HTTPException(status_code=404, detail="技师不存在")
    active = db.scalar(select(ServiceAssignment).where(ServiceAssignment.store_id == admin.store_id, ServiceAssignment.technician_id == technician.id, ServiceAssignment.status.in_(("assigned", "ready", "in_service"))))
    if active:
        raise HTTPException(status_code=409, detail="存在进行中或待服务任务，完成交接后才能离职")
    technician.status = "resigned"
    staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
    if staff:
        staff.status = "disabled"
    audit(db, admin, "resign_technician", technician.id, {"reason": str((body or {}).get("reason") or "").strip()[:256], "staff_id": staff.id if staff else None})
    db.commit()
    return {"id": technician.id, "status": technician.status}
