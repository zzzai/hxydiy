import importlib.util
import os
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import Base
from app.models import Staff, Store, Technician
from app.models.staff_external_identity import StaffExternalIdentity
from test_wecom_migration import NEW_TABLES, load_migration


def load_manager_migration():
    path = Path(__file__).parents[1] / 'alembic/versions/20261018_wecom_store_manager.py'
    spec = importlib.util.spec_from_file_location('manager_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


@pytest.fixture
def engine():
    url = os.environ.get('WECOM_TEST_DATABASE_URL')
    if url:
        if make_url(url).database != 'wecom_test' or settings.environment != 'test':
            raise RuntimeError('Isolated test database required')
        bootstrap = create_engine(url)
        with bootstrap.begin() as connection:
            connection.execute(text('CREATE SCHEMA manager_migration'))
        bootstrap.dispose()
        engine = create_engine(url, connect_args={'options': '-csearch_path=manager_migration'})
    else:
        engine = create_engine('sqlite://')
    try:
        Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in NEW_TABLES])
        with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
            load_migration().upgrade()
        yield engine
    finally:
        if url:
            with engine.begin() as connection:
                assert connection.scalar(text('SELECT current_schema()')) == 'manager_migration'
                connection.execute(text('DROP SCHEMA manager_migration CASCADE'))
        engine.dispose()


@pytest.mark.parametrize('has_manager', [False, True])
def test_nullable_upgrade_preserves_rows_constraints_and_safe_downgrade(engine, has_manager):
    table = StaffExternalIdentity.__table__
    with Session(engine) as db:
        store = Store(store_code='migration-synthetic', name='Synthetic', address='Synthetic')
        db.add(store)
        db.flush()
        tech = Technician(store_id=store.id, code='migration-tech', name='Synthetic')
        db.add(tech)
        db.flush()
        staff = Staff(username='migration-tech', name='Synthetic', role='technician', password_hash='unused',
            store_id=store.id, technician_id=tech.id)
        db.add(staff)
        db.flush()
        db.add(StaffExternalIdentity(corp_id='synthetic', userid='existing', staff_id=staff.id, technician_id=tech.id, store_id=store.id))
        db.commit()
        store_id = store.id
    migration = load_manager_migration()
    with engine.begin() as connection:
        before = list(connection.execute(select(table)).mappings())
        foreign_keys = inspect(connection).get_foreign_keys(table.name)
        indexes = inspect(connection).get_indexes(table.name)
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert list(connection.execute(select(table)).mappings()) == before
        assert sorted(inspect(connection).get_foreign_keys(table.name), key=lambda row: row['constrained_columns']) == sorted(foreign_keys, key=lambda row: row['constrained_columns'])
        assert [row['name'] for row in inspect(connection).get_indexes(table.name)] == [row['name'] for row in indexes]
        context = MigrationContext.configure(connection, opts={'include_object': lambda obj, name, kind, reflected, compare_to:
            name == table.name if kind == 'table' else getattr(obj, 'table', None) is None or obj.table.name == table.name})
        assert compare_metadata(context, Base.metadata) == []
    if has_manager:
        with Session(engine) as db:
            staff = Staff(username='migration-manager', name='Synthetic manager', role='manager', password_hash='unused', store_id=store_id)
            db.add(staff)
            db.flush()
            db.add(StaffExternalIdentity(corp_id='synthetic', userid='new-manager', staff_id=staff.id, technician_id=None, store_id=store_id))
            db.commit()
        with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match='preserve data'):
                migration.downgrade()
            assert len(list(connection.execute(select(table)))) == 2
    else:
        with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert list(connection.execute(select(table)).mappings()) == before
            column = next(item for item in inspect(connection).get_columns(table.name) if item['name'] == 'technician_id')
            assert column['nullable'] is False
