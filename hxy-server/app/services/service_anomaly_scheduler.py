"""Periodic service-anomaly detection for stores.

The job reuses the same provable DIY association detector as the manager
endpoint. It writes only to the existing operational exception queue and never
changes occupancy, selection, pricing or physical resources.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select, text

from app.core.config import Settings, settings
from app.db.session import SessionLocal
from app.models import Store

ADVISORY_LOCK_ID = 2026102601
logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def run_scheduled_service_anomaly_sync(
    runtime_settings: Settings = settings,
    trigger: str = "periodic",
) -> dict:
    from app.api.admin_v2 import _sync_service_anomalies_for_store

    totals = {"stores": 0, "detected": 0, "created": 0, "updated": 0, "reopened": 0, "resolved": 0}
    with SessionLocal() as db:
        if db.get_bind().dialect.name == "postgresql":
            acquired = bool(db.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                {"lock_id": ADVISORY_LOCK_ID},
            ))
            if not acquired:
                logger.info("service anomaly sync skipped because another worker holds the lock")
                return totals
        store_ids = list(db.scalars(select(Store.id).where(Store.status == "open")))
        for store_id in store_ids:
            result = _sync_service_anomalies_for_store(db, store_id)
            db.commit()
            totals["stores"] += 1
            for key in ("detected", "created", "updated", "reopened", "resolved"):
                totals[key] += int(result.get(key, 0))
        logger.info(
            "service anomaly sync trigger=%s stores=%s detected=%s created=%s updated=%s reopened=%s resolved=%s",
            trigger,
            totals["stores"],
            totals["detected"],
            totals["created"],
            totals["updated"],
            totals["reopened"],
            totals["resolved"],
        )
    return totals


def build_service_anomaly_scheduler(runtime_settings: Settings = settings) -> BackgroundScheduler | None:
    if runtime_settings.environment != "production" or not runtime_settings.service_anomaly_scheduler_enabled:
        return None
    scheduler = BackgroundScheduler(timezone=runtime_settings.occupancy_timezone)
    scheduler.add_job(
        run_scheduled_service_anomaly_sync,
        "interval",
        id="service-anomaly-sync",
        seconds=runtime_settings.service_anomaly_scheduler_interval_seconds,
        args=[runtime_settings, "periodic"],
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    return scheduler


def start_service_anomaly_scheduler(runtime_settings: Settings = settings) -> BackgroundScheduler | None:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = build_service_anomaly_scheduler(runtime_settings)
    if _scheduler is not None:
        _scheduler.start()
    return _scheduler


def stop_service_anomaly_scheduler() -> None:
    global _scheduler
    scheduler = _scheduler
    _scheduler = None
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
