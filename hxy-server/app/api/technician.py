import hashlib
import json
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.admin import _current_staff, create_staff_token, hash_password, normalize_staff_role
from app.db.session import get_db
from app.models import AuditLog, CustomerProfileRecord, PositionOccupancy, SelectionSession, Staff
from app.models.operations import Room, Technician
from app.models.catalog import Addon, Project
from app.models.service import StateTransition
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
    if not technician or technician.store_id != staff.store_id or technician.status not in {"available", "busy"}:
        raise HTTPException(status_code=401, detail={"code": "TECHNICIAN_ACCOUNT_UNAVAILABLE", "message": "技师当前不在岗或账号不可用"})
    return staff, technician


@router.post("/activate")
def activate(body: ActivateIn, db: Session = Depends(get_db)) -> dict:
    invite = db.scalar(select(TechnicianInvite).where(TechnicianInvite.token_hash == token_hash(body.token)))
    now = datetime.now(timezone.utc)
    if not invite or invite.used_at is not None:
        raise HTTPException(status_code=400, detail={"code": "TECHNICIAN_INVITE_INVALID", "message": "激活凭证无效或已过期"})
    expires_at = invite.expires_at if invite.expires_at.tzinfo else invite.expires_at.replace(tzinfo=timezone.utc)
    if now >= expires_at:
        raise HTTPException(status_code=400, detail={"code": "TECHNICIAN_INVITE_INVALID", "message": "激活凭证无效或已过期"})
    staff = db.get(Staff, invite.staff_id)
    technician = db.get(Technician, invite.technician_id)
    if (
        not staff
        or not technician
        or staff.store_id != invite.store_id
        or technician.store_id != invite.store_id
        or staff.technician_id != technician.id
        or technician.status == "resigned"
    ):
        raise HTTPException(status_code=400, detail={"code": "TECHNICIAN_INVITE_INVALID", "message": "激活凭证无效或已过期"})
    staff.password_hash = hash_password(body.password)
    staff.status = "active"
    staff.role = "technician"
    invite.used_at = now
    db.add(AuditLog(actor_type="staff", actor_id=str(staff.id), store_id=staff.store_id, action="activate_technician", entity_type="technician", entity_id=str(technician.id), detail={"staff_id": staff.id, "invite_id": invite.id, "purpose": invite.purpose}))
    db.commit()
    return {"token": create_staff_token(staff.id, staff.role, staff.credentials_version), "staff": {"id": staff.id, "name": staff.name, "role": staff.role, "store_id": staff.store_id, "technician_id": staff.technician_id}}


