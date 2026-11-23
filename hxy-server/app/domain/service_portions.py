from datetime import UTC, datetime
from hashlib import sha256
import re

from pydantic import BaseModel, Field

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import AuditLog, PositionOccupancy, Project, SelectionSession, ServiceLine, Staff, Technician
from app.models.service import ServiceAssignment, ServiceOrder, StateTransition, Visit


ENTITY = "selection_portion"


def registered_staff(store_id: int):
    return select(Technician).join(Staff, Staff.technician_id == Technician.id).where(
        Technician.store_id == store_id, Staff.store_id == store_id, Staff.status == "active",
        Technician.status.in_(("available", "busy")),
    ).order_by(Technician.sort_order, Technician.id)


def can_request(technician: Technician, project_id: int) -> bool:
    return isinstance(technician.skills, list) and any(
        type(skill) in (str, int) and str(skill) == str(project_id) for skill in technician.skills
    )


def candidate(db: Session, store_id: int, project_id: int, technician_id: int) -> Technician:
    technician = db.scalar(registered_staff(store_id).where(Technician.id == technician_id))
    project = db.get(Project, project_id)
    if (not technician or not project or project.store_id != store_id or not project.independently_visible
            or project.publication_status != "published" or not can_request(technician, project_id)):
        raise HTTPException(409, "这位技师当前不能点选，请改选或选择门店安排")
    return technician


def public_label(technician: Technician) -> str:
    label = (technician.name or "").strip()
    if label and not re.search(r"[0-9]{7,}|@", label):
        return label
    return f"技师 {technician.id}"


def entity_key(session_id: str, key: str) -> str:
    return sha256(f"{session_id}/{key}".encode()).hexdigest()


def portions_view(db: Session, session: SelectionSession) -> list[dict]:
    groups = {}
    for item in session.items or []:
        key = item.get("service_key")
        if key:
            groups.setdefault(key, []).append(item)
    if not groups:
        return []
    legacy = [item for item in session.items if not item.get("service_key")]
    if legacy:
        groups["legacy"] = legacy
    keys = {entity_key(session.id, key): key for key in groups}
    events = db.scalars(select(StateTransition).where(
        StateTransition.store_id == session.store_id, StateTransition.entity_type == ENTITY,
        StateTransition.entity_id.in_(keys),
    ).order_by(StateTransition.id))
    latest = {keys[event.entity_id]: event for event in events}
    views = []
    for key, items in groups.items():
        root = next((item for item in items if item.get("service_main")), None)
        if key == "legacy":
            root = {"project_id": None, "name": "原选单服务"}
        if not root:
            continue
        event = latest.get(key)
        choices = []
        for item in items:
            catalog = item.get("catalog_selection") or {}
            labels = [choice.get("name") or choice.get("choice_name") for choice in catalog.get("preference_snapshots") or []]
            choices.append({"name": item.get("name", ""), "preferences": list(dict.fromkeys(filter(None, [*(item.get("diy_preferences") or []), *labels])))})
        views.append({
            "key": key, "project_id": root["project_id"], "name": root["name"],
            "requested_technician_id": root.get("requested_technician_id"),
            "requested_label": root.get("requested_label"), "items": choices,
            "status": event.to_status if event else ("requested" if root.get("requested_technician_id") else "unassigned"),
            "technician_id": (event.after_snapshot or {}).get("technician_id") if event else None,
            "label": (event.after_snapshot or {}).get("label") if event else None,
            "version": event.id if event else 0,
        })
    if session.fulfillment_order_id:
        assignment = db.scalar(select(ServiceAssignment).join(
            ServiceOrder, ServiceOrder.id == ServiceAssignment.service_order_id
        ).join(Visit, Visit.id == ServiceOrder.visit_id).where(
            ServiceOrder.store_id == session.store_id, Visit.selection_session_id == session.id,
            ServiceAssignment.status.in_(("assigned", "ready", "in_service", "completed")),
        ).order_by(ServiceAssignment.id.desc()).limit(1))
        if assignment:
            actor = db.get(Technician, assignment.technician_id)
            for view in views:
                view.update(status="assigned" if assignment.status in {"ready", "assigned"} else assignment.status,
                            technician_id=assignment.technician_id, label=public_label(actor) if actor else None,
                            dispatched=True)
    return views


