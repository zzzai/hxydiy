import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import Staff, Store
from scripts.setup_admin import setup_admin, write_credentials


class SetupAdminTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.addCleanup(engine.dispose)
        self.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    def test_binds_the_bootstrap_admin_to_the_only_store(self):
        with self.SessionLocal() as db:
            store = Store(store_code="diy-1", name="DIY 门店", address="测试地址")
            db.add(store)
            db.commit()

            password = setup_admin(db)

            admin = db.query(Staff).filter_by(username="admin").one()
            self.assertTrue(password)
            self.assertEqual(admin.store_id, store.id)
            self.assertEqual(admin.role, "admin")
            self.assertEqual(admin.status, "active")

    def test_refuses_to_guess_a_store_when_multiple_stores_exist(self):
        with self.SessionLocal() as db:
            db.add_all([
                Store(store_code="diy-1", name="DIY 门店 1", address="测试地址"),
                Store(store_code="diy-2", name="DIY 门店 2", address="测试地址"),
            ])
            db.commit()

            with self.assertRaisesRegex(RuntimeError, "唯一门店"):
                setup_admin(db)

    def test_credential_file_is_owner_read_write_only_even_when_it_exists(self):
        with TemporaryDirectory() as temporary_directory:
            credential_path = Path(temporary_directory) / "admin-credentials.txt"
            credential_path.write_text("old credentials", encoding="utf-8")
            credential_path.chmod(0o644)

            write_credentials(credential_path, "admin", "test-password")

            if os.name == "posix":
                self.assertEqual(credential_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                credential_path.read_text(encoding="utf-8"),
                "username: admin\npassword: test-password\n",
            )


if __name__ == "__main__":
    unittest.main()
