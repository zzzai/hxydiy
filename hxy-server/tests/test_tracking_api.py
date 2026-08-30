import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models import EventLog


class TrackingApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)

        def override_get_db():
            with cls.SessionLocal() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def setUp(self):
        with self.SessionLocal() as db:
            db.query(EventLog).delete()
            db.commit()

    def test_client_timestamp_is_preserved_inside_event_data(self):
        response = self.client.post("/api/v1/events", json={"events": [{
            "event": "diy_entry_view",
            "page": "/diy",
            "ts": "2026-08-14T12:00:00.000Z",
            "data": {"anonymous_id": "anon-1", "client_session_id": "session-1"},
        }]})

        self.assertEqual(response.status_code, 200, response.text)
        with self.SessionLocal() as db:
            event = db.scalar(select(EventLog))
            self.assertEqual(event.data, {
                "anonymous_id": "anon-1",
                "client_session_id": "session-1",
                "client_ts": "2026-08-14T12:00:00.000Z",
            })

    def test_empty_event_name_is_rejected(self):
        response = self.client.post("/api/v1/events", json={"events": [{"event": ""}]})

        self.assertEqual(response.status_code, 422, response.text)

    def test_more_than_fifty_events_is_rejected_without_partial_write(self):
        response = self.client.post("/api/v1/events", json={
            "events": [{"event": "diy_entry_view", "data": {"index": index}} for index in range(51)],
        })

        self.assertEqual(response.status_code, 422, response.text)
        with self.SessionLocal() as db:
            self.assertEqual(db.query(EventLog).count(), 0)


if __name__ == "__main__":
    unittest.main()
