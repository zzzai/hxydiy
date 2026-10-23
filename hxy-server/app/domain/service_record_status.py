"""Read-only service-record completion, independent of customer confirmation."""
from datetime import timedelta

from sqlalchemy import String, and_, cast, exists, func, or_, select
from sqlalchemy.orm import aliased

from app.models import AuditLog, CustomerProfileRecord, PositionOccupancy, SelectionSession, Staff, Technician, User


def _supported_reference_version():
    return or_(
        and_(CustomerProfileRecord.schema_version == 7, CustomerProfileRecord.taxonomy_version == "service_handoff_v1"),
        and_(CustomerProfileRecord.schema_version == 6, CustomerProfileRecord.taxonomy_version == 'service_record_v1'),
        and_(CustomerProfileRecord.schema_version == 2, CustomerProfileRecord.taxonomy_version == "service_reference_v1"),
        and_(CustomerProfileRecord.schema_version == 3, CustomerProfileRecord.taxonomy_version == "service_reference_v2"),
        and_(CustomerProfileRecord.schema_version == 4, CustomerProfileRecord.taxonomy_version == "service_reference_v3"),
        and_(CustomerProfileRecord.schema_version == 5, CustomerProfileRecord.taxonomy_version == "service_reference_v4"),
    )


def _not_superseded_reference():
    correction = aliased(CustomerProfileRecord)
    return ~exists().where(
        correction.correction_of_id == CustomerProfileRecord.id,
        correction.store_id == CustomerProfileRecord.store_id,
        correction.user_id == CustomerProfileRecord.user_id,
    )


def finish_proven(staff_id):
    return select(AuditLog.id).where(
        AuditLog.store_id == PositionOccupancy.store_id,
        AuditLog.actor_type == 'staff', AuditLog.actor_id == cast(staff_id, String),
        AuditLog.action == 'technician_finish_service',
        AuditLog.entity_type == 'position_occupancy',
        AuditLog.entity_id == cast(PositionOccupancy.id, String),
    ).correlate(PositionOccupancy, Staff).exists()


def recordable_service(staff_id):
    # Match the existing write API: only the latest, owned completed occupancy.
    newer = aliased(PositionOccupancy)
    customer_exists = select(User.id).join(SelectionSession, SelectionSession.customer_id == User.id).where(
        SelectionSession.id == PositionOccupancy.selection_session_id,
        SelectionSession.store_id == PositionOccupancy.store_id,
    ).correlate(PositionOccupancy).exists()
    replaced = select(newer.id).where(
        newer.selection_session_id == PositionOccupancy.selection_session_id,
        newer.id > PositionOccupancy.id,
    ).correlate(PositionOccupancy).exists()
    return and_(
        customer_exists, ~replaced, finish_proven(staff_id),
        PositionOccupancy.actual_service_end_at.is_not(None),
    )


def own_record_exists(staff_id):
    return select(CustomerProfileRecord.id).join(SelectionSession, and_(
        SelectionSession.id == CustomerProfileRecord.selection_session_id,
        SelectionSession.store_id == CustomerProfileRecord.store_id,
        SelectionSession.customer_id == CustomerProfileRecord.user_id,
    )).where(
        CustomerProfileRecord.store_id == PositionOccupancy.store_id,
        CustomerProfileRecord.selection_session_id == PositionOccupancy.selection_session_id,
        CustomerProfileRecord.technician_id == PositionOccupancy.serviced_by_technician_id,
        CustomerProfileRecord.created_by_staff_id == staff_id,
        _supported_reference_version(), _not_superseded_reference(),
    ).correlate(PositionOccupancy, Staff).exists()


def pending_record_summary(db, store_id, now):
    # Only actionable, attributed services; no private record content is loaded.
    rows = db.execute(select(Technician.id, Technician.name, func.count(PositionOccupancy.id)).join(
        PositionOccupancy, and_(PositionOccupancy.serviced_by_technician_id == Technician.id, PositionOccupancy.store_id == Technician.store_id),
    ).join(Staff, and_(Staff.technician_id == Technician.id, Staff.store_id == Technician.store_id)).join(
        SelectionSession, and_(SelectionSession.id == PositionOccupancy.selection_session_id, SelectionSession.store_id == PositionOccupancy.store_id),
    ).where(
        PositionOccupancy.store_id == store_id,
        PositionOccupancy.actual_service_end_at >= now - timedelta(days=30),
        PositionOccupancy.actual_service_end_at <= now,
        SelectionSession.customer_id.is_not(None),
        Staff.status == 'active', Staff.role == 'technician',
        Technician.status.in_(('available', 'busy')),
        recordable_service(Staff.id), ~own_record_exists(Staff.id),
    ).group_by(Technician.id, Technician.name).order_by(Technician.id)).all()
    return {
        'window_days': 30,
        'pending_count': sum(int(count) for _, _, count in rows),
        'technicians': [{'technician_id': tech_id, 'name': name, 'count': int(count)} for tech_id, name, count in rows],
    }
