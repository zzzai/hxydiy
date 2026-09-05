import hashlib
import json
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import String, and_, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.api.admin import _current_staff, create_staff_token, hash_password, normalize_staff_role
from app.db.session import get_db
from app.models import AuditLog, CustomerProfileRecord, PositionOccupancy, SelectionSession, Staff, User
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
    "occupation_contexts": {"desk_work": "久坐办公", "standing_work": "久站服务", "frequent_driving": "经常驾驶", "physical_labor": "体力劳动", "family_care": "照护家庭", "freelance": "自由职业", "retired": "退休", "other": "其他"},
    "personal_context": {
        "age_band": {"18_24": "18-24岁", "25_34": "25-34岁", "35_44": "35-44岁", "45_54": "45-54岁", "55_64": "55-64岁", "65_plus": "65岁以上"},
        "build": {"slim": "偏瘦", "balanced": "匀称", "sturdy": "偏壮"},
        "height_band": {"shorter": "偏矮", "average": "适中", "taller": "偏高"},
    },
    "work_lifestyle": {"sleep_quality": {"good": "良好", "average": "一般", "poor": "较差"}},
    "service_related_context": {"contexts": {"long_term_condition": "顾客提及长期身体情况", "recent_discomfort_recovery": "顾客提及近期不适或恢复情况", "skin_sensitivity": "顾客提及皮肤敏感或接触偏好", "medication_mentioned": "顾客提及正在用药", "pregnancy_postpartum": "顾客提及孕期或产后阶段", "other_reconfirm": "其他需再次确认的情况"}},
    "session_response": {"relaxation": {"quick": "较快", "gradual": "逐渐", "tense": "始终较紧张"}},
    "communication_consumption": {
        "decision_priorities": {"price": "价格", "quality": "品质", "environment": "环境", "efficiency": "效率", "fixed_technician": "固定技师", "fixed_time": "固定时段"},
        "budget_preference": {"value": "实惠优先", "balanced": "平衡", "experience": "体验优先", "unexpressed": "未表达"},
    },
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
            _supported_reference_version(),
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

    safe_record = {
        "focus_areas": [],
        "avoid_areas": [],
        **(_history_profile_summary(record) or {}),
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


def _resolve_legacy_service_owner(db: Session, occupancy: PositionOccupancy) -> int | None:
    audits = db.scalars(select(AuditLog).where(
        AuditLog.entity_type == "position_occupancy",
        AuditLog.entity_id == str(occupancy.id),
        AuditLog.action.in_(("technician_confirm_service", "technician_finish_service")),
    )).all()
    owners = set()
    for audit in audits:
        actor = db.scalar(select(Staff).where(
            func.cast(Staff.id, String) == audit.actor_id,
        )) if audit.actor_type == "staff" else None
        technician = db.get(Technician, actor.technician_id) if actor and actor.technician_id else None
        if not technician or audit.store_id != occupancy.store_id or actor.store_id != occupancy.store_id or technician.store_id != occupancy.store_id:
            return None
        owners.add(technician.id)
    return next(iter(owners)) if len(owners) == 1 else None


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
    if occupancy.serviced_by_technician_id is None and occupancy.status == "in_service":
        owner = _resolve_legacy_service_owner(db, occupancy)
        if owner is None:
            raise HTTPException(status_code=409, detail={
                "code": "TECHNICIAN_SERVICE_OWNER_UNRESOLVED",
                "message": "旧服务无法唯一核对技师，请联系店长核对后通过管理端结束服务",
            })
        occupancy.serviced_by_technician_id = owner
        db.flush()
    if action == "confirm":
        owner_claim = db.execute(
            update(PositionOccupancy)
            .where(
                PositionOccupancy.id == occupancy.id,
                PositionOccupancy.store_id == technician.store_id,
                PositionOccupancy.serviced_by_technician_id.is_(None),
                PositionOccupancy.status == "waiting_service",
            )
            .values(serviced_by_technician_id=technician.id)
            .execution_options(synchronize_session=False)
        )
        if owner_claim.rowcount:
            occupancy.serviced_by_technician_id = technician.id
        else:
            # The conditional update is the concurrency boundary. Refresh before
            # deciding whether this is the same technician's idempotent action.
            db.refresh(occupancy)
        if occupancy.serviced_by_technician_id != technician.id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "TECHNICIAN_SERVICE_OWNER_MISMATCH",
                    "message": "该服务已由其他技师确认",
                },
            )
    elif action == "finish" and occupancy.serviced_by_technician_id != technician.id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TECHNICIAN_SERVICE_OWNER_MISMATCH",
                "message": "仅实际确认服务的技师可以结束服务",
            },
        )
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


