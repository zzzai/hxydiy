"""Safe release policy for abandoned customer service-position occupancies."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.occupancy import aware, audit_occupancy, release_occupancy
from app.models import (
    PositionOccupancy,
    Room,
    SelectionChangeRequest,
    SelectionRevision,
    SelectionSession,
)


WAITING_SERVICE_TTL_MINUTES = 60
SERVICE_END_GRACE_MINUTES = 30
SERVICE_DEFAULT_DURATION_MINUTES = 60


@dataclass(frozen=True)
class ReleaseCandidate:
    occupancy_id: int
    version: int
    room_id: int
    room_code: str
    status: str
    selection_session_id: str
    due_at: datetime
    overdue_seconds: int
    reason_code: str


@dataclass(frozen=True)
class CleanupResult:
    candidates: tuple[ReleaseCandidate, ...]
    released_ids: tuple[int, ...] = ()
    skipped: tuple[tuple[int, str], ...] = ()

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def released_count(self) -> int:
        return len(self.released_ids)

    @property
    def skipped_ids(self) -> tuple[int, ...]:
        return tuple(occupancy_id for occupancy_id, _ in self.skipped)


def waiting_deadline(
    occupancy: PositionOccupancy,
    session: SelectionSession,
) -> datetime | None:
    submitted_at = aware(session.submitted_at)
    if submitted_at is None:
        return None
    default_deadline = submitted_at + timedelta(minutes=WAITING_SERVICE_TTL_MINUTES)
    retained_until = aware(occupancy.retained_until)
    return max(default_deadline, retained_until) if retained_until else default_deadline


def service_deadline(occupancy: PositionOccupancy) -> datetime | None:
    """Return the timeout anchor, including compatibility for legacy rows."""
    expected_end = aware(occupancy.expected_end_at)
    if expected_end is not None:
        return expected_end + timedelta(minutes=SERVICE_END_GRACE_MINUTES)
    service_end = aware(occupancy.actual_service_end_at)
    if service_end is not None:
        return service_end + timedelta(minutes=SERVICE_END_GRACE_MINUTES)
    actual_start = aware(occupancy.actual_start_at)
    if actual_start is not None:
        return actual_start + timedelta(
            minutes=SERVICE_DEFAULT_DURATION_MINUTES + SERVICE_END_GRACE_MINUTES
        )
    return None


def _candidate(
    occupancy: PositionOccupancy,
    room: Room,
    session: SelectionSession,
    now: datetime,
    *,
    due_only: bool,
    allowed_statuses: frozenset[str],
) -> ReleaseCandidate | None:
    if occupancy.status not in allowed_statuses or occupancy.active_room_id != room.id:
        return None
    if session.fulfillment_order_id is not None:
        return None
    if occupancy.status in {"held", "waiting_service"} and occupancy.actual_start_at is not None:
        return None
    if occupancy.status == "held":
        if session.status not in {"draft", "submitted"}:
            return None
        due_at = aware(occupancy.hold_expires_at)
        reason_code = "hold_expired"
    elif occupancy.status == "waiting_service":
        if session.status != "submitted":
            return None
        due_at = waiting_deadline(occupancy, session)
        reason_code = "waiting_service_expired"
    elif occupancy.status in {"in_service", "post_service_present"}:
        due_at = service_deadline(occupancy)
        reason_code = "service_end_grace_expired"
    else:
        return None
    if due_at is None or (due_only and due_at > now):
        return None
    return ReleaseCandidate(
        occupancy_id=occupancy.id,
        version=occupancy.version,
        room_id=room.id,
        room_code=room.code,
        status=occupancy.status,
        selection_session_id=session.id,
        due_at=due_at,
        overdue_seconds=max(0, int((now - due_at).total_seconds())),
        reason_code=reason_code,
    )


def list_release_candidates(
    db: Session,
    now: datetime,
    store_id: int | None = None,
    due_only: bool = True,
    position_types: tuple[str, ...] = ("sofa",),
    *,
    statuses: tuple[str, ...] = ("held", "waiting_service"),
) -> list[ReleaseCandidate]:
    now = aware(now)
    if now is None:
        return []
    allowed_statuses = frozenset(statuses)
    stmt = (
        select(PositionOccupancy, Room, SelectionSession)
        .join(Room, Room.id == PositionOccupancy.active_room_id)
        .join(SelectionSession, SelectionSession.id == PositionOccupancy.selection_session_id)
        .where(
            PositionOccupancy.active_room_id.is_not(None),
            PositionOccupancy.status.in_(allowed_statuses),
            Room.room_type.in_(position_types),
        )
        .order_by(PositionOccupancy.id)
    )
    if store_id is not None:
        stmt = stmt.where(PositionOccupancy.store_id == store_id)
    candidates = []
    for occupancy, room, session in db.execute(stmt):
        item = _candidate(
            occupancy,
            room,
            session,
            now,
            due_only=due_only,
            allowed_statuses=allowed_statuses,
        )
        if item is not None:
            candidates.append(item)
    return candidates


def _reject_pending_changes(db: Session, session_id: str, now: datetime, reason: str) -> None:
    changes = list(db.scalars(select(SelectionChangeRequest).where(
        SelectionChangeRequest.selection_session_id == session_id,
        SelectionChangeRequest.state == "awaiting_staff_confirmation",
    )))
    for change in changes:
        change.state = "rejected"
        change.reason = reason
        change.resolved_at = now
        revision = db.get(SelectionRevision, change.selection_revision_id)
        if revision and revision.state == "awaiting_staff_confirmation":
            revision.state = "rejected"


def release_due_occupancies(
    db: Session,
    now: datetime,
    observe_only: bool = False,
    trigger: str = "scheduler",
    *,
    store_id: int | None = None,
    statuses: tuple[str, ...] = ("held", "waiting_service", "in_service", "post_service_present"),
) -> CleanupResult:
    candidates = tuple(list_release_candidates(
        db,
        now,
        store_id=store_id,
        statuses=statuses,
    ))
    if observe_only:
        return CleanupResult(candidates=candidates)

    expected_versions = {candidate.occupancy_id: candidate.version for candidate in candidates}
    return _release_candidates(
        db,
        now,
        candidates,
        expected_versions,
        trigger=trigger,
        action="occupancy_auto_released",
        release_reason=None,
        statuses=statuses,
    )


def _release_candidates(
    db: Session,
    now: datetime,
    candidates: tuple[ReleaseCandidate, ...],
    expected_versions: dict[int, int],
    *,
    trigger: str,
    action: str,
    release_reason: str | None,
    statuses: tuple[str, ...],
) -> CleanupResult:
    released_ids: list[int] = []
    skipped: list[tuple[int, str]] = []
    allowed_statuses = frozenset(statuses)
    now = aware(now)
    if now is None:
        return CleanupResult(candidates=candidates)
    for candidate in candidates:
        row = db.execute(
            select(PositionOccupancy, Room, SelectionSession)
            .join(Room, Room.id == PositionOccupancy.active_room_id)
            .join(SelectionSession, SelectionSession.id == PositionOccupancy.selection_session_id)
            .where(PositionOccupancy.id == candidate.occupancy_id)
            .with_for_update(skip_locked=True)
        ).first()
        if row is None:
            skipped.append((candidate.occupancy_id, "not_eligible"))
            continue
        occupancy, room, session = row
        if occupancy.version != expected_versions.get(occupancy.id):
            skipped.append((occupancy.id, "version_changed"))
            continue
        current = _candidate(
            occupancy,
            room,
            session,
            now,
            due_only=True,
            allowed_statuses=allowed_statuses,
        )
        if current is None:
            skipped.append((candidate.occupancy_id, "not_eligible"))
            continue
        reason = release_reason or (
            "服务位临时占用超时自动释放" if occupancy.status == "held"
            else "项目结束超过30分钟自动释放" if occupancy.status in {"in_service", "post_service_present"}
            else "服务位等待超时自动释放"
        )
        before_status = occupancy.status
        release_occupancy(occupancy, reason, now=now)
        if session.status in {"draft", "submitted"}:
            session.status = "expired"
        _reject_pending_changes(db, session.id, now, "服务位已自动释放")
        audit_occupancy(
            db,
            occupancy,
            action,
            "system",
            trigger,
            {
                "from_status": before_status,
                "to_status": occupancy.status,
                "reason_code": current.reason_code,
                "due_at": current.due_at.isoformat(),
                "overdue_seconds": current.overdue_seconds,
            },
        )
        released_ids.append(occupancy.id)
    db.commit()
    return CleanupResult(
        candidates=candidates,
        released_ids=tuple(released_ids),
        skipped=tuple(skipped),
    )


def release_selected_occupancies(
    db: Session,
    now: datetime,
    expected_versions: dict[int, int],
    *,
    store_id: int,
    trigger: str,
    release_reason: str,
) -> CleanupResult:
    current_candidates = {
        candidate.occupancy_id: candidate
        for candidate in list_release_candidates(db, now, store_id=store_id)
    }
    selected: list[ReleaseCandidate] = []
    skipped: list[tuple[int, str]] = []
    for occupancy_id, expected_version in expected_versions.items():
        occupancy = db.get(PositionOccupancy, occupancy_id)
        if occupancy is not None and occupancy.version != expected_version:
            skipped.append((occupancy_id, "version_changed"))
            continue
        candidate = current_candidates.get(occupancy_id)
        if candidate is None:
            skipped.append((occupancy_id, "not_eligible"))
            continue
        selected.append(candidate)
    result = _release_candidates(
        db,
        now,
        tuple(selected),
        expected_versions,
        trigger=trigger,
        action="occupancy_bulk_released",
        release_reason=release_reason,
        statuses=("held", "waiting_service"),
    )
    return CleanupResult(
        candidates=tuple(selected),
        released_ids=result.released_ids,
        skipped=tuple((*skipped, *result.skipped)),
    )
