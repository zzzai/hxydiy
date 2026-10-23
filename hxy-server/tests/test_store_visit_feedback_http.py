"""Verify the public entry over a real isolated localhost HTTP server."""

import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import Store, VisitFeedback


def test_store_entry_and_submission_over_real_http(tmp_path):
    root = Path(__file__).resolve().parents[1]
    database_url = f"sqlite:///{tmp_path / 'feedback-http.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as db, db.begin():
        db.add(Store(id=1, store_code="feedback-http", name="Synthetic HTTP store", address="Isolated", status="open"))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with (tmp_path / "uvicorn.log").open("w+") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=root, stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, "ENVIRONMENT": "test", "DATABASE_URL": database_url},
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=5) as client:
                deadline = time.monotonic() + 15
                while True:
                    assert server.poll() is None, "Isolated HTTP server exited before readiness"
                    try:
                        ready = client.get("/api/v1/health")
                        if ready.status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    assert time.monotonic() < deadline, "Isolated HTTP readiness deadline exceeded"
                    time.sleep(0.1)
                entry = client.post("/api/v1/visit-feedback/store-entry", json={"store_id": 1})
                assert entry.status_code == 200, entry.text
                assert client.cookies.get("hxy_browser_token")
                body = {"visit_feedback_token": entry.json()["visit_feedback_token"], "rating": 5, "note": "Synthetic HTTP feedback"}
                headers = {"Idempotency-Key": "real-http-feedback-key"}
                saved = client.post("/api/v1/visit-feedback", headers=headers, json=body)
                assert saved.status_code == 200, saved.text
                assert client.post("/api/v1/visit-feedback", headers=headers, json=body).json()["id"] == saved.json()["id"]
                no_rating = client.post("/api/v1/visit-feedback", headers={"Idempotency-Key": "real-http-missing-rating"}, json={"visit_feedback_token": body["visit_feedback_token"]})
                assert no_rating.status_code == 422
                client.cookies.clear()
                assert client.post("/api/v1/visit-feedback", headers=headers, json=body).status_code == 403
            with Session(engine) as db:
                rows = list(db.scalars(select(VisitFeedback)))
                assert len(rows) == 1 and rows[0].room_id is None and rows[0].source == "store_qr"
                for table in ("selection_sessions", "orders", "position_occupancies", "service_feedback"):
                    assert db.scalar(select(func.count()).select_from(Base.metadata.tables[table])) == 0
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            engine.dispose()