def _supported_reference_version():
    return or_(
        and_(CustomerProfileRecord.schema_version == 2, CustomerProfileRecord.taxonomy_version == "service_reference_v1"),
        and_(CustomerProfileRecord.schema_version == 3, CustomerProfileRecord.taxonomy_version == "service_reference_v2"),
    )


def _not_superseded_reference():
    correction = aliased(CustomerProfileRecord)
    return ~exists().where(
        correction.correction_of_id == CustomerProfileRecord.id,
        correction.store_id == CustomerProfileRecord.store_id,
        correction.user_id == CustomerProfileRecord.user_id,
    )


def _safe_reference_profile(value) -> dict:
    # Validate each container and leaf before label lookup. Historical JSON may
    # predate validation; never stringify arbitrary values or trust nested shape.
    shape = {
        "customer_reported": {
            "focus_areas": list, "avoid_areas": list,
            "force_preference": str, "temperature_preference": str,
            "work_lifestyle": {"occupation_contexts": list},
            "communication_consumption": {"decision_priorities": list, "budget_preference": str},
        },
        "technician_observed": {"service_feedback": str, "session_response": {"relaxation": str}},
        "next_visit": {"plan": str},
    }

    def project(node, allowed):
        node = node if isinstance(node, dict) else {}
        result = {}
        for key, kind in allowed.items():
            item = node.get(key)
            if isinstance(kind, dict):
                result[key] = project(item, kind)
            elif kind is list:
                result[key] = [code for code in item if isinstance(code, str)] if isinstance(item, list) else []
            else:
                result[key] = item if isinstance(item, str) else None
        return result

    return project(value, shape)


def _history_profile_summary(record: CustomerProfileRecord | None) -> dict | None:
    if record is None:
        return None
    profile = _safe_reference_profile(record.profile)
    if record.schema_version == 2 and record.taxonomy_version == "service_reference_v1":
        reported = profile.get("customer_reported") or {}
        observed = profile.get("technician_observed") or {}
        next_visit = profile.get("next_visit") or {}
        area_labels = SERVICE_REFERENCE_LABELS["areas"]
        summary = {
            "schema_version": 2,
            "taxonomy_version": "service_reference_v1",
            "focus_areas": [
                area_labels[code]
                for code in reported.get("focus_areas", [])
                if code in area_labels
            ],
            "avoid_areas": [
                area_labels[code]
                for code in reported.get("avoid_areas", [])
                if code in area_labels
            ],
            "force_preference": SERVICE_REFERENCE_LABELS["force"].get(
                reported.get("force_preference")
            ),
            "temperature_preference": SERVICE_REFERENCE_LABELS["temperature"].get(
                reported.get("temperature_preference")
            ),
            "service_feedback": SERVICE_REFERENCE_LABELS["feedback"].get(
                observed.get("service_feedback")
            ),
            "next_visit_plan": SERVICE_REFERENCE_LABELS["next_visit"].get(
                next_visit.get("plan")
            ),
        }
        return summary
    if record.schema_version == 3 and record.taxonomy_version == "service_reference_v2":
        reported = profile.get("customer_reported") or {}
        lifestyle = reported.get("work_lifestyle") or {}
        consumption = reported.get("communication_consumption") or {}
        observed = profile.get("technician_observed") or {}
        response = observed.get("session_response") or {}
        area_labels = SERVICE_REFERENCE_LABELS["areas"]
        summary = {
            "schema_version": 3,
            "taxonomy_version": "service_reference_v2",
            "focus_areas": [area_labels[code] for code in reported.get("focus_areas", []) if code in area_labels],
            "avoid_areas": [area_labels[code] for code in reported.get("avoid_areas", []) if code in area_labels],
            "force_preference": SERVICE_REFERENCE_LABELS["force"].get(reported.get("force_preference")),
            "temperature_preference": SERVICE_REFERENCE_LABELS["temperature"].get(reported.get("temperature_preference")),
            "occupation_contexts": [
                SERVICE_REFERENCE_V2_TAXONOMY["occupation_contexts"][code]
                for code in lifestyle.get("occupation_contexts", [])
                if code in SERVICE_REFERENCE_V2_TAXONOMY["occupation_contexts"]
            ],
            "relaxation": SERVICE_REFERENCE_V2_TAXONOMY["session_response"]["relaxation"].get(
                response.get("relaxation")
            ),
            "service_feedback": SERVICE_REFERENCE_LABELS["feedback"].get(observed.get("service_feedback")),
            "next_visit_plan": SERVICE_REFERENCE_LABELS["next_visit"].get((profile.get("next_visit") or {}).get("plan")),
            "decision_priorities": [
                SERVICE_REFERENCE_V2_TAXONOMY["communication_consumption"]["decision_priorities"][code]
                for code in consumption.get("decision_priorities", [])
                if code in SERVICE_REFERENCE_V2_TAXONOMY["communication_consumption"]["decision_priorities"]
            ],
            "budget_preference": SERVICE_REFERENCE_V2_TAXONOMY["communication_consumption"]["budget_preference"].get(consumption.get("budget_preference")),
        }
        return {key: value for key, value in summary.items() if value not in (None, [], "")}
    return None


