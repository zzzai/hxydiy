"""Durable per-image review queue. Provider I/O never holds a database lock."""
import asyncio
from datetime import UTC, datetime, timedelta
import logging

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import DailyAreaPhoto, DailyAreaPhotoReview, DailyStoreCheckin, MediaAsset
from app.services.inspection_vision import AREA_RUBRICS, MODEL, RUBRIC_VERSION, VisionError, inspect_photo, inspection_jpeg
from app.services.media_storage import MediaStorageError, get_media_storage

log = logging.getLogger("app.inspection_reviews")
LEASE = timedelta(minutes=3)


def find_review(db: Session, photo_id: int, media_id: int) -> DailyAreaPhotoReview | None:
    return db.scalar(select(DailyAreaPhotoReview).where(
        DailyAreaPhotoReview.photo_id == photo_id, DailyAreaPhotoReview.media_id == media_id))


def queue_photo(db: Session, photo: DailyAreaPhoto) -> DailyAreaPhotoReview:
    # Callers hold the parent check-in lock. The queue shares the image write's transaction.
    item = find_review(db, photo.id, photo.media_id)
    if item is None:
        item = DailyAreaPhotoReview(photo_id=photo.id, media_id=photo.media_id, model=MODEL, rubric=RUBRIC_VERSION)
        db.add(item)
    elif item.state == "superseded":
        item.state = "pending"
        item.error_code = None
        item.finished_at = None
    return item


def image_changed(db: Session, photo: DailyAreaPhoto, media: MediaAsset) -> None:
    db.execute(update(DailyAreaPhotoReview).where(
        DailyAreaPhotoReview.photo_id == photo.id, DailyAreaPhotoReview.media_id != photo.media_id,
        DailyAreaPhotoReview.state.in_(("pending", "running")),
    ).values(state="superseded", finished_at=datetime.now(UTC)))
    if not settings.inspection_ai_ready or media.purpose != "daily_area" or photo.area not in AREA_RUBRICS:
        return
    uploaded = media.created_at
    if uploaded is not None:
        uploaded = uploaded if uploaded.tzinfo else uploaded.replace(tzinfo=UTC)
        if uploaded.timestamp() > settings.inspection_ai_auto_from_epoch:
            queue_photo(db, photo)


def review_view(item: DailyAreaPhotoReview | None) -> dict | None:
    if item is None:
        return None
    return {"state": item.state, "attempt": item.attempt, "result": item.result if item.state == "done" else None,
            "manual_verdict": item.manual_verdict}


def _claim(factory):
    now = datetime.now(UTC)
    with factory.begin() as db:
        db.execute(update(DailyAreaPhotoReview).where(
            DailyAreaPhotoReview.state == "running", DailyAreaPhotoReview.started_at < now - LEASE
        ).values(state="failed", error_code="interrupted", finished_at=now))
        recently_blocked = db.scalar(select(DailyAreaPhotoReview.id).where(
            DailyAreaPhotoReview.state == "failed",
            DailyAreaPhotoReview.error_code.in_(("quota", "configuration", "rate_limited", "provider_unavailable")),
            DailyAreaPhotoReview.finished_at > now - timedelta(minutes=2),
        ).limit(1))
        if recently_blocked is not None:
            return None
        job = db.scalar(select(DailyAreaPhotoReview).where(DailyAreaPhotoReview.state == "pending")
                        .order_by(DailyAreaPhotoReview.id).limit(1).with_for_update(skip_locked=True))
        if job is None:
            return None
        job.state = "running"
        job.attempt += 1
        job.started_at = now
        return job.id, job.attempt, job.photo_id, job.media_id


def _source(factory, photo_id, media_id):
    with factory() as db:
        return db.execute(select(DailyAreaPhoto.area, MediaAsset.object_key).join(
            DailyStoreCheckin, DailyStoreCheckin.id == DailyAreaPhoto.checkin_id
        ).join(MediaAsset, MediaAsset.id == DailyAreaPhoto.media_id).where(
            DailyAreaPhoto.id == photo_id, DailyAreaPhoto.media_id == media_id,
            MediaAsset.store_id == DailyStoreCheckin.store_id, MediaAsset.media_type == "image",
            MediaAsset.purpose == "daily_area", MediaAsset.deleted_at.is_(None),
            DailyStoreCheckin.created_at >= datetime.now(UTC) - timedelta(days=90),
        )).one_or_none()


def process_next(factory=SessionLocal, *, provider=inspect_photo, storage=None) -> bool:
    if not settings.inspection_ai_ready:
        return False
    claim = _claim(factory)
    if claim is None:
        return False
    job_id, attempt, photo_id, media_id = claim
    state, result, error = "superseded", None, None
    try:
        source = _source(factory, photo_id, media_id)
        if source is not None and source.area in AREA_RUBRICS:
            reader = storage if storage is not None else get_media_storage(settings)
            content = reader.read(source.object_key, settings.media_max_size_bytes)
            jpeg = inspection_jpeg(content, settings.media_max_pixels)
            if _source(factory, photo_id, media_id) is not None:
                result = provider(source.area, jpeg, settings.inspection_ai_api_key)
                state = "done"
    except VisionError as exc:
        state, error = "failed", exc.code
    except (MediaStorageError, OSError):
        state, error = "failed", "image_unavailable"
    if error:
        log.warning("inspection_review_failed job=%s reason=%s", job_id, error)
    with factory.begin() as db:
        db.execute(update(DailyAreaPhotoReview).where(
            DailyAreaPhotoReview.id == job_id, DailyAreaPhotoReview.attempt == attempt,
            DailyAreaPhotoReview.state == "running",
        ).values(state=state, result=result, error_code=error, finished_at=datetime.now(UTC)))
    return True


async def run_worker():
    while True:
        try:
            worked = await asyncio.to_thread(process_next)
        except Exception as exc:
            # Avoid logging media URLs, provider bodies, credentials, or SQL parameters.
            log.error("inspection_review_worker_failed type=%s", type(exc).__name__)
            worked = False
        await asyncio.sleep(0.3 if worked else 5)
