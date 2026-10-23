"""Exercise real multi-connection store feedback on an explicitly isolated DB."""

from concurrent.futures import ThreadPoolExecutor
import threading
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.models import EventLog, Store, VisitFeedback
from test_visit_feedback_postgres_concurrency import _isolated_postgres_url


def test_store_feedback_concurrent_replay_conflict_and_rate_limit():
    engine = create_engine(_isolated_postgres_url(), pool_pre_ping=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    with sessions.begin() as db:
        stores = [Store(store_code=f"store-feedback-{suffix[:12]}-{i}", name="Synthetic", address="Isolated", status="open") for i in range(2)]
        db.add_all(stores)
        db.flush()
        store_ids = [store.id for store in stores]

    def override_db():
        with sessions() as db:
            yield db

    def parallel(browser, requests):
        barrier = threading.Barrier(len(requests))

        def send(item):
            token, key, rating = item
            with TestClient(app) as client:
                client.cookies.set("hxy_browser_token", browser)
                barrier.wait(timeout=15)
                response = client.post("/api/v1/visit-feedback", headers={"Idempotency-Key": key}, json={"visit_feedback_token": token, "rating": rating})
                return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=len(requests)) as executor:
            return list(executor.map(send, requests))

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            tokens = []
            for store_id in store_ids:
                entry = client.post("/api/v1/visit-feedback/store-entry", json={"store_id": store_id})
                assert entry.status_code == 200, entry.text
                tokens.append(entry.json()["visit_feedback_token"])
            browser = client.cookies.get("hxy_browser_token")
        replay = parallel(browser, [(tokens[0], f"replay-{suffix}", 5)] * 2)
        assert [status for status, _ in replay] == [200, 200]
        assert replay[0][1]["id"] == replay[1][1]["id"]
        conflicting = parallel(browser, [(tokens[0], f"cross-{suffix}", 4), (tokens[1], f"cross-{suffix}", 4)])
        assert sorted(status for status, _ in conflicting) == [200, 409]

        with TestClient(app) as client:
            entry = client.post("/api/v1/visit-feedback/store-entry", json={"store_id": store_ids[0]})
            assert entry.status_code == 200
            browser = client.cookies.get("hxy_browser_token")
            token = entry.json()["visit_feedback_token"]
        limited = parallel(browser, [(token, f"rate-{suffix}-{i}", 5) for i in range(6)])
        assert sorted(status for status, _ in limited) == [200] * 5 + [429]
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(VisitFeedback).where(VisitFeedback.store_id.in_(store_ids))) == 7
            assert db.scalar(select(func.count()).select_from(EventLog).where(EventLog.store_id.in_(store_ids))) == 7
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
