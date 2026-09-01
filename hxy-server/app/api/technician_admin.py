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


def _request_key(raw: str | None) -> str | None:
    """Normalize the optional retry key without accepting unbounded header input."""
    if raw is None:
        return None
    value = raw.strip()
    if not 8 <= len(value) <= 128:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IDEMPOTENCY_KEY", "message": "幂等键长度应为 8-128 个字符"})
    return value


def _has_replayed_request(db: Session, admin: Staff, technician_id: int, action: str, request_key: str | None) -> bool:
    if not request_key:
        return False
    rows = db.scalars(select(AuditLog).where(
        AuditLog.store_id == admin.store_id,
        AuditLog.action == action,
        AuditLog.entity_type == "technician",
        AuditLog.entity_id == str(technician_id),
    )).all()
    return any((row.detail or {}).get("idempotency_key") == request_key for row in rows)


def _reject_replay(db: Session, admin: Staff, technician_id: int, action: str, request_key: str | None) -> None:
    if _has_replayed_request(db, admin, technician_id, action, request_key):
        raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_REPLAY", "message": "该请求已处理，请使用首次返回的结果"})


def _owned_technician(db: Session, admin: Staff, tech_id: int) -> Technician:
    technician = db.get(Technician, tech_id)
    if not technician or technician.store_id != admin.store_id:
        raise HTTPException(status_code=404, detail="技师不存在")
    return technician


def _invalidate_invite(db: Session, technician_id: int) -> None:
    previous = db.scalar(select(TechnicianInvite).where(TechnicianInvite.technician_id == technician_id))
    if previous:
        db.delete(previous)
        db.flush()


def _issue_invite(
    db: Session,
    admin: Staff,
    technician: Technician,
    purpose: str,
    *,
    staff: Staff | None = None,
) -> dict:
    if staff is None:
        staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
    if staff is None:
        staff = Staff(
            username=f"tech-{technician.id}",
            password_hash=hash_password(make_invite_token()),
            name=technician.name,
            role="technician",
            status="invited",
            store_id=technician.store_id,
            technician_id=technician.id,
            credentials_version=1,
        )
        db.add(staff)
        db.flush()
    else:
        staff.name = technician.name
        staff.role = "technician"
        staff.status = "invited"
        staff.store_id = technician.store_id
        staff.credentials_version = int(staff.credentials_version or 1) + 1
    _invalidate_invite(db, technician.id)
    token = make_invite_token()
    invite = TechnicianInvite(
        store_id=technician.store_id,
        technician_id=technician.id,
        staff_id=staff.id,
        token_hash=token_hash(token),
        purpose=purpose,
        expires_at=invite_expiry(),
        created_by_staff_id=admin.id,
    )
    db.add(invite)
    db.flush()
    return {"technician_id": technician.id, "staff_id": staff.id, "username": staff.username, "token": token, "expires_at": invite.expires_at.isoformat(), "login_status": "invited"}


