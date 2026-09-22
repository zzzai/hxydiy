import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


class StaffScopeAssignmentMigrationTests(unittest.TestCase):
    def test_upgrade_backfills_grants_and_protects_admin_credentials(self):
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "staff-scope.db"
            database_url = f"sqlite:///{database_path}"
            engine = create_engine(database_url)
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
                connection.execute(text("INSERT INTO alembic_version VALUES ('20260921_product_catalog')"))
                connection.execute(text("CREATE TABLE stores (id INTEGER PRIMARY KEY, name VARCHAR(128) NOT NULL)"))
                connection.execute(text("INSERT INTO stores VALUES (1, '一号店'), (2, '二号店')"))
                connection.execute(text("""
                    CREATE TABLE staff (
                        id INTEGER PRIMARY KEY,
                        username VARCHAR(32) NOT NULL,
                        password_hash VARCHAR(128) NOT NULL,
                        name VARCHAR(32) NOT NULL,
                        role VARCHAR(16) NOT NULL,
                        store_id INTEGER,
                        technician_id INTEGER,
                        status VARCHAR(16) NOT NULL,
                        credentials_version INTEGER NOT NULL
                    )
                """))
                connection.execute(text("""
                    INSERT INTO staff VALUES
                    (1, 'admin', 'admin-hash', '管理员', 'admin', 1, NULL, 'active', 5),
                    (2, 'manager-a', 'manager-hash', '店长', 'manager', 1, NULL, 'active', 3),
                    (3, 'staff-a', 'staff-hash', '员工', 'staff', 2, NULL, 'inactive', 4),
                    (4, 'tech-a', 'tech-hash', '技师', 'technician', 1, 8, 'active', 7)
                """))
                connection.execute(text("""
                    CREATE TABLE audit_logs (
                        id INTEGER PRIMARY KEY,
                        actor_type VARCHAR(16) NOT NULL,
                        actor_id VARCHAR(64) NOT NULL,
                        store_id INTEGER,
                        action VARCHAR(64) NOT NULL,
                        entity_type VARCHAR(32) NOT NULL,
                        entity_id VARCHAR(64) NOT NULL,
                        detail JSON NOT NULL,
                        created_at DATETIME
                    )
                """))
            engine.dispose()

            environment = {**os.environ, "DATABASE_URL": database_url}
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=project_root,
                env=environment,
                capture_output=True,
                text=True,
                check=True,
            )

            engine = create_engine(database_url)
            with engine.begin() as connection:
                admin = connection.execute(text("SELECT password_hash, role, store_id, credentials_version FROM staff WHERE id = 1")).one()
                self.assertEqual(admin, ("admin-hash", "admin", None, 6))
                manager = connection.execute(text("SELECT credentials_version FROM staff WHERE id = 2")).scalar_one()
                staff = connection.execute(text("SELECT credentials_version FROM staff WHERE id = 3")).scalar_one()
                technician = connection.execute(text("SELECT role, store_id, credentials_version FROM staff WHERE id = 4")).one()
                self.assertEqual((manager, staff), (3, 4))
                self.assertEqual(technician, ("technician", 1, 7))
                assignments = connection.execute(text("""
                    SELECT staff_id, role, scope_type, scope_id, status
                    FROM staff_scope_assignments ORDER BY staff_id
                """)).all()
                self.assertEqual(assignments, [
                    (1, "brand_admin", "brand", None, "active"),
                    (2, "store_manager", "store", 1, "active"),
                    (3, "store_staff", "store", 2, "disabled"),
                ])
                with self.assertRaises(IntegrityError):
                    connection.execute(text("""
                        INSERT INTO staff_scope_assignments
                        (staff_id, role, scope_type, scope_id, status)
                        VALUES (2, 'store_manager', 'store', 1, 'active')
                    """))

            with engine.connect() as connection:
                audit_columns = {column["name"] for column in inspect(connection).get_columns("audit_logs")}
                self.assertTrue({"assignment_id", "actor_role", "scope_type", "scope_id"}.issubset(audit_columns))
            engine.dispose()

            subprocess.run(
                [sys.executable, "-m", "alembic", "downgrade", "20260921_product_catalog"],
                cwd=project_root,
                env=environment,
                capture_output=True,
                text=True,
                check=True,
            )
            engine = create_engine(database_url)
            with engine.connect() as connection:
                inspector = inspect(connection)
                self.assertNotIn("staff_scope_assignments", inspector.get_table_names())
                audit_columns = {column["name"] for column in inspector.get_columns("audit_logs")}
                self.assertFalse({"assignment_id", "actor_role", "scope_type", "scope_id"} & audit_columns)
                self.assertEqual(connection.execute(text("SELECT password_hash FROM staff WHERE id = 1")).scalar_one(), "admin-hash")
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
