import importlib.util
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from app.db.session import Base
import app.models  # Register the complete application schema.

NEW_TABLES = {"staff_external_identities", "staff_oauth_attempts", "customer_tag_contributions"}


def load_migration():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "20261017_wecom_technician.py"
    spec = importlib.util.spec_from_file_location("wecom_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_upgrade_matches_models_and_downgrade_preserves_existing_tables():
    engine = create_engine("sqlite://")
    old_tables = [table for table in Base.metadata.sorted_tables if table.name not in NEW_TABLES]
    Base.metadata.create_all(engine, tables=old_tables)
    migration = load_migration()
    with engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) - before == NEW_TABLES
        # SQLite autogenerate treats unspecified VARCHAR lengths as equivalent.
        # Reflect actual migration output so a missing FK string bound is caught.
        for name in NEW_TABLES:
            columns = {column["name"]: column for column in inspect(connection).get_columns(name)}
            for column in Base.metadata.tables[name].columns:
                assert columns[column.name]["type"].compile(dialect=engine.dialect) == column.type.compile(dialect=engine.dialect), (name, column.name)
        context = MigrationContext.configure(connection, opts={
            "include_object": lambda obj, name, type_, reflected, compare_to: (
                name in NEW_TABLES if type_ == "table" else getattr(obj, "table", None) is None or obj.table.name in NEW_TABLES
            ),
        })
        assert compare_metadata(context, Base.metadata) == []
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert set(inspect(connection).get_table_names()) == before
    engine.dispose()
