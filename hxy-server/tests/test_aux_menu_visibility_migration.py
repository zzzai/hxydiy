import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, inspect, text


def test_visibility_migration_preserves_existing_projects_and_defaults_new_projects_visible():
    project_root = Path(__file__).resolve().parents[1]
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{Path(directory) / 'aux-menu.db'}"
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(text("INSERT INTO alembic_version VALUES ('20260923_qr_short_code')"))
            connection.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY, code VARCHAR(32))"))
            connection.execute(text("INSERT INTO projects (id, code) VALUES (8, 'hxy-baguan-1')"))
        engine.dispose()
        environment = {**os.environ, "DATABASE_URL": database_url}
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "20260924_aux_visibility"],
                       cwd=project_root, env=environment, capture_output=True, text=True, check=True)
        engine = create_engine(database_url)
        with engine.begin() as connection:
            assert connection.execute(text("SELECT independently_visible FROM projects WHERE id = 8")).scalar_one() == 1
            connection.execute(text("INSERT INTO projects (id, code) VALUES (9, 'hxy-guasha-1')"))
            assert connection.execute(text("SELECT independently_visible FROM projects WHERE id = 9")).scalar_one() == 1
        subprocess.run([sys.executable, "-m", "alembic", "downgrade", "20260923_qr_short_code"],
                       cwd=project_root, env=environment, capture_output=True, text=True, check=True)
        assert "independently_visible" not in {column["name"] for column in inspect(engine).get_columns("projects")}
        engine.dispose()
