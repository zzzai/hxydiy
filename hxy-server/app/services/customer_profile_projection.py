from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.wellness_profile import ProjectedProfileValue, extract_confirmed_v3_profile
from app.models import CustomerProfileCurrent, CustomerProfileRecord


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def rebuild_customer_profile_current(
    db: Session,
    *,
    customer_id: int,
    now: datetime | None = None,
) -> list[CustomerProfileCurrent]:
    current_time = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    records = list(db.scalars(
        select(CustomerProfileRecord)
        .where(CustomerProfileRecord.user_id == customer_id)
        .order_by(CustomerProfileRecord.created_at.asc(), CustomerProfileRecord.id.asc())
    ))
    superseded_ids = {record.correction_of_id for record in records if record.correction_of_id is not None}
    latest_by_code: dict[str, tuple[CustomerProfileRecord, list[ProjectedProfileValue]]] = {}
    confirmation_counts: dict[tuple[str, str], int] = {}
    first_confirmed: dict[tuple[str, str], datetime] = {}

    for record in records:
        if record.id in superseded_ids or not record.customer_confirmed or record.confirmed_at is None:
            continue
        confirmed_at = _as_utc(record.confirmed_at)
        for profile_code, values in extract_confirmed_v3_profile(record.profile or {}).items():
            latest_by_code[profile_code] = (record, values)
            for value in values:
                key = (profile_code, value.value)
                confirmation_counts[key] = confirmation_counts.get(key, 0) + 1
                first_confirmed.setdefault(key, confirmed_at)

    db.execute(delete(CustomerProfileCurrent).where(CustomerProfileCurrent.customer_id == customer_id))
    db.flush()

    created: list[CustomerProfileCurrent] = []
    for profile_code, (record, values) in latest_by_code.items():
        confirmed_at = _as_utc(record.confirmed_at)
        for value in values:
            key = (profile_code, value.value)
            valid_until = confirmed_at + timedelta(days=value.valid_days)
            row = CustomerProfileCurrent(
                customer_id=customer_id,
                profile_code=profile_code,
                profile_value_key=value.value,
                profile_value_json={"value": value.value},
                body_area_code="",
                body_side="",
                source_record_id=record.id,
                first_confirmed_at=first_confirmed[key],
                last_confirmed_at=confirmed_at,
                confirmation_count=confirmation_counts[key],
                valid_until=valid_until,
                sensitivity_level=value.sensitivity_level,
                taxonomy_version=record.taxonomy_version or "",
                status="active" if valid_until > current_time else "expired",
            )
            db.add(row)
            created.append(row)

    db.flush()
    return created
