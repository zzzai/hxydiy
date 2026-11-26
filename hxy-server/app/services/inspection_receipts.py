"""Record an authenticated recipient opening an individual WeCom notification."""
from datetime import UTC, datetime
import hmac

from sqlalchemy import update

from app.core.config import settings
from app.models import InspectionDelivery


def notice_key(item: InspectionDelivery) -> str:
    subject = f"inspection-notice/v1/{item.id}/{item.binding_id}/{item.binding_version}/{item.event_key}"
    signature = hmac.digest(settings.jwt_secret.encode(), subject.encode(), "sha256").hex()[:32]
    return f"{item.id}.{signature}"


def record_notice_open(db, attempt, key: str):
    identifier, separator, signature = key.partition(".")
    if not separator or len(signature) != 32 or not identifier.isascii() or not identifier.isdecimal() or len(identifier) > 10:
        return None
    item = db.get(InspectionDelivery, int(identifier))
    if (item is None or not hmac.compare_digest(notice_key(item), key)
            or item.binding_id != attempt.identity_id or item.binding_version != attempt.binding_version
            or item.attempted_at is None or item.state not in {"sending", "accepted", "unknown"}):
        return None
    is_weekly_recipient = (item.binding_id == settings.inspection_weekly_binding_id
                           and item.binding_version == settings.inspection_weekly_binding_version)
    if bool(item.week_start) != is_weekly_recipient:
        return None
    db.execute(update(InspectionDelivery).where(InspectionDelivery.id == item.id,
        InspectionDelivery.opened_at.is_(None)).values(opened_at=datetime.now(UTC)))
    db.commit()
    return item.summary_text if item.week_start else None
