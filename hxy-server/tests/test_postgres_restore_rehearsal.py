import unittest

from scripts.rehearse_postgres_restore import (
    target_database_url,
    validate_rehearsal_database_name,
)
from sqlalchemy.engine import make_url


class PostgresRestoreRehearsalTests(unittest.TestCase):
    def test_accepts_only_disposable_rehearsal_database_names(self):
        self.assertEqual(
            validate_rehearsal_database_name("hxy_diy_restore_rehearsal"),
            "hxy_diy_restore_rehearsal",
        )
        for name in ("hxy_diy", "postgres", "production_restore", "restore-db"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    validate_rehearsal_database_name(name)

    def test_builds_target_url_without_losing_credentials(self):
        admin_url = make_url(
            "postgresql+psycopg://hxy_admin:secret@example.test:5432/hxy_diy"
        )
        self.assertEqual(
            target_database_url(admin_url, "hxy_diy_restore_test"),
            "postgresql+psycopg://hxy_admin:secret@example.test:5432/hxy_diy_restore_test",
        )


if __name__ == "__main__":
    unittest.main()
