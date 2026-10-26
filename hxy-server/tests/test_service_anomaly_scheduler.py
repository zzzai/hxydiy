from app.core.config import settings
from app.services.service_anomaly_scheduler import build_service_anomaly_scheduler


def test_scheduler_disabled_outside_production_or_by_default():
    runtime = settings.model_copy(update={"environment": "test", "service_anomaly_scheduler_enabled": True})
    assert build_service_anomaly_scheduler(runtime) is None
    runtime = settings.model_copy(update={"environment": "production", "service_anomaly_scheduler_enabled": False})
    assert build_service_anomaly_scheduler(runtime) is None


def test_scheduler_builds_one_periodic_job_in_production():
    runtime = settings.model_copy(update={
        "environment": "production",
        "service_anomaly_scheduler_enabled": True,
        "service_anomaly_scheduler_interval_seconds": 300,
    })
    scheduler = build_service_anomaly_scheduler(runtime)
    assert scheduler is not None
    scheduler.start()
    job = scheduler.get_job("service-anomaly-sync")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 300
    scheduler.shutdown(wait=False)
