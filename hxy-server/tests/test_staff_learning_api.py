import copy
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token
from app.api.staff_learning import content_hash
from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app
from app.models import Staff, Store, Technician
from app.models.staff_learning import LearningCourseVersion, StaffLearningAssignment, StaffLearningEvent

PREFIX = "/api/v1/staff-learning"
COURSE = {"id": "S01", "version": "test-v1", "title": "Synthetic lesson", "category": "Service",
    "minutes": "3 minutes", "intro": "", "sources": [],
    "sections": [{"id": "one", "title": "Listen", "paragraphs": ["Listen first"]}, {"id": "two", "title": "Confirm", "paragraphs": ["Confirm first"]}],
    "questions": [{"id": "q1", "prompt": "Which?", "choices": ["A", "B"], "answer": 1, "explanation": "Synthetic answer"},
                  {"id": "q2", "prompt": "Which again?", "choices": ["A", "B"], "answer": 0, "explanation": "Synthetic explanation"}]}


@pytest.fixture
def learning(monkeypatch):
    monkeypatch.setattr(settings, "staff_learning_enabled", True)
    monkeypatch.setattr(settings, "environment", "test")
    url = os.getenv("LEARNING_TEST_DATABASE_URL")
    schema = "learning_" + uuid.uuid4().hex
    if url:
        # Only the dedicated disposable test database is accepted.
        assert "/learning_test" in url and "learning-postgres-v8" in url
        control = create_engine(url)
        with control.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        @event.listens_for(engine, "connect")
        def fk(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        stores = [Store(store_code=f"learning-{n}", name="Synthetic store", address="Synthetic") for n in range(2)]
        db.add_all(stores); db.flush()
        techs = [Technician(store_id=stores[n // 2].id, code=f"L{n}", name=f"Synthetic {n}", status="available") for n in range(3)]
        db.add_all(techs); db.flush()
        staff = [Staff(username=f"learning-tech-{n}", name=f"Tech {n}", password_hash="unused", role="technician",
            store_id=t.store_id, technician_id=t.id) for n, t in enumerate(techs)]
        managers = [Staff(username=f"learning-manager-{n}", name=f"Manager {n}", password_hash="unused", role="manager", store_id=stores[n].id) for n in range(2)]
        extra = Staff(username="learning-manager-extra", name="Manager extra", password_hash="unused", role="manager", store_id=stores[0].id)
        db.add_all([*staff, *managers, extra]); db.flush()
        course = LearningCourseVersion(id=str(uuid.uuid4()), code=COURSE["id"], version=COURSE["version"], status="pilot",
            content=copy.deepcopy(COURSE), content_sha256=content_hash(COURSE), approval_reference="")
        db.add(course); db.commit()
        accounts = {"a": staff[0], "b": staff[1], "other": staff[2], "manager": managers[0], "other_manager": managers[1], "manager2": extra}
        ids = {key: value.id for key, value in accounts.items()}
        headers = {key: {"Authorization": "Bearer " + create_staff_token(value.id, value.role)} for key, value in accounts.items()}
        course_id = course.id
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, factory, ids, headers, course_id, bool(url)
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()
    if url:
        with control.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def arrange(data, learner="a", manager="manager", key=None):
    client, _, ids, headers, *_ = data
    return client.post(PREFIX + "/assignments", headers=headers[manager], json={"staff_id": ids[learner],
        "course_id": COURSE["id"], "course_version": COURSE["version"], "request_id": key or str(uuid.uuid4())})


def command(data, task, kind, as_role="a", key=None, **payload):
    client, _, _, headers, *_ = data
    return client.post(PREFIX + f"/assignments/{task['id']}/actions", headers=headers[as_role],
        json={"kind": kind, "request_id": key or str(uuid.uuid4()), "expected_revision": task["revision"], **payload})


def read_all(data):
    response = arrange(data)
    assert response.status_code == 200, response.text
    task = response.json()["assignments"][0]
    for section in ("one", "two"):
        response = command(data, task, "mark_section", section_id=section)
        assert response.status_code == 200, response.text
        task = response.json()["assignments"][0]
    return task


def test_feature_off_and_anonymous(learning, monkeypatch):
    client, _, _, headers, *_ = learning
    assert client.get(PREFIX + "/bootstrap").status_code == 401
    monkeypatch.setattr(settings, "staff_learning_enabled", False)
    assert client.get(PREFIX + "/status", headers=headers["a"]).json() == {"enabled": False}
    assert client.get(PREFIX + "/bootstrap", headers=headers["a"]).status_code == 404


def test_assign_scope_and_replay(learning):
    client, factory, ids, headers, *_ = learning
    key = str(uuid.uuid4())
    first = arrange(learning, key=key)
    assert first.status_code == 200, first.text
    assert arrange(learning, key=key).status_code == 200
    assert arrange(learning, manager="manager2").status_code == 200
    assert arrange(learning, "b", key=key).status_code == 409
    assert arrange(learning, "other").status_code == 404
    assert arrange(learning, manager="a").status_code == 403
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(StaffLearningAssignment)) == 1
        assert db.scalar(select(func.count()).select_from(StaffLearningEvent)) == 2
    own = client.get(PREFIX + "/bootstrap", headers=headers["a"]).json()
    assert len(own["assignments"]) == 1 and own["roster"] == []
    assert "answer" not in str(own["courses"]) and "explanation" not in str(own["courses"])
    for who in ("b", "other", "other_manager"):
        assert client.get(PREFIX + "/bootstrap", headers=headers[who]).json()["assignments"] == []
    assert client.get(PREFIX + "/bootstrap?store_id=2", headers=headers["manager"]).status_code == 422


@pytest.mark.parametrize("who,kind,payload,status", [
    ("b", "mark_section", {"section_id": "one"}, 404),
    ("other", "mark_section", {"section_id": "one"}, 404),
    ("manager", "mark_section", {"section_id": "one"}, 403),
    ("a", "follow_up", {"note": "Cannot coach"}, 403),
    ("other_manager", "follow_up", {"note": "Other store"}, 404),
])
def test_no_proxy_or_cross_store_writes(learning, who, kind, payload, status):
    task = arrange(learning).json()["assignments"][0]
    assert command(learning, task, kind, who, **payload).status_code == status


def test_validation_and_reading_not_exam(learning):
    client, factory, _, headers, *_ = learning
    task = arrange(learning).json()["assignments"][0]
    assert command(learning, task, "mark_section", section_id="two").status_code == 422
    assert command(learning, task, "submit", answers={"q1": 1, "q2": 0}).status_code == 422
    task = read_all(learning)
    assert task["attempts"] == [] and len(task["sectionsRead"]) == 2
    for answers in ({"q1": 1}, {"q1": True, "q2": 0}, {"q1": 1, "q2": 0, "q3": 0}, {"q1": 5, "q2": 0}):
        assert command(learning, task, "submit", answers=answers).status_code == 422
    assert command(learning, task, "submit", answers={"q1": 1, "q2": 0}, correct=100).status_code == 422


def test_server_score_followup_retry_and_history(learning):
    task = read_all(learning)
    key = str(uuid.uuid4())
    first = command(learning, task, "submit", key=key, answers={"q1": 0, "q2": 0})
    assert first.status_code == 200, first.text
    saved = first.json()["assignments"][0]
    assert saved["attempts"][0]["correct"] == 1
    assert len(command(learning, task, "submit", key=key, answers={"q1": 0, "q2": 0}).json()["assignments"][0]["attempts"]) == 1
    assert command(learning, task, "submit", key=key, answers={"q1": 1, "q2": 0}).status_code == 409
    followed = command(learning, saved, "follow_up", "manager", note="Review the first question")
    assert followed.status_code == 200, followed.text
    assert followed.json()["assignments"][0]["attempts"] == saved["attempts"]
    assert command(learning, saved, "submit", answers={"q1": 1, "q2": 0}).status_code == 409
    task = followed.json()["assignments"][0]
    final = command(learning, task, "submit", answers={"q1": 1, "q2": 0})
    assert final.status_code == 200, final.text
    task = final.json()["assignments"][0]
    assert [a["correct"] for a in task["attempts"]] == [1, 2]
    assert task["followUps"][0]["note"] == "Review the first question"
    assert all("answer" not in q for c in final.json()["courses"] for q in c["questions"])


def test_role_revocation_and_content_integrity(learning):
    client, factory, ids, headers, course_id, _ = learning
    task = arrange(learning).json()["assignments"][0]
    with factory() as db:
        staff = db.get(Staff, ids["a"]); staff.status = "disabled"; db.commit()
    assert client.get(PREFIX + "/bootstrap", headers=headers["a"]).status_code == 401
    with factory() as db:
        course = db.get(LearningCourseVersion, course_id)
        changed = copy.deepcopy(course.content); changed["title"] = "Tampered"; course.content = changed; db.commit()
    assert client.get(PREFIX + "/bootstrap", headers=headers["manager"]).status_code == 409


def test_pilot_never_available_in_production(learning, monkeypatch):
    client, _, _, headers, *_ = learning
    monkeypatch.setattr(settings, "environment", "production")
    assert client.get(PREFIX + "/bootstrap", headers=headers["manager"]).json()["courses"] == []
    assert arrange(learning).status_code == 409


def test_postgres_concurrent_submit_and_assignment(learning):
    if not learning[-1]:
        pytest.skip("requires disposable PostgreSQL")
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda manager: arrange(learning, manager=manager), ["manager", "manager2"]))
    assert [r.status_code for r in results] == [200, 200]
    task = read_all(learning)
    key = str(uuid.uuid4())
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: command(learning, task, "submit", key=key, answers={"q1": 1, "q2": 0}), range(2)))
    assert [r.status_code for r in results] == [200, 200]
    assert all(len(r.json()["assignments"][0]["attempts"]) == 1 for r in results)


def test_learning_migration_roundtrip_preserves_existing_rows(learning):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    _, factory, _, _, _, _ = learning
    with factory() as db:
        engine = db.get_bind()
        before = [(s.id, s.username, s.role, s.store_id, s.credentials_version) for s in db.scalars(select(Staff).order_by(Staff.id))]
    for model in (StaffLearningEvent, StaffLearningAssignment, LearningCourseVersion):
        model.__table__.drop(engine)
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_staff_learning.py'
    spec = importlib.util.spec_from_file_location('learning_migration_test', path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
    inspector = inspect(engine)
    for model in (LearningCourseVersion, StaffLearningAssignment, StaffLearningEvent):
        columns = {c['name']: c for c in inspector.get_columns(model.__tablename__)}
        assert set(columns) == set(model.__table__.columns.keys())
        assert all(columns[c.name]['nullable'] == c.nullable for c in model.__table__.columns)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
    with factory() as db:
        after = [(s.id, s.username, s.role, s.store_id, s.credentials_version) for s in db.scalars(select(Staff).order_by(Staff.id))]
        assert after == before
        assert db.scalar(select(func.count()).select_from(Store)) == 2
