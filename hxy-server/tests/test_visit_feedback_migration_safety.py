"""Reject incomplete pre-existing feedback tables during migration."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text


def test_existing_incomplete_visit_feedback_table_fails_before_stamping_revision():
    project_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
        database_url = f"sqlite:///{Path(directory) / 'feedback-migration.db'}"
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(text("INSERT INTO alembic_version VALUES ('20260921_product_catalog')"))
            connection.execute(text("CREATE TABLE visit_feedback (id INTEGER PRIMARY KEY)"))
        engine.dispose()

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260921_visit_feedback"],
            cwd=project_root,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "Incomplete existing visit_feedback table" in result.stderr
        engine = create_engine(database_url)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260921_product_catalog"
        engine.dispose()


def test_existing_complete_visit_feedback_table_can_resume_migration():
    project_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
        database_url = f"sqlite:///{Path(directory) / 'feedback-resume.db'}"
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(text("INSERT INTO alembic_version VALUES ('20260921_product_catalog')"))
        engine.dispose()
        environment = {**os.environ, "DATABASE_URL": database_url}
        command = [sys.executable, "-m", "alembic", "upgrade", "20260921_visit_feedback"]
        subprocess.run(command, cwd=project_root, env=environment, capture_output=True, text=True, check=True)
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = '20260921_product_catalog'"))
        engine.dispose()
        subprocess.run(command, cwd=project_root, env=environment, capture_output=True, text=True, check=True)
        engine = create_engine(database_url)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260921_visit_feedback"
        engine.dispose()
