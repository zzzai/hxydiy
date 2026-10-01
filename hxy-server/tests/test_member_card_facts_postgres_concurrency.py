"""Verify card update serialization on the existing isolated CI PostgreSQL service."""

import os
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.api.admin import create_staff_token
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, MembershipCard, Staff, Store, User


def _isolated_postgres_url():
    value = os.getenv("HXY_FEEDBACK_TEST_POSTGRES_URL")
    if not value:
        pytest.skip("isolated CI PostgreSQL is required for card row-lock verification")
    parsed = make_url(value)
    if (parsed.drivername != "postgresql+psycopg" or parsed.host not in {"localhost", "127.0.0.1"}
            or parsed.database != "hxy_feedback_ci" or parsed.query):
        pytest.fail("card concurrency verification requires the isolated local hxy_feedback_ci database")
    return value


@pytest.mark.parametrize("value", [
    "postgresql+psycopg://test:test@remote.example/hxy_feedback_ci",
    "postgresql+psycopg://test:test@localhost/hxy_diy",
    "postgresql+psycopg://test:test@localhost/hxy_feedback_ci?host=remote.example",
    "postgresql+psycopg2://test:test@localhost/hxy_feedback_ci",
])
def test_card_postgres_guard_rejects_other_databases_and_connection_overrides(monkeypatch, value):
    monkeypatch.setenv("HXY_FEEDBACK_TEST_POSTGRES_URL", value)
    with pytest.raises(pytest.fail.Exception, match="isolated local hxy_feedback_ci"):
        _isolated_postgres_url()


@pytest.mark.parametrize("same_request", [False, True], ids=["two-managers-one-version", "same-key-replay"])
def test_postgres_serializes_card_fact_updates(same_request):
    engine = create_engine(_isolated_postgres_url(), pool_pre_ping=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    now = datetime.now(UTC)
    with sessions.begin() as db:
        store = Store(store_code=f"card-pg-{suffix[:16]}", name="Test", address="isolated CI")
        user = User(openid=f"card-pg-{suffix}", balance_cents=500, is_member=False)
        db.add_all([store, user])
        db.flush()
        staff = [Staff(username=f"card-pg-{suffix[:16]}-{index}", name="Test manager", role="manager",
                       store_id=store.id, status="active", password_hash="unused-in-isolated-token-test")
                 for index in range(2)]
        card = MembershipCard(user_id=user.id, store_id=store.id, source="test", source_card_key=suffix,
                              card_type="stored", balance_cents=100, status="active",
                              started_at=now - timedelta(days=2), observed_at=now - timedelta(days=1))
        db.add_all([*staff, card])
        db.flush()
        card_id, user_id = card.id, user.id
        staff_ids = [person.id for person in staff]

    worker_pids = queue.Queue()
    capturing = threading.Event()

    def override():
        with sessions() as db:
            if capturing.is_set():
                db.execute(text("SET LOCAL lock_timeout = '15s'"))
                worker_pids.put(db.scalar(text("SELECT pg_backend_pid()")))
            yield db

    def post(index, body):
        checker = staff_ids[0] if same_request else staff_ids[index]
        with TestClient(app) as client:
            response = client.post(f"/api/v1/admin/v2/membership-cards/{card_id}/facts", json=body,
                                   headers={"Authorization": "Bearer " + create_staff_token(checker, "manager")})
            return response.status_code, response.json()

    app.dependency_overrides[get_db] = override
    try:
        payload = {"balance_cents": 0, "observed_at": now.isoformat(),
                   "evidence": "isolated checked ledger", "reason": "verified zero principal"}
        writes = []
        for index in range(2):
            status, preview = post(index, payload)
            assert status == 200, preview
            writes.append({**payload, "apply": True, "expected_version": preview["version"],
                           "preview_token": preview["preview_token"],
                           "idempotency_key": f"pg-{suffix}-{0 if same_request else index}"})

        with sessions() as blocker, ThreadPoolExecutor(max_workers=2) as workers:
            blocker.scalar(select(MembershipCard).where(MembershipCard.id == card_id).with_for_update())
            capturing.set()
            pending = [workers.submit(post, index, writes[index]) for index in range(2)]
            try:
                pids = [worker_pids.get(timeout=10) for _ in range(2)]
                deadline = time.monotonic() + 10
                blocked = False
                with engine.connect() as observer:
                    while time.monotonic() < deadline:
                        blocked = all(observer.scalar(text("SELECT pg_blocking_pids(:pid)"), {"pid": pid}) for pid in pids)
                        if blocked:
                            break
                        time.sleep(0.05)
                assert blocked, "both real PostgreSQL workers must contend on the held card"
            finally:
                blocker.commit()
            results = [future.result(timeout=20) for future in pending]
        capturing.clear()
        assert sorted(status for status, _ in results) == ([200, 200] if same_request else [200, 409])
        winner = next(body for status, body in results if status == 200)
        if same_request:
            assert results[0][1] == results[1][1]
        else:
            rejected = next(body for status, body in results if status == 409)
            assert rejected["detail"]["code"] == "MEMBER_CARD_VERSION_CONFLICT"
            status, latest = post(1, {**payload, "observed_at": datetime.now(UTC).isoformat()})
            assert status == 200, latest
            assert latest["version"] == winner["version"]
        with sessions() as db:
            assert db.get(MembershipCard, card_id).balance_cents == 0
            assert db.get(User, user_id).balance_cents == 500
            assert db.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "update_member_card_facts", AuditLog.entity_id == str(card_id),
            )) == 1
    finally:
        capturing.clear()
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
