"""The roomless migration preserves feedback and refuses destructive downgrade."""

import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import CheckConstraint, MetaData, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models import Room, Store, VisitFeedback
from app.db.session import Base
from test_visit_feedback_postgres_concurrency import _isolated_postgres_url


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_store_feedback_upgrade_preserves_rows_and_downgrade_is_guarded(tmp_path, backend):
    root = Path(__file__).resolve().parents[1]
    database_url = f"sqlite:///{tmp_path / 'store-feedback-migration.db'}"
    if backend == "postgresql":
        database_url = make_url(_isolated_postgres_url()).set(database="hxy_feedback_migration_ci").render_as_string(hide_password=False)

    def migrate(action, revision):
        return subprocess.run(
            [sys.executable, "-m", "alembic", action, revision], cwd=root,
            env={**os.environ, "DATABASE_URL": database_url}, text=True, capture_output=True,
        )

    engine = create_engine(database_url)
    # The migration chain assumes the legacy base tables already exist.
    previous = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(previous)
    previous.tables["visit_feedback"].c.room_id.nullable = False
    previous.tables["visit_feedback"].append_constraint(CheckConstraint("rating BETWEEN 1 AND 5", name="ck_visit_feedback_rating"))
    previous.tables["visit_feedback"].append_constraint(CheckConstraint(
        "follow_up_status IN ('open', 'in_progress', 'resolved', 'dismissed')", name="ck_visit_feedback_follow_up_status",
    ))
    previous.create_all(engine)
    result = migrate("stamp", "20261025_exception_owner")
    assert result.returncode == 0, result.stderr
    with Session(engine) as db, db.begin():
        db.add(Store(id=1, store_code="migration-store-feedback", name="Synthetic", address="Test", status="open"))
        db.flush()
        db.add(Room(id=1, store_id=1, code="migration-room", name="Synthetic room"))
        db.flush()
        db.add(VisitFeedback(
            id=1, store_id=1, room_id=1, source="personal_qr", rating=5, tags=[], note="keep this fact",
            identity_hash="a" * 64, idempotency_key_hash="b" * 64, request_fingerprint="c" * 64,
        ))
    with engine.connect() as connection:
        original = dict(connection.execute(text("SELECT * FROM visit_feedback WHERE id=1")).mappings().one())
    original_indexes = inspect(engine).get_indexes("visit_feedback")
    original_foreign_keys = sorted(inspect(engine).get_foreign_keys("visit_feedback"), key=lambda item: item["constrained_columns"])
    original_checks = inspect(engine).get_check_constraints("visit_feedback")
    original_unique = inspect(engine).get_unique_constraints("visit_feedback")
    result = migrate("upgrade", "20261023_store_feedback")
    assert result.returncode == 0, result.stderr
    assert next(c for c in inspect(engine).get_columns("visit_feedback") if c["name"] == "room_id")["nullable"]
    assert inspect(engine).get_indexes("visit_feedback") == original_indexes
    assert sorted(inspect(engine).get_foreign_keys("visit_feedback"), key=lambda item: item["constrained_columns"]) == original_foreign_keys
    assert inspect(engine).get_check_constraints("visit_feedback") == original_checks
    assert inspect(engine).get_unique_constraints("visit_feedback") == original_unique
    with engine.connect() as connection:
        assert dict(connection.execute(text("SELECT * FROM visit_feedback WHERE id=1")).mappings().one()) == original
    result = migrate("downgrade", "20261025_exception_owner")
    assert result.returncode == 0, result.stderr
    assert not next(c for c in inspect(engine).get_columns("visit_feedback") if c["name"] == "room_id")["nullable"]
    result = migrate("upgrade", "20261023_store_feedback")
    assert result.returncode == 0, result.stderr
    with Session(engine) as db, db.begin():
        db.add(VisitFeedback(
            id=2, store_id=1, room_id=None, source="store_qr", rating=4, tags=[], note="keep roomless fact",
            identity_hash="d" * 64, idempotency_key_hash="e" * 64, request_fingerprint="f" * 64,
        ))
    result = migrate("downgrade", "20261025_exception_owner")
    assert result.returncode != 0
    assert "roomless visit feedback" in result.stderr
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261023_store_feedback"
        assert connection.execute(text("SELECT count(*) FROM visit_feedback")).scalar_one() == 2
        assert dict(connection.execute(text("SELECT * FROM visit_feedback WHERE id=1")).mappings().one()) == original
        assert connection.execute(text("SELECT note FROM visit_feedback WHERE id=2")).scalar_one() == "keep roomless fact"
    engine.dispose()
