from datetime import date as date_type, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.admin import _current_staff, _staff_store_id, hash_password, normalize_staff_role
from app.db.session import get_db
from app.models import AuditLog, Order, PositionOccupancy, Staff
from app.models.operations import Technician
from app.models.service import ServiceAssignment, ServiceOrder
from app.models.technician_portal import TechnicianInvite, TechnicianLeaveRequest, TechnicianShift
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


def _active_service_occupancy(db: Session, admin: Staff, technician: Technician) -> PositionOccupancy | None:
    staff = db.scalar(select(Staff).where(Staff.technician_id == technician.id))
    if not staff:
        return None
    entity_ids = [int(entity_id) for entity_id in db.scalars(select(AuditLog.entity_id).where(AuditLog.store_id == admin.store_id, AuditLog.actor_type == "staff", AuditLog.actor_id == str(staff.id), AuditLog.action == "technician_confirm_service", AuditLog.entity_type == "position_occupancy")).all() if str(entity_id).isdigit()]
    if not entity_ids:
        return None
    return db.scalar(select(PositionOccupancy).where(PositionOccupancy.store_id == admin.store_id, PositionOccupancy.id.in_(entity_ids), PositionOccupancy.status == "in_service").with_for_update())


def _leave_schedule_conflicts(
    db: Session,
    admin: Staff,
    technician: Technician,
    start_date,
    end_date,
) -> list[dict]:
    rows = db.execute(
        select(Order.order_no, Order.booking_date, Order.booking_time, ServiceAssignment.status)
        .join(ServiceOrder, ServiceOrder.order_id == Order.id)
        .join(ServiceAssignment, ServiceAssignment.service_order_id == ServiceOrder.id)
        .where(
            ServiceAssignment.store_id == admin.store_id,
            ServiceAssignment.technician_id == technician.id,
            ServiceAssignment.status.in_(("assigned", "ready", "in_service")),
            Order.booking_date.is_not(None),
            Order.booking_date >= start_date.isoformat(),
            Order.booking_date <= end_date.isoformat(),
        )
        .order_by(Order.booking_date, Order.booking_time)
    ).all()
    return [{
        "order_no": order_no,
        "booking_date": booking_date,
        "booking_time": booking_time,
        "assignment_status": status,
    } for order_no, booking_date, booking_time, status in rows]


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