def ensure_free(db: Session, technician: Technician, own_key: str = "", occupancy_id: int | None = None, session_id: str | None = None) -> None:
    # Callers lock the technician before this check, including the legacy dispatch paths.
    latest = select(func.max(StateTransition.id)).where(
        StateTransition.store_id == technician.store_id, StateTransition.entity_type == ENTITY
    ).group_by(StateTransition.entity_id)
    reservation = select(StateTransition.id).where(
        StateTransition.id.in_(latest), StateTransition.entity_id != own_key,
        StateTransition.to_status.in_(("assigned", "in_service")),
        StateTransition.after_snapshot["technician_id"].as_integer() == technician.id,
        StateTransition.after_snapshot["session_id"].as_string().in_(select(SelectionSession.id).where(
            SelectionSession.store_id == technician.store_id, SelectionSession.status.in_(("submitted", "confirmed")),
            or_(~select(PositionOccupancy.id).where(PositionOccupancy.selection_session_id == SelectionSession.id).exists(),
                select(PositionOccupancy.id).where(PositionOccupancy.selection_session_id == SelectionSession.id,
                    PositionOccupancy.active_room_id.is_not(None),
                    PositionOccupancy.status.in_(("held", "waiting_service", "in_service"))).exists()),
        )),
    )
    if session_id:
        reservation = reservation.where(or_(
            StateTransition.after_snapshot["session_id"].as_string() != session_id,
            StateTransition.to_status == "in_service",
        ))
    if db.scalar(reservation.limit(1)):
        raise HTTPException(409, "这位技师已有服务安排，请稍后或换一位")
    if own_key:
        legacy = select(PositionOccupancy.id).where(
            PositionOccupancy.store_id == technician.store_id, PositionOccupancy.serviced_by_technician_id == technician.id,
            PositionOccupancy.status == "in_service",
        )
        if occupancy_id is not None:
            legacy = legacy.where(PositionOccupancy.id != occupancy_id)
        if db.scalar(legacy.limit(1)) or db.scalar(select(ServiceAssignment.id).where(
            ServiceAssignment.technician_id == technician.id, ServiceAssignment.status.in_(("assigned", "ready", "in_service")),
        ).limit(1)):
            raise HTTPException(409, "这位技师已有进行中的服务")


class PortionAction(BaseModel):
    version: int = Field(ge=0)


