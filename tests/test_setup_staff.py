import importlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import verify_password
from app.db.session import Base
from app.models import Staff, Store


def load_setup_staff_module():
    """Import the command module with no CLI arguments.

    The bootstrap helper must be import-safe so it can be tested without
    connecting to the production database or creating staff as a side effect.
    """
    sys.modules.pop("scripts.setup_staff", None)
    original_argv = sys.argv
    sys.argv = ["setup_staff.py"]
    try:
        return importlib.import_module("scripts.setup_staff")
    finally:
        sys.argv = original_argv


class SetupStaffTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.addCleanup(engine.dispose)
        self.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    def test_binds_each_bootstrap_staff_member_to_the_only_store(self):
        script = load_setup_staff_module()
        with self.SessionLocal() as db:
            store = Store(store_code="diy-1", name="DIY 门店", address="测试地址")
            db.add(store)
            db.commit()

            credentials = script.setup_staff(db, ["tech-1"])

            staff = db.query(Staff).filter_by(username="tech-1").one()
            self.assertEqual(credentials[0][0], "tech-1")
            self.assertTrue(verify_password(credentials[0][1], staff.password_hash))
            self.assertEqual(staff.store_id, store.id)
            self.assertEqual(staff.role, "staff")
            self.assertEqual(staff.status, "active")

    def test_refuses_to_guess_a_store_when_multiple_stores_exist(self):
        script = load_setup_staff_module()
        with self.SessionLocal() as db:
            db.add_all([
                Store(store_code="diy-1", name="DIY 门店 1", address="测试地址"),
                Store(store_code="diy-2", name="DIY 门店 2", address="测试地址"),
            ])
            db.commit()

            with self.assertRaisesRegex(RuntimeError, "唯一门店"):
                script.setup_staff(db, ["tech-1"])

    def test_credential_file_is_owner_read_write_only_even_when_it_exists(self):
        script = load_setup_staff_module()
        with TemporaryDirectory() as temporary_directory:
            credential_path = Path(temporary_directory) / "staff-credentials.txt"
            credential_path.write_text("old credentials", encoding="utf-8")
            credential_path.chmod(0o644)

            script.write_credentials(credential_path, [("tech-1", "test-password")])

            self.assertEqual(credential_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                credential_path.read_text(encoding="utf-8"),
                "username: tech-1\npassword: test-password\n",
            )


if __name__ == "__main__":
    unittest.main()