@router.get("/technician-board")
def technician_board(
    day: str | None = Query(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    """Per-store on-duty board: leave, current bookings and next appointment."""
    admin = require_admin(authorization, db)
    try:
        board_date = date_type.fromisoformat(day) if day else datetime.now(ZoneInfo("Asia/Shanghai")).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")
    technicians = list(db.scalars(select(Technician).where(Technician.store_id == admin.store_id).order_by(Technician.id)))
    leaves = list(db.scalars(select(TechnicianLeaveRequest).where(
        TechnicianLeaveRequest.store_id == admin.store_id,
        TechnicianLeaveRequest.status == "approved",
        TechnicianLeaveRequest.start_date <= board_date,
        TechnicianLeaveRequest.end_date >= board_date,
    )))
    leave_by_tech = {leave.technician_id: leave for leave in leaves}
    assignment_rows = db.execute(
        select(
            ServiceAssignment.technician_id,
            func.count().label("booking_count"),
            func.min(Order.booking_time).label("next_booking_time"),
        )
        .join(ServiceOrder, ServiceOrder.id == ServiceAssignment.service_order_id)
        .join(Order, Order.id == ServiceOrder.order_id)
        .where(
            ServiceAssignment.store_id == admin.store_id,
            ServiceAssignment.status.in_(("assigned", "ready", "in_service")),
            Order.booking_date == board_date.isoformat(),
        )
        .group_by(ServiceAssignment.technician_id)
    ).all()
    booking_by_tech = {row.technician_id: row for row in assignment_rows}
    status_labels = {"available": "在岗", "busy": "服务中", "off": "休息", "resigned": "离职"}
    items = []
    for technician in technicians:
        if technician.status == "resigned":
            continue
        leave = leave_by_tech.get(technician.id)
        booking = booking_by_tech.get(technician.id)
        on_leave = leave is not None
        on_duty = not on_leave and technician.status in ("available", "busy")
        items.append({
            "id": technician.id,
            "name": technician.name,
            "code": technician.code,
            "status": technician.status,
            "status_label": "请假" if on_leave else status_labels.get(technician.status, technician.status),
            "on_duty": on_duty,
            "on_leave": on_leave,
            "leave_end": leave.end_date.isoformat() if leave else None,
            "booking_count": int(booking.booking_count) if booking else 0,
            "next_booking_time": booking.next_booking_time if booking else None,
        })
    return {
        "date": board_date.isoformat(),
        "summary": {
            "total": len(items),
            "on_duty": sum(1 for item in items if item["on_duty"]),
            "on_leave": sum(1 for item in items if item["on_leave"]),
            "booking_count": sum(item["booking_count"] for item in items),
        },
        "items": items,
    }


@router.get("/technician-shifts")
def list_technician_shifts(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    admin = require_admin(authorization, db)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    try:
        range_start = date_type.fromisoformat(start_date) if start_date else today - timedelta(days=today.weekday())
        range_end = date_type.fromisoformat(end_date) if end_date else range_start + timedelta(days=6)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")
    if range_end < range_start or (range_end - range_start).days > 62:
        raise HTTPException(status_code=400, detail="排班日期范围不合法")
    rows = list(db.scalars(select(TechnicianShift).where(
        TechnicianShift.store_id == admin.store_id,
        TechnicianShift.work_date >= range_start,
        TechnicianShift.work_date <= range_end,
    ).order_by(TechnicianShift.work_date, TechnicianShift.technician_id)))
    return {
        "start_date": range_start.isoformat(),
        "end_date": range_end.isoformat(),
        "items": [{
            "id": row.id,
            "technician_id": row.technician_id,
            "work_date": row.work_date.isoformat(),
            "shift_type": row.shift_type,
            "start_time": row.start_time,
            "end_time": row.end_time,
            "note": row.note,
        } for row in rows],
    }


@router.put("/technician-shifts")
def upsert_technician_shift(
    body: dict | None = None,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    admin = require_admin(authorization, db)
    payload = body or {}
    technician_id = payload.get("technician_id")
    try:
        technician_id = int(technician_id)
        work_date = date_type.fromisoformat(str(payload.get("work_date") or ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="技师和日期必填")
    technician = db.get(Technician, technician_id)
    if not technician or technician.store_id != admin.store_id:
        raise HTTPException(status_code=404, detail="技师不存在")
    shift_type = str(payload.get("shift_type") or "full")
    allowed_types = {"off", "full", "morning", "afternoon", "evening", "custom"}
    if shift_type not in allowed_types:
        raise HTTPException(status_code=400, detail="班次类型不合法")
    start_time = str(payload.get("start_time") or "").strip()[:5]
    end_time = str(payload.get("end_time") or "").strip()[:5]
    if shift_type == "custom" and (not start_time or not end_time):
        raise HTTPException(status_code=400, detail="自定义班次需要开始和结束时间")
    if shift_type in ("morning", "afternoon", "evening"):
        start_time, end_time = {"morning": ("09:00", "13:00"), "afternoon": ("13:00", "18:00"), "evening": ("18:00", "22:00")}[shift_type]
    if shift_type == "full":
        start_time, end_time = "09:00", "22:00"
    if shift_type == "off":
        start_time, end_time = "", ""

    leave = db.scalar(select(TechnicianLeaveRequest).where(
        TechnicianLeaveRequest.store_id == admin.store_id,
        TechnicianLeaveRequest.technician_id == technician_id,
        TechnicianLeaveRequest.status == "approved",
        TechnicianLeaveRequest.start_date <= work_date,
        TechnicianLeaveRequest.end_date >= work_date,
    ))
    if leave and shift_type != "off":
        raise HTTPException(status_code=409, detail={"code": "SHIFT_LEAVE_CONFLICT", "message": "该日期已有已批准的请假，不能排班"})
    if shift_type == "off":
        booking_count = db.scalar(
            select(func.count()).select_from(ServiceAssignment)
            .join(ServiceOrder, ServiceOrder.id == ServiceAssignment.service_order_id)
            .join(Order, Order.id == ServiceOrder.order_id)
            .where(
                ServiceAssignment.store_id == admin.store_id,
                ServiceAssignment.technician_id == technician_id,
                ServiceAssignment.status.in_(("assigned", "ready", "in_service")),
                Order.booking_date == work_date.isoformat(),
            )
        ) or 0
        if booking_count:
            raise HTTPException(status_code=409, detail={"code": "SHIFT_BOOKING_CONFLICT", "message": f"该日期仍有 {booking_count} 个已排服务，不能排休息"})

    row = db.scalar(select(TechnicianShift).where(
        TechnicianShift.technician_id == technician_id,
        TechnicianShift.work_date == work_date,
    ))
    if row is None:
        row = TechnicianShift(
            store_id=admin.store_id,
            technician_id=technician_id,
            work_date=work_date,
            created_by_staff_id=admin.id,
        )
        db.add(row)
    row.shift_type = shift_type
    row.start_time = start_time
    row.end_time = end_time
    row.note = str(payload.get("note") or "").strip()[:200]
    db.flush()
    audit(db, admin, "upsert_technician_shift", technician_id, {
        "shift_id": row.id,
        "work_date": work_date.isoformat(),
        "shift_type": shift_type,
    })
    db.commit()
    return {
        "id": row.id,
        "technician_id": technician_id,
        "work_date": work_date.isoformat(),
        "shift_type": shift_type,
        "start_time": start_time,
        "end_time": end_time,
        "note": row.note,
    }


@router.post("/technician-shifts/copy-week")
def copy_technician_shift_week(
    body: dict | None = None,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    admin = require_admin(authorization, db)
    payload = body or {}
    try:
        source_start = date_type.fromisoformat(str(payload.get("source_start") or ""))
        target_start = date_type.fromisoformat(str(payload.get("target_start") or ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="源周和目标周日期必填")
    if source_start.weekday() != 0 or target_start.weekday() != 0:
        raise HTTPException(status_code=400, detail="请使用周一作为周的起点")
    if source_start == target_start:
        raise HTTPException(status_code=400, detail="源周和目标周不能相同")
    overwrite = bool(payload.get("overwrite"))
    source_shifts = list(db.scalars(select(TechnicianShift).where(
        TechnicianShift.store_id == admin.store_id,
        TechnicianShift.work_date >= source_start,
        TechnicianShift.work_date <= source_start + timedelta(days=6),
    )))
    copied = 0
    skipped_existing = 0
    skipped_leave = 0
    skipped_booking = 0
    for source in source_shifts:
        target_date = target_start + timedelta(days=(source.work_date - source_start).days)
        existing = db.scalar(select(TechnicianShift).where(
            TechnicianShift.technician_id == source.technician_id,
            TechnicianShift.work_date == target_date,
        ))
        if existing and not overwrite:
            skipped_existing += 1
            continue
        if source.shift_type != "off":
            leave = db.scalar(select(TechnicianLeaveRequest).where(
                TechnicianLeaveRequest.store_id == admin.store_id,
                TechnicianLeaveRequest.technician_id == source.technician_id,
                TechnicianLeaveRequest.status == "approved",
                TechnicianLeaveRequest.start_date <= target_date,
                TechnicianLeaveRequest.end_date >= target_date,
            ))
            if leave:
                skipped_leave += 1
                continue
        if source.shift_type == "off":
            booking_count = db.scalar(
                select(func.count()).select_from(ServiceAssignment)
                .join(ServiceOrder, ServiceOrder.id == ServiceAssignment.service_order_id)
                .join(Order, Order.id == ServiceOrder.order_id)
                .where(
                    ServiceAssignment.store_id == admin.store_id,
                    ServiceAssignment.technician_id == source.technician_id,
                    ServiceAssignment.status.in_(("assigned", "ready", "in_service")),
                    Order.booking_date == target_date.isoformat(),
                )
            ) or 0
            if booking_count:
                skipped_booking += 1
                continue
        row = existing or TechnicianShift(
            store_id=admin.store_id,
            technician_id=source.technician_id,
            work_date=target_date,
            created_by_staff_id=admin.id,
        )
        if existing is None:
            db.add(row)
        row.shift_type = source.shift_type
        row.start_time = source.start_time
        row.end_time = source.end_time
        row.note = source.note
        copied += 1
    audit(db, admin, "copy_technician_shift_week", admin.id, {
        "source_start": source_start.isoformat(),
        "target_start": target_start.isoformat(),
        "copied": copied,
        "skipped_existing": skipped_existing,
        "skipped_leave": skipped_leave,
        "skipped_booking": skipped_booking,
    })
    db.commit()
    return {
        "source_start": source_start.isoformat(),
        "target_start": target_start.isoformat(),
        "copied": copied,
        "skipped_existing": skipped_existing,
        "skipped_leave": skipped_leave,
        "skipped_booking": skipped_booking,
    }


@router.delete("/technician-shifts/{shift_id}")
def delete_technician_shift(
    shift_id: int,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    admin = require_admin(authorization, db)
    row = db.get(TechnicianShift, shift_id)
    if not row or row.store_id != admin.store_id:
        raise HTTPException(status_code=404, detail="排班记录不存在")
    audit(db, admin, "delete_technician_shift", row.technician_id, {
        "shift_id": row.id,
        "work_date": row.work_date.isoformat(),
    })
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/technician-leave-requests/{request_id}/approve")
def approve_leave_request(request_id: int, body: dict | None = None, authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    admin = require_admin(authorization, db)
    request = db.get(TechnicianLeaveRequest, request_id)
    if not request or request.store_id != admin.store_id:
        raise HTTPException(status_code=404, detail="请假申请不存在")
    if request.status != "submitted":
        raise HTTPException(status_code=409, detail="请假申请状态已变更")
    if admin.technician_id and admin.technician_id == request.technician_id:
        raise HTTPException(status_code=403, detail={"code": "SELF_APPROVAL_FORBIDDEN", "message": "不能审批自己的请假申请，请由其他管理员处理"})
    technician = db.get(Technician, request.technician_id)
    if not technician or technician.status == "resigned":
        raise HTTPException(status_code=409, detail="技师当前不可审批请假")
    if _active_service_occupancy(db, admin, technician):
        raise HTTPException(status_code=409, detail={"code": "TECHNICIAN_ACTIVE_SERVICE", "message": "存在未结束的 DIY 服务，请完成服务交接后再审批"})
    conflicts = _leave_schedule_conflicts(db, admin, technician, request.start_date, request.end_date)
    if conflicts:
        raise HTTPException(status_code=409, detail={
            "code": "LEAVE_SCHEDULE_CONFLICT",
            "message": f"请假日期内仍有 {len(conflicts)} 个已排服务，请先改派或调整预约",
            "conflicts": conflicts[:10],
        })
    request.status = "approved"
    request.reviewed_by_staff_id = admin.id
    request.reviewed_at = datetime.now(timezone.utc)
    request.review_note = str((body or {}).get("review_note") or "").strip()[:500]
    technician.status = "off"
    audit(db, admin, "approve_technician_leave", technician.id, {"request_id": request.id})
    db.commit()
    return {"id": request.id, "status": request.status, "technician_status": technician.status}


@router.post("/technician-leave-requests/{request_id}/reject")
def reject_leave_request(request_id: int, body: dict | None = None, authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    admin = require_admin(authorization, db)
    request = db.get(TechnicianLeaveRequest, request_id)
    if not request or request.store_id != admin.store_id:
        raise HTTPException(status_code=404, detail="请假申请不存在")
    if request.status != "submitted":
        raise HTTPException(status_code=409, detail="请假申请状态已变更")
    if admin.technician_id and admin.technician_id == request.technician_id:
        raise HTTPException(status_code=403, detail={"code": "SELF_APPROVAL_FORBIDDEN", "message": "不能审批自己的请假申请，请由其他管理员处理"})
    review_note = str((body or {}).get("review_note") or "").strip()[:500]
    if len(review_note) < 2:
        raise HTTPException(status_code=400, detail="请填写至少 2 个字的驳回原因")
    request.status = "rejected"
    request.reviewed_by_staff_id = admin.id
    request.reviewed_at = datetime.now(timezone.utc)
    request.review_note = review_note
    audit(db, admin, "reject_technician_leave", request.technician_id, {"request_id": request.id, "review_note": review_note})
    db.commit()
    return {"id": request.id, "status": request.status}


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
    if _active_service_occupancy(db, admin, technician):
        raise HTTPException(status_code=409, detail={"code": "TECHNICIAN_ACTIVE_SERVICE", "message": "存在未结束的 DIY 服务，请完成服务交接后再离职"})
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
