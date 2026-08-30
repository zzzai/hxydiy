"""Production scheduler for safe service-position occupancy cleanup."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

from app.core.config import Settings, settings
from app.db.session import SessionLocal
from app.domain.occupancy import utcnow
from app.domain.occupancy_release_policy import CleanupResult, release_due_occupancies


ADVISORY_LOCK_ID = 2026081701
logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def run_scheduled_occupancy_cleanup(
    runtime_settings: Settings = settings,
    trigger: str = "minute_sweep",
) -> CleanupResult:
    with SessionLocal() as db:
        if db.get_bind().dialect.name == "postgresql":
            acquired = bool(db.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                {"lock_id": ADVISORY_LOCK_ID},
            ))
            if not acquired:
                logger.info("occupancy cleanup skipped because another worker holds the lock")
                return CleanupResult(candidates=())
        result = release_due_occupancies(
            db,
            utcnow(),
            observe_only=runtime_settings.occupancy_scheduler_observe_only,
            trigger=trigger,
        )
        logger.info(
            "occupancy cleanup trigger=%s observe_only=%s candidates=%s released=%s skipped=%s",
            trigger,
            runtime_settings.occupancy_scheduler_observe_only,
            result.candidate_count,
            result.released_count,
            len(result.skipped),
        )
        return result


def build_occupancy_scheduler(
    runtime_settings: Settings = settings,
) -> BackgroundScheduler | None:
    if (
        runtime_settings.environment != "production"
        or not runtime_settings.occupancy_scheduler_enabled
    ):
        return None
    scheduler = BackgroundScheduler(timezone=runtime_settings.occupancy_timezone)
    common = {"coalesce": True, "max_instances": 1, "replace_existing": True}
    scheduler.add_job(
        run_scheduled_occupancy_cleanup,
        "interval",
        id="occupancy-minute-sweep",
        seconds=runtime_settings.occupancy_scheduler_interval_seconds,
        args=[runtime_settings, "minute_sweep"],
        **common,
    )
    scheduler.add_job(
        run_scheduled_occupancy_cleanup,
        "cron",
        id="occupancy-closing-sweep",
        hour=runtime_settings.occupancy_closing_hour,
        minute=0,
        args=[runtime_settings, "closing_sweep"],
        **common,
    )
    return scheduler


def start_occupancy_scheduler(
    runtime_settings: Settings = settings,
) -> BackgroundScheduler | None:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = build_occupancy_scheduler(runtime_settings)
    if _scheduler is not None:
        _scheduler.start()
    return _scheduler


def stop_occupancy_scheduler() -> None:
    global _scheduler
    scheduler = _scheduler
    _scheduler = None
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