@router.get("/me")
def me(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    staff, technician = current_technician(authorization, db)
    return {"staff": {"id": staff.id, "name": staff.name, "username": staff.username, "role": "technician", "status": staff.status, "store_id": staff.store_id, "technician_id": technician.id}, "technician": {"id": technician.id, "name": technician.name, "code": technician.code, "level": technician.level, "skills": technician.skills, "status": technician.status}}


@router.get("/tasks")
def tasks(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> dict:
    staff, technician = current_technician(authorization, db)
    completed_occupancy_ids = {
        row.entity_id for row in db.scalars(select(AuditLog).where(
            AuditLog.store_id == technician.store_id,
            AuditLog.actor_type == "staff",
            AuditLog.actor_id == str(staff.id),
            AuditLog.action == "technician_finish_service",
            AuditLog.entity_type == "position_occupancy",
        )).all()
    }
    # 技师端按现场区位展示：沙发是独立区位，房间以空间容器为一个区位。
    # 底层床位仅保留给占用、订单和审计，不向技师端暴露 A/B 床位。
    standalone_rooms = list(db.scalars(select(Room).where(
        Room.store_id == technician.store_id,
        Room.is_service_position.is_(True),
        Room.is_space_container.is_(False),
        Room.parent_room_id.is_(None),
        Room.operational_status == "active",
    ).order_by(Room.sort_order, Room.id)))
    room_containers = list(db.scalars(select(Room).where(
        Room.store_id == technician.store_id,
        Room.room_type == "room",
        Room.is_space_container.is_(True),
        Room.operational_status == "active",
    ).order_by(Room.sort_order, Room.id)))
    rooms = sorted([*standalone_rooms, *room_containers], key=lambda room: (room.sort_order, room.id))
    display_room_ids = {room.id for room in rooms}
    occupancies_by_room: dict[int, list[tuple[PositionOccupancy, SelectionSession]]] = {}
    if display_room_ids:
        active_rows = db.execute(
            select(PositionOccupancy, SelectionSession, Room)
            .join(SelectionSession, SelectionSession.id == PositionOccupancy.selection_session_id)
            .join(Room, Room.id == PositionOccupancy.room_id)
            .where(
                PositionOccupancy.store_id == technician.store_id,
                PositionOccupancy.status.in_(("waiting_service", "in_service", "post_service_present")),
                SelectionSession.status.in_(("submitted", "confirmed")),
            )
            .order_by(PositionOccupancy.id)
        ).all()
        for occupancy, session, occupied_room in active_rows:
            display_room_id = occupied_room.parent_room_id or occupied_room.id
            if display_room_id in display_room_ids:
                occupancies_by_room.setdefault(display_room_id, []).append((occupancy, session))

    items = []
    for room in rooms:
        room_occupancies = occupancies_by_room.get(room.id, [])
        if len(room_occupancies) > 1:
            items.append({"occupancy_id": None, "user_id": None, "selection_session_id": None, "occupancy_status": "conflict", "completed_by_me": False, "selection_status": None, "room_id": room.id, "room_name": room.name, "room_type": room.room_type, "room_status": room.status, "items": [], "conflict": True, "conflict_count": len(room_occupancies)})
            continue
        occupancy, session = room_occupancies[0] if room_occupancies else (None, None)
        items.append({
            "occupancy_id": occupancy.id if occupancy else None,
            "user_id": session.customer_id if session else None,
            "selection_session_id": session.id if session else None,
            "occupancy_status": occupancy.status if occupancy else "available",
            "completed_by_me": bool(occupancy and str(occupancy.id) in completed_occupancy_ids),
            "selection_status": session.status if session else None,
            "room_id": room.id,
            "room_name": room.name,
            "room_type": room.room_type,
            "room_status": room.status,
            "items": session.items or [] if session else [],
            "conflict": False,
            "conflict_count": 0,
        })
    return {"items": items}


def _technician_occupancy(db: Session, occupancy_id: int, technician: Technician) -> PositionOccupancy:
    occupancy = db.scalar(select(PositionOccupancy).where(PositionOccupancy.id == occupancy_id).with_for_update())
    session = db.get(SelectionSession, occupancy.selection_session_id) if occupancy else None
    if not occupancy or occupancy.store_id != technician.store_id or not session or session.store_id != technician.store_id:
        raise HTTPException(status_code=404, detail="服务任务不存在")
    return occupancy


SERVICE_REFERENCE_LABELS = {
    "areas": {
        "neck_shoulder": "肩颈", "waist_hip": "腰臀", "legs": "腿部",
        "abdomen": "腹部", "feet": "足部", "full_relaxation": "整体放松",
    },
    "force": {"gentle": "轻柔", "medium": "适中", "strong": "偏强"},
    "temperature": {"lower": "偏低", "medium": "适中", "higher": "偏高"},
    "feedback": {
        "suitable": "本次合适", "better_after_adjustment": "调整后更合适",
        "adjust_next_time": "下次需调整",
    },
    "next_visit": {"repeat_current": "延续本次", "confirm_on_arrival": "到店再确认"},
}


SERVICE_REFERENCE_V2_TAXONOMY = {
    "occupation_contexts": {"desk_work": "久坐办公", "standing_work": "久站服务"},
    "personal_context": {
        "age_band": {"25_34": "25-34岁"},
        "build": {"balanced": "匀称"},
    },
    "body_context": {"height_band": {"shorter": "偏矮", "average": "适中", "taller": "偏高"}},
    "work_lifestyle": {"sleep_quality": {"average": "一般"}},
    "service_related_context": {"contexts": {"medication_mentioned": "顾客提及正在用药"}},
    "session_response": {"relaxation": {"quick": "较快", "gradual": "逐渐", "tense": "始终较紧张"}},
}


@router.get("/service-reference-taxonomy")
def get_service_reference_taxonomy(
    authorization: str | None = Header(None), db: Session = Depends(get_db)
) -> dict:
    current_technician(authorization, db)
    return {"schema_version": 3, "taxonomy_version": "service_reference_v2", "groups": SERVICE_REFERENCE_V2_TAXONOMY}


@router.get("/occupancies/{occupancy_id}/service-reference")
def get_service_reference(
    occupancy_id: int,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    staff, technician = current_technician(authorization, db)
    occupancy = _technician_occupancy(db, occupancy_id, technician)
    if (
        occupancy.status not in {"waiting_service", "in_service", "post_service_present"}
        or occupancy.active_room_id != occupancy.room_id
        or occupancy.active_session_id != occupancy.selection_session_id
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "SERVICE_REFERENCE_UNAVAILABLE", "message": "当前服务位已不再活动"},
        )
    session = db.get(SelectionSession, occupancy.selection_session_id)
    if not session or session.status not in {"submitted", "confirmed"}:
        raise HTTPException(
            status_code=409,
            detail={"code": "SERVICE_REFERENCE_UNAVAILABLE", "message": "当前选单已不再活动"},
        )
    if session.customer_id is None:
        return {"record": None, "message": "暂无顾客确认的历史服务参考，请现场询问"}

    superseded_ids = select(CustomerProfileRecord.correction_of_id).where(
        CustomerProfileRecord.store_id == technician.store_id,
        CustomerProfileRecord.user_id == session.customer_id,
        CustomerProfileRecord.correction_of_id.is_not(None),
    )
    record = db.scalar(
        select(CustomerProfileRecord).where(
            CustomerProfileRecord.store_id == technician.store_id,
            CustomerProfileRecord.user_id == session.customer_id,
            CustomerProfileRecord.schema_version == 2,
            CustomerProfileRecord.taxonomy_version == "service_reference_v1",
            CustomerProfileRecord.customer_confirmed.is_(True),
            CustomerProfileRecord.id.not_in(superseded_ids),
            or_(
                CustomerProfileRecord.selection_session_id.is_(None),
                CustomerProfileRecord.selection_session_id != session.id,
            ),
        ).order_by(CustomerProfileRecord.created_at.desc(), CustomerProfileRecord.id.desc()).limit(1)
    )
    if record is None:
        return {"record": None, "message": "暂无顾客确认的历史服务参考，请现场询问"}

    profile = record.profile or {}
    reported = profile.get("customer_reported") or {}
    observed = profile.get("technician_observed") or {}
    next_visit = profile.get("next_visit") or {}
    area_labels = SERVICE_REFERENCE_LABELS["areas"]
    safe_record = {
        "focus_areas": [area_labels[code] for code in reported.get("focus_areas", []) if code in area_labels],
        "avoid_areas": [area_labels[code] for code in reported.get("avoid_areas", []) if code in area_labels],
        "force_preference": SERVICE_REFERENCE_LABELS["force"].get(reported.get("force_preference")),
        "temperature_preference": SERVICE_REFERENCE_LABELS["temperature"].get(reported.get("temperature_preference")),
        "service_feedback": SERVICE_REFERENCE_LABELS["feedback"].get(observed.get("service_feedback")),
        "next_visit_plan": SERVICE_REFERENCE_LABELS["next_visit"].get(next_visit.get("plan")),
        "recorded_date": record.created_at.date().isoformat() if record.created_at else None,
        "prompt": "请本次服务前再次确认",
    }
    db.add(AuditLog(
        actor_type="staff",
        actor_id=str(staff.id),
        store_id=technician.store_id,
        action="technician_view_service_reference",
        entity_type="position_occupancy",
        entity_id=str(occupancy.id),
        detail={
            "customer_id": session.customer_id,
            "technician_id": technician.id,
            "source_record_id": record.id,
        },
    ))
    db.commit()
    return {"record": safe_record, "message": "上次已确认服务参考"}


def _reject_conflicted_room_action(db: Session, occupancy: PositionOccupancy) -> None:
    occupied_room = db.get(Room, occupancy.room_id)
    if not occupied_room:
        return
    display_room_id = occupied_room.parent_room_id or occupied_room.id
    active_ids = db.scalars(
        select(PositionOccupancy.id)
        .join(SelectionSession, SelectionSession.id == PositionOccupancy.selection_session_id)
        .join(Room, Room.id == PositionOccupancy.room_id)
        .where(
            PositionOccupancy.store_id == occupancy.store_id,
            PositionOccupancy.status.in_(("waiting_service", "in_service", "post_service_present")),
            SelectionSession.status.in_(("submitted", "confirmed")),
            (Room.id == display_room_id) | (Room.parent_room_id == display_room_id),
        )
        .with_for_update()
    ).all()
    if len(active_ids) > 1:
        raise HTTPException(status_code=409, detail={"code": "POSITION_OCCUPANCY_CONFLICT", "message": "该房间存在多个活动服务记录，请联系店长核对现场服务位"})


def _selection_duration_minutes(db: Session, session: SelectionSession | None) -> int:
    """Use the submitted service snapshot to establish the timeout deadline."""
    if session is None:
        return 60
    total = 0
    for item in session.items or []:
        quantity = max(1, int(item.get("quantity") or 1))
        project_id = item.get("project_id")
        project = db.get(Project, project_id) if isinstance(project_id, int) else None
        if project and project.duration_min:
            total += int(project.duration_min) * quantity
        for addon_id in item.get("addon_ids", []):
            addon = db.get(Addon, addon_id)
            if addon and addon.duration_min:
                total += int(addon.duration_min) * quantity
        if item.get("item_kind") == "standalone_addon":
            addon = db.get(Addon, item.get("addon_id"))
            if addon and addon.duration_min:
                total += int(addon.duration_min) * quantity
    return max(total, 60)


def _occupancy_action(db: Session, occupancy: PositionOccupancy, action: str) -> None:
    if action == "confirm":
        if occupancy.status == "waiting_service":
            now = datetime.now(timezone.utc)
            session = db.get(SelectionSession, occupancy.selection_session_id)
            occupancy.status = "in_service"
            occupancy.actual_start_at = now
            occupancy.expected_end_at = now + timedelta(minutes=_selection_duration_minutes(db, session))
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
    occupancy = _technician_occupancy(db, occupancy_id, technician)
    request_hash = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
    replay = db.scalar(select(StateTransition).where(StateTransition.store_id == technician.store_id, StateTransition.idempotency_key == body.idempotency_key).with_for_update())
    if replay:
        # 幂等键只允许重放同一登录技师对同一服务位执行的同一动作。
        # 门店级唯一键用于防止并发重复写入，但不能把不同目标的请求误当成重试。
        if (
            replay.entity_type != "position_occupancy"
            or replay.entity_id != str(occupancy.id)
            or replay.action != action
            or replay.actor_type != "staff"
            or replay.actor_id != str(staff.id)
            or replay.request_hash != request_hash
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "IDEMPOTENCY_KEY_REUSED",
                    "message": "该幂等键已用于其他服务操作，请生成新的幂等键",
                },
            )
        return replay.result_snapshot
    _reject_conflicted_room_action(db, occupancy)
    before = occupancy.status
    _occupancy_action(db, occupancy, action)
    room = db.get(Room, occupancy.room_id)
    result = {"occupancy_id": occupancy.id, "status": occupancy.status, "service_status": occupancy.status, "resource_status": room.status if room else None, "resource_control": "external_read_only", "version": occupancy.version}
    db.add(StateTransition(store_id=technician.store_id, entity_type="position_occupancy", entity_id=str(occupancy.id), action=action, from_status=before, to_status=occupancy.status, actor_type="staff", actor_id=str(staff.id), actor_role=staff.role, idempotency_key=body.idempotency_key, request_hash=hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest(), result_snapshot=result))
    db.add(AuditLog(actor_type="staff", actor_id=str(staff.id), store_id=technician.store_id, action=f"technician_{action}_service", entity_type="position_occupancy", entity_id=str(occupancy.id), detail={"from_status": before, "to_status": occupancy.status, "selection_session_id": occupancy.selection_session_id, "note": body.note}))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = db.scalar(select(StateTransition).where(StateTransition.store_id == technician.store_id, StateTransition.idempotency_key == body.idempotency_key))
        if replay and replay.action == action and replay.entity_id == str(occupancy.id) and replay.actor_id == str(staff.id) and replay.request_hash == request_hash:
            return replay.result_snapshot
        raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_KEY_REUSED", "message": "该幂等键已用于其他服务操作，请生成新的幂等键"})
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