def change_portion(db: Session, store_id: int, session_id: str, key: str, action: str, version: int,
                   staff: Staff, technician: Technician | None = None) -> dict:
    # Serialize room edits before locking the person shared across different rooms.
    target = select(SelectionSession).where(SelectionSession.id == session_id, SelectionSession.store_id == store_id)
    session = db.scalar(target.with_for_update().execution_options(populate_existing=True))
    if not session:
        raise HTTPException(404, "服务单不存在")
    nominee = next((row.get("requested_technician_id") for row in session.items or []
                    if row.get("service_key") == key and row.get("service_main")), None)
    tech_id = technician.id if technician else nominee
    occupancy = db.scalar(select(PositionOccupancy).where(
        PositionOccupancy.selection_session_id == session_id, PositionOccupancy.store_id == store_id,
    ).order_by(PositionOccupancy.id.desc()).limit(1).with_for_update().execution_options(populate_existing=True))
    try:
        locked = db.scalar(select(Technician).where(Technician.store_id == store_id, Technician.id == tech_id)
                           .with_for_update(nowait=True).execution_options(populate_existing=True)) if tech_id else None
    except OperationalError as exc:
        if getattr(exc.orig, "sqlstate", None) != "55P03":
            raise
        db.rollback()
        raise HTTPException(409, "技师安排正在更新，请刷新后再试") from exc
    token = sha256(f"portion/{session_id}/{key}/{action}/{version}/{staff.id}".encode()).hexdigest()
    replay = db.scalar(select(StateTransition).where(StateTransition.store_id == store_id, StateTransition.idempotency_key == token))
    if replay:
        return replay.result_snapshot
    views = portions_view(db, session)
    portion = next((row for row in views if row["key"] == key), None)
    if not portion:
        raise HTTPException(404, "本份服务不存在")
    if session.status not in {"submitted", "confirmed"} or (occupancy and (
        occupancy.status not in {"waiting_service", "in_service"} or not occupancy.active_room_id
    )):
        raise HTTPException(409, "服务单当前不能操作")
    if portion.get("dispatched") or (session.fulfillment_order_id and action in {"start", "finish"}):
        raise HTTPException(409, "该服务单已进入派钟流程")
    if portion["version"] != version:
        raise HTTPException(409, "该份服务已有更新，请刷新")
    if action in {"confirm", "release"}:
        if portion["status"] not in ({"requested"} if action == "confirm" else {"requested", "assigned"}):
            raise HTTPException(409, "当前没有可处理的点名")
        if action == "confirm":
            if not locked or locked.id != portion["requested_technician_id"]:
                raise HTTPException(409, "点名信息已有更新")
            candidate(db, store_id, portion["project_id"], locked.id)
            ensure_free(db, locked, entity_key(session_id, key), occupancy.id if occupancy else None, session_id)
        state = "assigned" if action == "confirm" else "unassigned"
    else:
        if not occupancy or not locked or locked.status not in {"available", "busy"}:
            raise HTTPException(409, "请先安排服务位并确认在岗身份")
        if portion["technician_id"] and portion["technician_id"] != locked.id:
            raise HTTPException(403, "本份服务已安排其他技师")
        if action == "start" and portion["status"] in {"assigned", "unassigned"}:
            ensure_free(db, locked, entity_key(session_id, key), occupancy.id, session_id)
            state = "in_service"
        elif action == "finish" and portion["status"] == "in_service":
            state = "completed"
        else:
            raise HTTPException(409, "当前状态不能执行此操作")
    after = {"session_id": session_id, "technician_id": locked.id if locked and action != "release" else None,
             "label": public_label(locked) if locked and action != "release" else None}
    event = StateTransition(store_id=store_id, entity_type=ENTITY, entity_id=entity_key(session_id, key), action=action,
                            from_status=portion["status"], to_status=state, actor_type="staff", actor_id=str(staff.id),
                            actor_role=staff.role, idempotency_key=token, request_hash=token,
                            before_snapshot={"version": version}, after_snapshot=after)
    db.add(event)
    db.flush()
    if occupancy and action in {"start", "finish"}:
        from app.api.technician import _occupancy_action, _reject_conflicted_room_action
        _reject_conflicted_room_action(db, occupancy)
        now = datetime.now(UTC)
        for line in db.scalars(select(ServiceLine).where(ServiceLine.selection_session_id == session_id,
                ServiceLine.state.in_(("pending", "in_service"))).with_for_update()):
            if ((line.snapshot or {}).get("service_key") or "legacy") == key:
                line.state = state
                if action == "start":
                    line.started_at = now
                else:
                    line.completed_at = now
        if action == "start" and occupancy.status == "waiting_service":
            _occupancy_action(db, occupancy, "confirm")
        if action == "finish" and all(row["status"] == "completed" or row["key"] == key for row in views):
            _occupancy_action(db, occupancy, "finish")
            actors = {row["technician_id"] for row in views if row["key"] != key} | {locked.id}
            if len(actors) == 1:
                occupancy.serviced_by_technician_id = locked.id
                db.add(AuditLog(store_id=store_id, actor_type="staff", actor_id=str(staff.id),
                    action="technician_finish_service", entity_type="position_occupancy", entity_id=str(occupancy.id),
                    detail={"selection_session_id": session_id}))
    result = {"key": key, "status": state, "version": event.id, "technician_id": after["technician_id"], "label": after["label"]}
    event.result_snapshot = result
    db.commit()
    return result
