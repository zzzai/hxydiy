"""Preview/publish/retire an immutable course package; never assign or erase learning records."""
import argparse
import hashlib
import json
from pathlib import Path
import uuid

from sqlalchemy import select, text

from app.api.staff_learning import content_hash
from app.db.session import SessionLocal
from app.domain.learning_content import load_package
from app.models import AuditLog, Store
from app.models.staff_learning import LearningCourseVersion

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "content/staff-learning/production-manifest.json"


def reconcile_courses(db, manifest_path=DEFAULT_MANIFEST, *, retire=False, apply=False, expected_hash=None):
    manifest, courses, approved = load_package(manifest_path)
    if not approved:
        raise ValueError("learning_package_not_approved")
    store = db.get(Store, 1)
    if store is None or store.store_code != "hxy-anyang-ziwei-001":
        raise ValueError("learning_store_identity_mismatch")
    if apply and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(18362143)"))
    changes = []
    for content in courses:
        query = select(LearningCourseVersion).where(
            LearningCourseVersion.code == content["id"], LearningCourseVersion.version == content["version"])
        current = db.scalar(query.with_for_update() if apply else query)
        digest = content_hash(content)
        if current and (current.content_sha256 != digest or content_hash(current.content) != digest
                        or current.approval_reference != manifest["production_approval_reference"]):
            raise ValueError("immutable_course_version_conflict")
        if retire and current is None:
            raise ValueError("cannot_retire_missing_course")
        if current and current.status == "retired" and not retire:
            raise ValueError("retired_version_cannot_be_republished")
        target = "retired" if retire else "published"
        if current is None or current.status != target:
            changes.append({"code": content["id"], "version": content["version"], "content_sha256": digest,
                            "before": current.status if current else None, "after": target})
    report = {"manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              "content_sha256": manifest["content_sha256"], "action": "retire" if retire else "publish",
              "approval_reference": manifest["production_approval_reference"], "changes": changes}
    report["preview_hash"] = content_hash(report)
    if apply:
        if expected_hash != report["preview_hash"]:
            raise ValueError("learning_preview_changed")
        by_code = {c["id"]: c for c in courses}
        for change in changes:
            content = by_code[change["code"]]
            current = db.scalar(select(LearningCourseVersion).where(
                LearningCourseVersion.code == change["code"], LearningCourseVersion.version == change["version"]))
            if current:
                current.status = change["after"]
            else:
                db.add(LearningCourseVersion(id=str(uuid.uuid4()), code=content["id"], version=content["version"],
                    content=content, content_sha256=change["content_sha256"], status="published",
                    approval_reference=manifest["production_approval_reference"]))
        if changes:
            db.add(AuditLog(actor_type="system", actor_id="LEARNING-20261102", store_id=1,
                action="learning_course_package_" + report["action"], entity_type="learning_course_package",
                entity_id=report["content_sha256"], detail=report))
        db.flush()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--retire", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-hash")
    parser.add_argument("--backup-reference", type=Path)
    parser.add_argument("--backup-sha256")
    args = parser.parse_args()
    if args.apply:
        path = args.backup_reference
        if not args.expected_hash or not path or path.is_symlink() or not path.is_file():
            parser.error("apply requires exact preview and actual database backup")
        with path.open("rb") as stream:
            if stream.read(5) != b"PGDMP":
                parser.error("PostgreSQL custom-format backup required")
            stream.seek(0)
            if hashlib.file_digest(stream, "sha256").hexdigest() != args.backup_sha256:
                parser.error("backup digest mismatch")
    with SessionLocal() as db:
        try:
            if db.bind.dialect.name == "postgresql":
                if not args.apply:
                    db.execute(text("SET TRANSACTION READ ONLY"))
                db.execute(text("SET LOCAL lock_timeout = '5s'"))
                db.execute(text("SET LOCAL statement_timeout = '30s'"))
            result = reconcile_courses(db, args.manifest, retire=args.retire, apply=args.apply, expected_hash=args.expected_hash)
            db.commit() if args.apply else db.rollback()
        except Exception:
            db.rollback()
            raise
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
