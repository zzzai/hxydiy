"""Coordinator-only atomic upgrade of an already installed readonly reader."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import time
import uuid


class UpgradeError(Exception):
    pass


def restart_service():
    result = subprocess.run(["systemctl", "restart", "tcm-webhook.service"], capture_output=True)
    if result.returncode:
        raise UpgradeError("RESTART_FAILED")


def healthy():
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        connection = http.client.HTTPConnection("172.18.0.1", 18090, timeout=2, source_address=("127.0.0.1", 0))
        try:
            connection.request("GET", "/health")
            if connection.getresponse().status == 200:
                return True
        except OSError:
            pass
        finally:
            connection.close()
        time.sleep(0.25)
    return False


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_module(target, content, owner):
    temporary = target.with_name(".readonly-reader-" + uuid.uuid4().hex + ".tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fchown(stream.fileno(), owner.st_uid, owner.st_gid)
            os.fchmod(stream.fileno(), 0o640)
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        descriptor = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def verified_backup(database, backup):
    deadline = time.monotonic() + 30
    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise UpgradeError("BACKUP_TIMEOUT")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=5)) as source:
        source.execute("PRAGMA query_only=ON")
        with closing(sqlite3.connect(backup / "tcm.db")) as target:
            source.backup(target, pages=256, progress=progress)
            if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise UpgradeError("BACKUP_INTEGRITY_FAILED")
            with closing(sqlite3.connect(backup / "restore-check.db")) as restored:
                target.backup(restored, pages=256, progress=progress)
                if restored.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise UpgradeError("RESTORE_INTEGRITY_FAILED")
    for name in ("tcm.db", "restore-check.db"):
        (backup / name).chmod(0o600)


def upgrade(root, source, database, old_digest, new_digest, *, install=False, sample_id=None):
    if os.name != "posix" or any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in (old_digest, new_digest)):
        raise UpgradeError("INVALID_PLATFORM_OR_DIGEST")
    root = Path(root).resolve(strict=True)
    source, database = Path(source), Path(database)
    target = root / "readonly_reports.py"
    if any(path.is_symlink() for path in (source, database, target)):
        raise UpgradeError("SYMLINK_TARGET_REJECTED")
    source, database = source.resolve(strict=True), database.resolve(strict=True)
    if root not in database.parents or source == target or not all(path.is_file() for path in (target, source, database)):
        raise UpgradeError("INVALID_SCOPE")
    previous = target.read_bytes()
    reviewed = source.read_bytes()
    owner = target.stat()
    if stat.S_IMODE(owner.st_mode) != 0o640:
        raise UpgradeError("UNEXPECTED_READER_MODE")
    if digest(previous) != old_digest or digest(reviewed) != new_digest:
        raise UpgradeError("MODULE_DIGEST_MISMATCH")
    compiled = compile(reviewed, str(source), "exec")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
        db.execute("PRAGMA query_only=ON")
        columns = {row[1] for row in db.execute("PRAGMA table_info(tcm_reports)")}
        if not {"report_no", "phone", "report_time", "structured_data", "heart_rate", "blood_oxygen", "moisture_index", "report_print_url"} <= columns:
            raise UpgradeError("READER_SCHEMA_MISMATCH")
        result = {"status": "preflight_passed", "old_sha256": old_digest, "new_sha256": new_digest}
        if sample_id is not None:
            if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", sample_id) is None:
                raise UpgradeError("INVALID_SAMPLE_ID")
            namespace = {"__name__": "reviewed_readonly_probe"}
            exec(compiled, namespace)
            row = db.execute("SELECT report_no,CASE WHEN length(report_print_url)<=4096 THEN report_print_url ELSE NULL END FROM tcm_reports WHERE report_no=? LIMIT 1", (sample_id,)).fetchone()
            result["sample_source_exists"] = row is not None
            result["sample_print_id_matches_source"] = row is not None and namespace["original_link"](row[1], row[0]) is not None
    if not install:
        return result
    backup = root / "data" / ("reader-original-backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex)
    backup.mkdir(mode=0o700)
    (backup / "readonly_reports.py").write_bytes(previous)
    (backup / "readonly_reports.py").chmod(0o600)
    verified_backup(database, backup)
    if digest(target.read_bytes()) != old_digest:
        raise UpgradeError("READER_CHANGED_AFTER_BACKUP")
    result.update(backup=str(backup), restore_integrity="ok")
    try:
        atomic_module(target, reviewed, owner)
        if digest(target.read_bytes()) != new_digest:
            raise UpgradeError("INSTALLED_DIGEST_MISMATCH")
        restart_service()
        if not healthy():
            raise UpgradeError("HEALTH_FAILED")
        result.update(status="installed", health_ok=True)
    except Exception as error:
        result.update(status="failed_restored", error_code=str(error) if isinstance(error, UpgradeError) else type(error).__name__)
        result["old_module_restored"] = False
        try:
            atomic_module(target, previous, owner)
            result["old_module_restored"] = digest(target.read_bytes()) == old_digest
            restart_service()
            result["original_health_ok"] = healthy()
            if not result["old_module_restored"] or not result["original_health_ok"]:
                result["status"] = "rollback_failed"
        except Exception:
            result["status"] = "rollback_failed"
            result["original_health_ok"] = False
    return result


def main():
    os.umask(0o077)
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/opt/tcm-ingest")
    parser.add_argument("--database", default="/opt/tcm-ingest/data/tcm.db")
    parser.add_argument("--source", required=True)
    parser.add_argument("--old-sha", required=True)
    parser.add_argument("--new-sha", required=True)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--check-sample", action="store_true", help="Read the one approved sample ID from private stdin; never log it")
    args = parser.parse_args()
    try:
        result = upgrade(args.root, args.source, args.database, args.old_sha, args.new_sha,
                         install=args.install, sample_id=sys.stdin.readline().strip() if args.check_sample else None)
    except Exception as error:
        result = {"status": "failed", "error_code": str(error) if isinstance(error, UpgradeError) else type(error).__name__}
    print(json.dumps(result))
    return 0 if result["status"] in ("preflight_passed", "installed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
