"""服务位占用状态机和共享序列化逻辑。"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, PositionOccupancy, Room, SelectionSession


HOLD_TTL_MINUTES = 10
ACTIVE_STATUSES = {"held", "waiting_service", "in_service", "post_service_present", "cleaning"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def expire_stale_holds(db: Session, store_id: int | None = None) -> int:
    from app.domain.occupancy_release_policy import release_due_occupancies

    result = release_due_occupancies(
        db,
        utcnow(),
        store_id=store_id,
        statuses=("held",),
        trigger="lazy_request",
    )
    return result.released_count


def refresh_hold(db: Session, selection_session_id: str) -> PositionOccupancy | None:
    occupancy = db.scalar(select(PositionOccupancy).where(
        PositionOccupancy.active_session_id == selection_session_id,
    ))
    if occupancy and occupancy.status == "held":
        occupancy.hold_expires_at = utcnow() + timedelta(minutes=HOLD_TTL_MINUTES)
        occupancy.version += 1
    return occupancy


def release_occupancy(
    occupancy: PositionOccupancy,
    reason: str,
    *,
    now: datetime | None = None,
) -> None:
    now = now or utcnow()
    occupancy.status = "released"
    occupancy.active_room_id = None
    occupancy.active_session_id = None
    occupancy.hold_expires_at = None
    occupancy.retained_until = None
    occupancy.released_at = now
    occupancy.release_reason = reason
    occupancy.version += 1


def occupancy_view(occupancy: PositionOccupancy) -> dict:
    return {
        "id": occupancy.id,
        "store_id": occupancy.store_id,
        "room_id": occupancy.room_id,
        "selection_session_id": occupancy.selection_session_id,
        "active_room_id": occupancy.active_room_id,
        "active_session_id": occupancy.active_session_id,
        "status": occupancy.status,
        "source": occupancy.source,
        "hold_expires_at": aware(occupancy.hold_expires_at),
        "retained_until": aware(occupancy.retained_until),
        "expected_end_at": aware(occupancy.expected_end_at),
        "actual_start_at": aware(occupancy.actual_start_at),
        "actual_service_end_at": aware(occupancy.actual_service_end_at),
        "departed_at": aware(occupancy.departed_at),
        "released_at": aware(occupancy.released_at),
        "release_reason": occupancy.release_reason,
        "version": occupancy.version,
    }


def position_view(room: Room, occupancy: PositionOccupancy | None = None, *, current: bool = False) -> dict:
    if occupancy:
        state = occupancy.status
    elif room.operational_status != "active" or room.status != "available":
        state = "unavailable"
    else:
        state = "available"
    return {
        "id": room.id,
        "code": room.code,
        "name": room.name,
        "customer_label": room.customer_label or ("当前房间" if room.room_type == "room" else room.name),
        "type": room.room_type,
        "state": state,
        "is_current": current,
        "customer_selectable": room.customer_selectable,
        "operational_status": room.operational_status,
        "map_x": room.map_x,
        "map_y": room.map_y,
        "map_width": room.map_width,
        "map_height": room.map_height,
        "sort_order": room.sort_order,
        "occupancy": occupancy_view(occupancy) if occupancy else None,
    }


def audit_occupancy(
    db: Session,
    occupancy: PositionOccupancy,
    action: str,
    actor_type: str,
    actor_id: str,
    detail: dict,
) -> None:
    db.add(AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        store_id=occupancy.store_id,
        action=action,
        entity_type="position_occupancy",
        entity_id=str(occupancy.id),
        detail=detail,
    ))
