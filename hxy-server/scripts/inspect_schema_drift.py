"""Read-only comparison between a SQLAlchemy database and registered models."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect

# Allow `python scripts/inspect_schema_drift.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import Base
from app import models  # noqa: F401  # register all model tables


def build_report(database_url: str) -> dict[str, Any]:
    engine = create_engine(database_url)
    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names())
    ignored_tables = sorted(actual_tables & {"alembic_version"})
    actual_tables -= set(ignored_tables)
    model_tables = set(Base.metadata.tables)
    table_reports: list[dict[str, Any]] = []

    for table_name in sorted(actual_tables & model_tables):
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        model_columns = set(Base.metadata.tables[table_name].columns.keys())
        if actual_columns != model_columns:
            table_reports.append(
                {
                    "table": table_name,
                    "missing_in_database": sorted(model_columns - actual_columns),
                    "extra_in_database": sorted(actual_columns - model_columns),
                }
            )

    return {
        "database_url": database_url,
        "ignored_tables": ignored_tables,
        "database_tables": sorted(actual_tables),
        "model_tables": sorted(model_tables),
        "missing_tables": sorted(model_tables - actual_tables),
        "extra_tables": sorted(actual_tables - model_tables),
        "column_drift": table_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default="sqlite:///./hxy_dev.db",
        help="SQLAlchemy database URL; the command never writes schema or data",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="return exit code 1 when tables or columns differ",
    )
    args = parser.parse_args()
    report = build_report(args.database_url)

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"database tables: {len(report['database_tables'])}")
        print(f"model tables: {len(report['model_tables'])}")
        print(f"missing tables: {', '.join(report['missing_tables']) or '-'}")
        print(f"extra tables: {', '.join(report['extra_tables']) or '-'}")
        for drift in report["column_drift"]:
            print(
                f"{drift['table']}: "
                f"missing={','.join(drift['missing_in_database']) or '-'} "
                f"extra={','.join(drift['extra_in_database']) or '-'}"
            )

    has_drift = bool(report["missing_tables"] or report["extra_tables"] or report["column_drift"])
    return 1 if args.fail_on_drift and has_drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