@router.get("/service-history")
def service_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    profile_status: str = Query(default="all"),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    _, technician = current_technician(authorization, db)
    if profile_status not in {"all", "confirmed", "pending"}:
        raise HTTPException(status_code=422, detail="画像状态筛选值不合法")

    confirmed_profile = exists().where(
        CustomerProfileRecord.store_id == PositionOccupancy.store_id,
        CustomerProfileRecord.selection_session_id == PositionOccupancy.selection_session_id,
        CustomerProfileRecord.technician_id == PositionOccupancy.serviced_by_technician_id,
        _supported_reference_version(),
        _not_superseded_reference(),
        CustomerProfileRecord.customer_confirmed.is_(True),
    )
    conditions = [
        PositionOccupancy.store_id == technician.store_id,
        PositionOccupancy.serviced_by_technician_id == technician.id,
        PositionOccupancy.actual_service_end_at.is_not(None),
    ]
    if profile_status == "confirmed":
        conditions.append(confirmed_profile)
    elif profile_status == "pending":
        conditions.append(~confirmed_profile)

    total = db.scalar(select(func.count(PositionOccupancy.id)).where(*conditions)) or 0
    unassigned_legacy_count = db.scalar(select(func.count(PositionOccupancy.id)).where(
        PositionOccupancy.store_id == technician.store_id,
        PositionOccupancy.serviced_by_technician_id.is_(None),
        PositionOccupancy.actual_service_end_at.is_not(None),
    )) or 0
    rows = db.execute(
        select(PositionOccupancy, SelectionSession, Room, User)
        .join(SelectionSession, SelectionSession.id == PositionOccupancy.selection_session_id)
        .join(Room, Room.id == PositionOccupancy.room_id)
        .outerjoin(User, User.id == SelectionSession.customer_id)
        .where(*conditions)
        .order_by(PositionOccupancy.actual_service_end_at.desc(), PositionOccupancy.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = []
    for occupancy, session, room, customer in rows:
        record = db.scalar(
            select(CustomerProfileRecord)
            .where(
                CustomerProfileRecord.store_id == technician.store_id,
                CustomerProfileRecord.selection_session_id == session.id,
                CustomerProfileRecord.technician_id == technician.id,
                _supported_reference_version(),
                _not_superseded_reference(),
                CustomerProfileRecord.customer_confirmed.is_(True),
            )
            .order_by(CustomerProfileRecord.created_at.desc(), CustomerProfileRecord.id.desc())
            .limit(1)
        )
        project_names = []
        for selection_item in session.items or []:
            name = selection_item.get("name")
            if isinstance(name, str) and name.strip() and name.strip() not in project_names:
                project_names.append(name.strip())
        duration_minutes = None
        if occupancy.actual_start_at and occupancy.actual_service_end_at:
            duration_minutes = max(
                0,
                int((occupancy.actual_service_end_at - occupancy.actual_start_at).total_seconds() // 60),
            )
        items.append({
            "occupancy_id": occupancy.id,
            "completed_at": occupancy.actual_service_end_at,
            "duration_minutes": duration_minutes,
            "profile_status": "confirmed" if record else "pending",
            "customer": {"display_name": f"顾客 #{customer.id}"} if customer else {"display_name": "匿名顾客"},
            "projects": project_names,
            "service_position": room.name,
            "profile_summary": _history_profile_summary(record),
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size, "unassigned_legacy_count": unassigned_legacy_count}


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