@router.post("/technicians/{tech_id}/invite")
def invite_technician(tech_id: int, authorization: str | None = Header(None), idempotency_key: str | None = Header(None, alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    admin = require_admin(authorization, db)
    technician = _owned_technician(db, admin, tech_id)
    request_key = _request_key(idempotency_key)
    _reject_replay(db, admin, technician.id, "invite_technician", request_key)
    if technician.status == "resigned":
        raise HTTPException(status_code=409, detail="已离职技师不能发送邀请")
    staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
    if staff and staff.status == "active":
        raise HTTPException(status_code=409, detail="该技师已有可用登录账号")
    result = _issue_invite(db, admin, technician, "activate", staff=staff)
    audit(db, admin, "invite_technician", technician.id, {"staff_id": result["staff_id"], "expires_at": result["expires_at"], "purpose": "activate", "idempotency_key": request_key})
    db.commit()
    return result


@router.post("/technicians/{tech_id}/reset-login")
def reset_technician_login(tech_id: int, authorization: str | None = Header(None), idempotency_key: str | None = Header(None, alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    admin = require_admin(authorization, db)
    technician = _owned_technician(db, admin, tech_id)
    request_key = _request_key(idempotency_key)
    _reject_replay(db, admin, technician.id, "reset_technician_login", request_key)
    if technician.status == "resigned":
        raise HTTPException(status_code=409, detail={"code": "TECHNICIAN_RESIGNED", "message": "已离职技师请先返聘"})
    staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
    if not staff:
        raise HTTPException(status_code=409, detail={"code": "TECHNICIAN_LOGIN_NOT_OPENED", "message": "该技师尚未开通登录"})
    result = _issue_invite(db, admin, technician, "reset", staff=staff)
    audit(db, admin, "reset_technician_login", technician.id, {"staff_id": staff.id, "expires_at": result["expires_at"], "purpose": "reset", "idempotency_key": request_key})
    db.commit()
    return result


@router.post("/technicians/{tech_id}/disable")
def disable_technician_login(tech_id: int, authorization: str | None = Header(None), idempotency_key: str | None = Header(None, alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    admin = require_admin(authorization, db)
    technician = _owned_technician(db, admin, tech_id)
    request_key = _request_key(idempotency_key)
    if _has_replayed_request(db, admin, technician.id, "disable_technician_login", request_key):
        staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
        return {"technician_id": technician.id, "status": technician.status, "login_status": staff.status if staff else "disabled"}
    staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
    if not staff:
        raise HTTPException(status_code=409, detail={"code": "TECHNICIAN_LOGIN_NOT_OPENED", "message": "该技师尚未开通登录"})
    if staff.status != "disabled":
        staff.status = "disabled"
        staff.credentials_version = int(staff.credentials_version or 1) + 1
        _invalidate_invite(db, technician.id)
        audit(db, admin, "disable_technician_login", technician.id, {"staff_id": staff.id, "idempotency_key": request_key})
    db.commit()
    return {"technician_id": technician.id, "status": technician.status, "login_status": staff.status}


@router.post("/technicians/{tech_id}/restore")
def restore_technician_login(tech_id: int, authorization: str | None = Header(None), idempotency_key: str | None = Header(None, alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    admin = require_admin(authorization, db)
    technician = _owned_technician(db, admin, tech_id)
    request_key = _request_key(idempotency_key)
    if _has_replayed_request(db, admin, technician.id, "restore_technician_login", request_key):
        staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
        return {"technician_id": technician.id, "status": technician.status, "login_status": staff.status if staff else "disabled"}
    if technician.status == "resigned":
        raise HTTPException(status_code=409, detail={"code": "TECHNICIAN_RESIGNED", "message": "已离职技师请使用返聘并重新开通"})
    staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
    if not staff:
        raise HTTPException(status_code=409, detail={"code": "TECHNICIAN_LOGIN_NOT_OPENED", "message": "该技师尚未开通登录"})
    if staff.status != "active":
        staff.status = "active"
        staff.credentials_version = int(staff.credentials_version or 1) + 1
        _invalidate_invite(db, technician.id)
        audit(db, admin, "restore_technician_login", technician.id, {"staff_id": staff.id, "idempotency_key": request_key})
    db.commit()
    return {"technician_id": technician.id, "status": technician.status, "login_status": staff.status}


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
def resign_technician(tech_id: int, body: dict | None = None, authorization: str | None = Header(None), idempotency_key: str | None = Header(None, alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    admin = require_admin(authorization, db)
    technician = _owned_technician(db, admin, tech_id)
    request_key = _request_key(idempotency_key)
    if _has_replayed_request(db, admin, technician.id, "resign_technician", request_key):
        staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
        return {"id": technician.id, "status": technician.status, "login_status": staff.status if staff else "disabled"}
    if technician.status == "resigned":
        staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
        return {"id": technician.id, "status": technician.status, "login_status": staff.status if staff else "disabled"}
    active = db.scalar(select(ServiceAssignment).where(ServiceAssignment.store_id == admin.store_id, ServiceAssignment.technician_id == technician.id, ServiceAssignment.status.in_(("assigned", "ready", "in_service"))))
    if active:
        raise HTTPException(status_code=409, detail="存在进行中或待服务任务，完成交接后才能离职")
    technician.status = "resigned"
    staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
    if staff:
        staff.status = "disabled"
        staff.credentials_version = int(staff.credentials_version or 1) + 1
        _invalidate_invite(db, technician.id)
    audit(db, admin, "resign_technician", technician.id, {"reason": str((body or {}).get("reason") or "").strip()[:256], "staff_id": staff.id if staff else None, "idempotency_key": request_key})
    db.commit()
    return {"id": technician.id, "status": technician.status, "login_status": staff.status if staff else "disabled"}


@router.post("/technicians/{tech_id}/rehire")
def rehire_technician(tech_id: int, authorization: str | None = Header(None), idempotency_key: str | None = Header(None, alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    admin = require_admin(authorization, db)
    technician = _owned_technician(db, admin, tech_id)
    request_key = _request_key(idempotency_key)
    _reject_replay(db, admin, technician.id, "rehire_technician", request_key)
    if technician.status != "resigned":
        raise HTTPException(status_code=409, detail={"code": "TECHNICIAN_NOT_RESIGNED", "message": "技师当前不是离职状态"})
    technician.status = "available"
    staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
    result = _issue_invite(db, admin, technician, "activate", staff=staff)
    audit(db, admin, "rehire_technician", technician.id, {"staff_id": staff.id if staff else None, "expires_at": result["expires_at"], "purpose": "activate", "idempotency_key": request_key})
    db.commit()
    return {**result, "status": "invited", "technician_status": technician.status}
