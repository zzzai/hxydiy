import importlib.util

import pytest
from sqlalchemy import create_engine, text

from app.api.admin import normalize_staff_role


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "normalize_staff_roles",
        "alembic/versions/20260826_normalize_staff_roles.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _db():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE staff (id INTEGER PRIMARY KEY, username VARCHAR(32), role VARCHAR(16), technician_id INTEGER)")
        conn.exec_driver_sql("CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, detail JSON)")
        conn.exec_driver_sql("CREATE UNIQUE INDEX uq_staff_technician_id ON staff (technician_id)")
    return engine


def test_migration_maps_admin_to_manager_and_bound_staff_to_technician():
    engine = _db()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO staff(id,username,role,technician_id) VALUES (1,'a','admin',NULL),(2,'t','staff',7)"))
    module = _migration_module()
    module.normalize_roles(engine.connect())
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT role FROM staff ORDER BY id")).scalars().all()
    assert rows == ["manager", "technician"]


def test_migration_rejects_unbound_staff():
    engine = _db()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO staff(id,username,role,technician_id) VALUES (1,'orphan','staff',NULL)"))
    module = _migration_module()
    with pytest.raises(RuntimeError, match="orphan"):
        module.normalize_roles(engine.connect())


def test_migration_unique_technician_binding_is_enforced():
    engine = _db()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO staff(id,username,role,technician_id) VALUES (1,'a','staff',7)"))
        with pytest.raises(Exception):
            conn.execute(text("INSERT INTO staff(id,username,role,technician_id) VALUES (2,'b','staff',7)"))


def test_legacy_audit_role_value_is_not_rewritten():
    engine = _db()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO audit_logs(id,detail) VALUES (1, '{\"role\":\"admin\"}')"))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT detail FROM audit_logs WHERE id=1")).scalar_one() == '{"role":"admin"}'


def test_unbound_legacy_staff_never_leaks_staff_as_a_public_role():
    with pytest.raises(ValueError):
        normalize_staff_role("staff")


def test_unknown_role_is_rejected_instead_of_falling_back():
    with pytest.raises(ValueError):
        normalize_staff_role("superuser")
