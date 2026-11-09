"""店长经营数据 90 天保留清理。

店长端打开经营页时会做一次轻量清理；这个后台任务保证即使当天没人打开页面，
过期的区域照片、晨会录音和转写也会在 90 天后被删除。
"""

import asyncio
from datetime import UTC, datetime, timedelta
import logging

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import DailyAreaPhoto, DailyMeetingRecording, DailyStoreCheckin, MediaAsset
from app.services.media_storage import MediaStorageError, get_media_storage

logger = logging.getLogger("app.daily_ops_retention")
RETENTION_DAYS = 90


def cleanup_expired_daily_ops() -> dict:
    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
    deleted_checkins = 0
    deleted_media = 0
    with SessionLocal() as db:
        checkins = list(db.scalars(select(DailyStoreCheckin).where(
            DailyStoreCheckin.created_at < cutoff,
        )))
        if not checkins:
            return {"checkins": 0, "media": 0}
        storage = None
        try:
            storage = get_media_storage(settings)
        except MediaStorageError:
            storage = None
        for checkin in checkins:
            photos = list(db.scalars(select(DailyAreaPhoto).where(DailyAreaPhoto.checkin_id == checkin.id)))
            meetings = list(db.scalars(select(DailyMeetingRecording).where(DailyMeetingRecording.checkin_id == checkin.id)))
            for item in [*photos, *meetings]:
                media = db.get(MediaAsset, item.media_id)
                if media and not media.deleted_at:
                    if storage is not None:
                        try:
                            storage.delete(media.object_key)
                        except MediaStorageError as exc:
                            logger.warning("daily_ops_media_delete_failed media=%s: %s", media.id, exc)
                    media.deleted_at = datetime.now(UTC)
                    deleted_media += 1
                db.delete(item)
            db.delete(checkin)
            deleted_checkins += 1
        db.commit()
    if deleted_checkins:
        logger.info("daily_ops_retention checkins=%s media=%s", deleted_checkins, deleted_media)
    return {"checkins": deleted_checkins, "media": deleted_media}


_task: asyncio.Task | None = None


async def _run() -> None:
    while True:
        try:
            await asyncio.to_thread(cleanup_expired_daily_ops)
        except Exception:
            logger.exception("daily_ops_retention_failed")
        await asyncio.sleep(max(3600, int(settings.daily_ops_retention_interval_seconds)))


def start_daily_ops_retention() -> None:
    global _task
    if not settings.daily_ops_retention_enabled or _task is not None:
        return
    _task = asyncio.create_task(_run())


def stop_daily_ops_retention() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    _task = None
