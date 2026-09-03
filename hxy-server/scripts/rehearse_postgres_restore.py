"""Restore a PostgreSQL dump into an isolated database and verify migrations.

The target database name must clearly identify a disposable rehearsal database.
This script never connects to or mutates the source production database.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url


SAFE_DATABASE_NAME = re.compile(r"^[A-Za-z0-9_]+$")
SAFE_MARKERS = ("restore", "rehearsal", "test")


def validate_rehearsal_database_name(name: str) -> str:
    if not SAFE_DATABASE_NAME.fullmatch(name):
        raise ValueError("rehearsal database name must contain only letters, numbers, and underscores")
    lowered = name.lower()
    if "production" in lowered or "prod" in lowered:
        raise ValueError("refusing a database name that appears to reference production")
    if not any(marker in lowered for marker in SAFE_MARKERS):
        raise ValueError("rehearsal database name must include restore, rehearsal, or test")
    if lowered in {"postgres", "template0", "template1", "hxy", "hxy_diy"}:
        raise ValueError("refusing to use a production or system database name")
    return name


def postgres_cli_env(url: URL) -> dict[str, str]:
    environment = os.environ.copy()
    if url.host:
        environment["PGHOST"] = url.host
    if url.port:
        environment["PGPORT"] = str(url.port)
    if url.username:
        environment["PGUSER"] = url.username
    if url.password:
        environment["PGPASSWORD"] = url.password
    return environment


def target_database_url(admin_url: URL, database: str) -> str:
    driver = admin_url.drivername
    if driver == "postgresql":
        driver = "postgresql+psycopg"
    return admin_url.set(drivername=driver, database=database).render_as_string(
        hide_password=False
    )


def run_checked(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--admin-url", required=True)
    parser.add_argument("--database", default="hxy_diy_restore_rehearsal")
    parser.add_argument("--keep-database", action="store_true")
    parser.add_argument(
        "--confirm-isolated-restore",
        action="store_true",
        help="Required acknowledgement that the target is disposable and isolated.",
    )
    args = parser.parse_args()

    if not args.confirm_isolated_restore:
        parser.error("--confirm-isolated-restore is required")
    dump = args.dump.resolve()
    if not dump.is_file():
        parser.error(f"dump file not found: {dump}")
    database = validate_rehearsal_database_name(args.database)
    admin_url = make_url(args.admin_url)
    if not admin_url.drivername.startswith("postgresql"):
        parser.error("--admin-url must be a PostgreSQL URL")

    project_root = Path(__file__).resolve().parents[1]
    environment = postgres_cli_env(admin_url)
    database_url = target_database_url(admin_url, database)
    migration_environment = {**environment, "DATABASE_URL": database_url}
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    database_created = False

    try:
        with engine.connect() as connection:
            existing = connection.exec_driver_sql(
                "SELECT 1 FROM pg_database WHERE datname = %s", (database,)
            ).scalar()
            if existing:
                raise RuntimeError(
                    f"rehearsal database already exists; refusing to overwrite: {database}"
                )
            connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
            database_created = True

        run_checked(
            [
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                database,
                str(dump),
            ],
            cwd=project_root,
            env=environment,
        )
        run_checked(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=project_root,
            env=migration_environment,
        )
        run_checked(
            [sys.executable, "scripts/verify_selection_closure_upgrade.py"],
            cwd=project_root,
            env=migration_environment,
        )
        run_checked(
            [
                sys.executable,
                "scripts/inspect_schema_drift.py",
                "--database-url",
                database_url,
                "--fail-on-drift",
            ],
            cwd=project_root,
            env=environment,
        )
        print(f"restore rehearsal verified: {database}")
    finally:
        engine.dispose()
        if database_created and not args.keep_database:
            cleanup_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
            try:
                with cleanup_engine.connect() as connection:
                    connection.exec_driver_sql(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()",
                        (database,),
                    )
                    connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database}"')
            finally:
                cleanup_engine.dispose()


if __name__ == "__main__":
    main()
