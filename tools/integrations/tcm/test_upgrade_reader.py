"""Synthetic filesystem/SQLite upgrade and rollback tests; no systemd calls."""
import hashlib
import importlib.util
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.name == "posix", "Run ownership/atomic upgrade checks on Linux")
class UpgradeReaderTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location("reader_upgrade",Path(__file__).with_name("upgrade_reader.py"))
        self.module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)/"tcm"
        (self.root/"data").mkdir(parents=True)
        self.old=self.root/"readonly_reports.py"
        self.old.write_bytes(b"# original reader\n")
        self.old.chmod(0o640)
        self.old_digest=hashlib.sha256(self.old.read_bytes()).hexdigest()
        self.source=Path(self.temporary.name)/"reviewed.py"
        self.source.write_bytes(Path(__file__).with_name("readonly_reports.py").read_bytes())
        self.new_digest=hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.database=self.root/"data/tcm.db"
        with sqlite3.connect(self.database) as db:
            db.execute("CREATE TABLE tcm_reports(report_no TEXT,phone TEXT,report_time TEXT,structured_data TEXT,heart_rate TEXT,blood_oxygen TEXT,moisture_index TEXT,report_print_url TEXT)")
            db.execute("INSERT INTO tcm_reports(report_no) VALUES('fixture')")
        self.main=self.root/"main.py"
        self.main.write_bytes(b"# unchanged mount\n")
        self.environment=self.root/"private.env"
        self.environment.write_bytes(b"UNCHANGED_FIXTURE=1\n")

    def upgrade(self, install=True, old_digest=None):
        return self.module.upgrade(self.root,self.source,self.database,old_digest or self.old_digest,self.new_digest,install=install)

    def unchanged_database_and_configuration(self):
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM tcm_reports").fetchone()[0],1)
        self.assertEqual(self.main.read_bytes(),b"# unchanged mount\n")
        self.assertEqual(self.environment.read_bytes(),b"UNCHANGED_FIXTURE=1\n")

    def test_preflight_and_hash_mismatch_never_replace_or_restart(self):
        with patch.object(self.module,"restart_service",side_effect=AssertionError("No restart in preflight")):
            result=self.upgrade(install=False)
            self.assertEqual(result["status"],"preflight_passed")
            with self.assertRaises(self.module.UpgradeError):
                self.upgrade(old_digest="0"*64)
        self.assertEqual(self.old.read_bytes(),b"# original reader\n")
        self.assertEqual(list((self.root/"data").glob("reader-original-backup-*")),[])
        self.unchanged_database_and_configuration()

    def test_atomic_upgrade_preserves_owner_mode_and_verified_restore_copy(self):
        previous=self.old.stat()
        with patch.object(self.module,"restart_service"),patch.object(self.module,"healthy",return_value=True):
            result=self.upgrade()
        self.assertEqual(result["status"],"installed")
        self.assertEqual(hashlib.sha256(self.old.read_bytes()).hexdigest(),self.new_digest)
        self.assertEqual((self.old.stat().st_uid,self.old.stat().st_gid),(previous.st_uid,previous.st_gid))
        self.assertEqual(stat.S_IMODE(self.old.stat().st_mode),0o640)
        backup=Path(result["backup"])
        self.assertEqual(hashlib.sha256((backup/"readonly_reports.py").read_bytes()).hexdigest(),self.old_digest)
        for name in ("tcm.db","restore-check.db"):
            with sqlite3.connect(backup/name) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                self.assertEqual(db.execute("SELECT count(*) FROM tcm_reports").fetchone()[0],1)
        self.unchanged_database_and_configuration()

    def test_health_failure_restores_only_reader_and_recovers_original_health(self):
        with patch.object(self.module,"restart_service"),patch.object(self.module,"healthy",side_effect=[False,True]):
            result=self.upgrade()
        self.assertEqual(result["status"],"failed_restored")
        self.assertTrue(result["original_health_ok"])
        self.assertEqual(self.old.read_bytes(),b"# original reader\n")
        self.unchanged_database_and_configuration()


if __name__ == "__main__":
    unittest.main()
