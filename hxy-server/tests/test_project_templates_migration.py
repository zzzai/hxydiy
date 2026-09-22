import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


class ProjectTemplatesMigrationTests(unittest.TestCase):
    """MULTI-STORE-005 PR1：门店项目回填为品牌模板，价格快照逐项一致。"""

    def test_upgrade_backfills_templates_and_price_policies(self):
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "project-templates.db"
            database_url = f"sqlite:///{database_path}"
            engine = create_engine(database_url)
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
                connection.execute(text("INSERT INTO alembic_version VALUES ('20260921_staff_scope')"))
                connection.execute(text("CREATE TABLE stores (id INTEGER PRIMARY KEY, name VARCHAR(128) NOT NULL)"))
                connection.execute(text("INSERT INTO stores VALUES (1, '一号店')"))
                connection.execute(text("""
                    CREATE TABLE projects (
                        id INTEGER PRIMARY KEY,
                        store_id INTEGER NOT NULL,
                        code VARCHAR(32) NOT NULL,
                        category VARCHAR(32) NOT NULL,
                        name VARCHAR(64) NOT NULL,
                        duration_min INTEGER,
                        summary VARCHAR(512),
                        image_url VARCHAR(512),
                        tags JSON,
                        detail_modules JSON,
                        display_order INTEGER NOT NULL
                    )
                """))
                connection.execute(text("""
                    INSERT INTO projects VALUES
                    (1, 1, 'Z1-BATH-01', 'bath', '草本足浴', 60, '现煮草本', '/img/bath.png',
                     '["现煮"]', '[{"type": "text"}]', 1),
                    (2, 1, 'Z1-CARE-01', 'care', '肩颈护理', 45, '', '', '[]', NULL, 2)
                """))
                connection.execute(text("""
                    CREATE TABLE price_book (
                        id INTEGER PRIMARY KEY,
                        project_id INTEGER NOT NULL,
                        price_type VARCHAR(16) NOT NULL,
                        amount_cents INTEGER NOT NULL,
                        version VARCHAR(32),
                        publisher VARCHAR(64),
                        published_at DATETIME,
                        effective_to DATETIME
                    )
                """))
                connection.execute(text("""
                    INSERT INTO price_book VALUES
                    (1, 1, 'store', 12800, 'v1', 'system', '2026-09-01 00:00:00', NULL),
                    (2, 1, 'member', 9800, 'v1', 'system', '2026-09-01 00:00:00', NULL),
                    (3, 1, 'group', 8800, 'v1', 'system', '2026-09-01 00:00:00', NULL),
                    (4, 1, 'store', 9999, 'v0', 'system', '2026-08-01 00:00:00', '2026-09-01 00:00:00'),
                    (5, 1, 'store', 11800, 'v2', 'system', '2026-09-10 00:00:00', NULL),
                    (6, 2, 'store', 6600, 'v1', 'system', '2026-09-01 00:00:00', NULL)
                """))
                connection.execute(text("""
                    CREATE TABLE products (
                        id INTEGER PRIMARY KEY,
                        store_id INTEGER NOT NULL,
                        code VARCHAR(32) NOT NULL,
                        price_cents INTEGER NOT NULL,
                        member_price_cents INTEGER
                    )
                """))
                connection.execute(text("INSERT INTO products VALUES (1, 1, 'Z1-TEA-01', 1500, 1200)"))
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
                templates = connection.execute(text("""
                    SELECT code, name, category, duration_min, desc, image_url, display_order, brand_enabled
                    FROM project_templates ORDER BY id
                """)).all()
                self.assertEqual(templates, [
                    ("Z1-BATH-01", "草本足浴", "bath", 60, "现煮草本", "/img/bath.png", 1, 1),
                    ("Z1-CARE-01", "肩颈护理", "care", 45, "", "", 2, 1),
                ])
                links = connection.execute(text("""
                    SELECT p.id, t.code FROM projects p
                    JOIN project_templates t ON t.id = p.template_id ORDER BY p.id
                """)).all()
                self.assertEqual(links, [(1, "Z1-BATH-01"), (2, "Z1-CARE-01")])
                policies = connection.execute(text("""
                    SELECT t.code, pp.price_type, pp.standard_price_cents,
                           pp.override_allowed, pp.force_standard
                    FROM template_price_policies pp
                    JOIN project_templates t ON t.id = pp.template_id
                    ORDER BY t.code, pp.price_type
                """)).all()
                # 过期行（9999）被排除；同类型多条现行价取最新（11800）。
                self.assertEqual(policies, [
                    ("Z1-BATH-01", "group", 8800, 1, 0),
                    ("Z1-BATH-01", "member", 9800, 1, 0),
                    ("Z1-BATH-01", "store", 11800, 1, 0),
                    ("Z1-CARE-01", "store", 6600, 1, 0),
                ])
                toggles = connection.execute(text(
                    "SELECT member_price_enabled FROM projects ORDER BY id"
                )).scalars().all()
                self.assertEqual(toggles, [0, 0])
                product_toggle = connection.execute(text(
                    "SELECT member_price_enabled FROM products WHERE id = 1"
                )).scalar_one()
                self.assertEqual(product_toggle, 0)
                with self.assertRaises(IntegrityError):
                    connection.execute(text("""
                        INSERT INTO template_price_policies
                        (template_id, price_type, standard_price_cents, override_allowed, force_standard)
                        VALUES (1, 'store', 100, 1, 0)
                    """))

            with engine.connect() as connection:
                inspector = inspect(connection)
                self.assertTrue(
                    {"project_templates", "template_price_policies", "store_price_overrides"}
                    .issubset(set(inspector.get_table_names()))
                )
                project_columns = {column["name"] for column in inspector.get_columns("projects")}
                self.assertTrue({"template_id", "member_price_enabled"}.issubset(project_columns))
            engine.dispose()

            subprocess.run(
                [sys.executable, "-m", "alembic", "downgrade", "20260921_staff_scope"],
                cwd=project_root,
                env=environment,
                capture_output=True,
                text=True,
                check=True,
            )
            engine = create_engine(database_url)
            with engine.connect() as connection:
                inspector = inspect(connection)
                self.assertFalse(
                    {"project_templates", "template_price_policies", "store_price_overrides"}
                    & set(inspector.get_table_names())
                )
                project_columns = {column["name"] for column in inspector.get_columns("projects")}
                self.assertFalse({"template_id", "member_price_enabled"} & project_columns)
                product_columns = {column["name"] for column in inspector.get_columns("products")}
                self.assertNotIn("member_price_enabled", product_columns)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
