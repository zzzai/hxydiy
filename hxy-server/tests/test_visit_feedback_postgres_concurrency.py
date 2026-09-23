"""Verify visit feedback idempotency and rate limits on real PostgreSQL workers."""

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.domain.visit_feedback_tokens import create_visit_feedback_token
from app.main import app
from app.models import Room, ServicePositionQr, Store, VisitFeedback


def _isolated_postgres_url() -> str:
    value = os.getenv("HXY_FEEDBACK_TEST_POSTGRES_URL")
    if not value:
        pytest.skip("HXY_FEEDBACK_TEST_POSTGRES_URL is required for PostgreSQL concurrency verification")
    parsed = make_url(value)
    if (
        parsed.drivername != "postgresql+psycopg"
        or parsed.host not in {"127.0.0.1", "localhost"}
        or parsed.database != "hxy_feedback_ci"
        or parsed.query
    ):
        pytest.fail("HXY_FEEDBACK_TEST_POSTGRES_URL must target the isolated local hxy_feedback_ci database")
    return value


def test_parallel_submissions_respect_idempotency_and_rate_limit():
    engine = create_engine(_isolated_postgres_url(), pool_pre_ping=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    with SessionLocal.begin() as db:
        store = Store(store_code=f"feedback-ci-{suffix[:16]}", name="Concurrency test store", address="isolated CI")
        db.add(store)
        db.flush()
        room = Room(
            store_id=store.id,
            code=f"feedback-ci-{suffix[:16]}",
            name="Concurrency test position",
            room_type="sofa",
            customer_label="1",
            operational_status="active",
            is_service_position=True,
            is_space_container=False,
        )
        db.add(room)
        db.flush()
        qr = ServicePositionQr(
            public_id=str(uuid.uuid4()), store_id=store.id, room_id=room.id,
            source="personal_qr", status="active",
        )
        db.add(qr)
        db.flush()
        room_id = room.id
        qr_id = qr.id

    def override_get_db():
        with SessionLocal() as db:
            yield db

    def submit(browser: str, token: str, key: str, barrier: threading.Barrier):
        with TestClient(app) as client:
            client.cookies.set("hxy_browser_token", browser)
            barrier.wait(timeout=15)
            response = client.post(
                "/api/v1/visit-feedback",
                headers={"Idempotency-Key": key},
                json={"visit_feedback_token": token, "rating": 5, "tags": [], "note": ""},
            )
            return response.status_code, response.json()

    app.dependency_overrides[get_db] = override_get_db
    try:
        browser = f"feedback-ci-browser-{suffix}"
        with SessionLocal() as db:
            token = create_visit_feedback_token(db.get(Room, room_id), "personal_qr", browser, qr_id)
        with ThreadPoolExecutor(max_workers=6) as executor:
            barrier = threading.Barrier(6)
            results = list(executor.map(
                lambda index: submit(browser, token, f"rate-test-{suffix}-{index}", barrier), range(6)
            ))
        assert sorted(status for status, _ in results) == [200] * 5 + [429]
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(VisitFeedback).where(
                VisitFeedback.room_id == room_id
            )) == 5

        replay_browser = f"feedback-ci-replay-{suffix}"
        with SessionLocal() as db:
            replay_token = create_visit_feedback_token(db.get(Room, room_id), "personal_qr", replay_browser, qr_id)
        with ThreadPoolExecutor(max_workers=2) as executor:
            barrier = threading.Barrier(2)
            replay = list(executor.map(
                lambda _: submit(replay_browser, replay_token, f"same-key-{suffix}", barrier), range(2)
            ))
        assert [status for status, _ in replay] == [200, 200]
        assert replay[0][1]["id"] == replay[1][1]["id"]
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(VisitFeedback).where(
                VisitFeedback.room_id == room_id
            )) == 6
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
