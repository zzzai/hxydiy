"""Evidence-bound additive batches; the historical 19-person CLI stays unchanged."""

from datetime import UTC, datetime, timedelta, timezone
from contextlib import ExitStack
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from sqlalchemy import select, text

from app.models import AuditLog, MembershipCard, Store, User
from scripts import import_member_cards as core


SOURCE = "meiguanjia_export"
STORE_CODE = "hxy-anyang-ziwei-001"
STORE_ID = 1
SHOP_TIMEZONE = timezone(timedelta(hours=8))
ROLES = {"input", "phones", "source", "attestation", "baseline"}


class BatchError(ValueError):
    """Non-personal diagnostic suitable for an operations report."""


def require(condition, code):
    if not condition:
        raise BatchError(code)


def normalized(value):
    if isinstance(value, datetime):
        return (value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)).isoformat()
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalized(item) for item in value]
    return value


def fingerprint(value):
    return hashlib.sha256(json.dumps(normalized(value), sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def code_sha256(path):
    """Python universal newlines match Git LF; data and backups are never normalized."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def private_bytes(path, expected):
    path = Path(path)
    metadata = path.lstat()
    require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and not path.is_symlink(), "unsafe_private_file")
    require(os.name != "posix" or metadata.st_mode & 0o077 == 0, "private_file_permissions")
    require(metadata.st_size <= 8 * 1024 * 1024, "private_file_too_large")
    content = path.read_bytes()
    require(re.fullmatch(r"[a-f0-9]{64}", expected) is not None
            and hashlib.sha256(content).hexdigest() == expected, "private_file_sha256_mismatch")
    return content


def source_key(identifier):
    require(type(identifier) in {str, int} and bool(str(identifier).strip()), "invalid_source_identifier")
    return hashlib.sha256((STORE_CODE + "\0" + str(identifier)).encode("utf-8")).hexdigest()


def project_source(row):
    require(isinstance(row["phone"], str) and re.fullmatch(r"1[3-9]\d{9}", row["phone"]), "invalid_source_phone")
    milliseconds = row["opened_at_epoch_ms"]
    require(type(milliseconds) in {int, str} and re.fullmatch(r"\d+", str(milliseconds)), "invalid_source_activation")
    started = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=int(milliseconds))
    expiry = row["expires_at_date"]
    require(expiry is None or expiry == "" or isinstance(expiry, str)
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", expiry), "invalid_source_expiry")
    expires = datetime.fromisoformat(expiry).replace(tzinfo=SHOP_TIMEZONE) if expiry else None
    require(type(row["principal_yuan"]) in {str, int, float}, "invalid_source_principal")
    cents = Decimal(str(row["principal_yuan"])) * 100
    require(cents.is_finite() and cents == cents.to_integral_value() and 0 <= cents <= 2**31 - 1,
            "invalid_source_principal")
    return {"phone": row["phone"], "source_card_id": str(row["card_number"]), "card_name": row["card_name"],
            "source_card_type": "储值消费卡", "started_at": started.astimezone(SHOP_TIMEZONE).isoformat(),
            "expires_at": expires.isoformat() if expires else None, "balance_cents": int(cents),
            "allow_cross_store": False, "status": "active"}


def load_batch(manifest_path, expected_sha256):
    """Validate frozen evidence before opening any application database session."""
    path = Path(manifest_path)
    try:
        manifest = json.loads(private_bytes(path, expected_sha256))
        require(manifest["version"] == 1 and manifest["source"] == SOURCE
                and manifest["store_code"] == STORE_CODE and manifest["store_id"] == STORE_ID,
                "fixed_scope_mismatch")
        require(manifest["runner_sha256"] == code_sha256(Path(__file__))
                and manifest["core_sha256"] == code_sha256(Path(core.__file__)), "reviewed_code_mismatch")
        require(set(manifest["files"]) == ROLES, "evidence_roles_mismatch")
        contents = {}
        for role, reference in manifest["files"].items():
            name = reference["name"]
            require(isinstance(name, str) and Path(name).name == name and name not in {".", ".."}
                    and not name.startswith(".") and "/" not in name and "\\" not in name
                    and Path(name).suffix.lower() == (".txt" if role == "phones" else ".json"),
                    "unsafe_evidence_path")
            contents[role] = private_bytes(path.parent / name, reference["sha256"])
        payload = json.loads(contents["input"])
        source = json.loads(contents["source"])
        attestation = json.loads(contents["attestation"])
        baseline = json.loads(contents["baseline"])
        rows = source["rows"]
        require(str(source["source_tenant_id"]) == "1581452" and str(source["source_shop_id"]) == "1581453",
                "source_shop_mismatch")
        rows_sha = hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        require(attestation["task_id"] == manifest["batch_id"] and attestation["verified_status"] == "active"
                and attestation["scope_excludes_future_cards"] is True
                and attestation["confirmed_on"] == datetime.now(SHOP_TIMEZONE).date().isoformat()
                and attestation["scope"]["cards"] == len(rows)
                and str(attestation["scope"]["tenant_id"]) == "1581452"
                and str(attestation["scope"]["shop_id"]) == "1581453"
                and attestation["source_file_sha256"] == manifest["files"]["source"]["sha256"]
                and attestation["source_rows_sha256"] == rows_sha, "source_status_evidence_mismatch")
        require(len(rows) == source["source_total_cards"] and len(set(source["columns"])) == len(source["columns"]),
                "incomplete_source_snapshot")
        require(baseline["target_store"]["id"] == STORE_ID
                and baseline["target_store"]["store_code"] == STORE_CODE, "baseline_store_mismatch")
        old_keys = {card["source_card_key"] for card in baseline["existing_cards"] if card["source"] == SOURCE}
        records = [dict(zip(source["columns"], row, strict=True)) for row in rows]
        all_keys = [source_key(row["card_number"]) for row in records]
        new_keys = manifest["new_source_keys"]
        require(len(set(all_keys)) == len(all_keys) and len(new_keys) == len(set(new_keys))
                and set(new_keys) == set(all_keys) - old_keys and 0 < len(new_keys) <= 100,
                "new_key_scope_mismatch")
        wanted = {"source": SOURCE, "store_code": STORE_CODE,
                  "cards": [project_source(row) for row, key in zip(records, all_keys) if key in set(new_keys)]}
        require(payload == wanted, "input_differs_from_attested_source")
        phones = contents["phones"].decode("utf-8-sig").split()
        require(len(phones) == len(set(phones)) and set(phones) == {row["phone"] for row in payload["cards"]},
                "phone_allowlist_mismatch")
        require(len(new_keys) == manifest["cards"] and len(phones) == manifest["people"], "batch_count_mismatch")
        return {"manifest": manifest, "manifest_sha256": expected_sha256, "payload": payload,
                "phones": set(phones), "baseline": baseline}
    except BatchError:
        raise
    except (OSError, ValueError, TypeError, KeyError, InvalidOperation, OverflowError):
        raise BatchError("batch_evidence_invalid") from None


def snapshot(db, baseline):
    require(set(baseline["protected_users"]["columns"]) == set(User.__table__.columns.keys())
            and set(baseline["protected_cards"]["columns"]) == set(MembershipCard.__table__.columns.keys()),
            "protected_schema_changed")
    result = {}
    for model, name, identifier in [(User, "users", "user_id"), (MembershipCard, "cards", "card_id")]:
        result[name] = [{identifier: row["id"], "full_row_sha256": fingerprint(dict(row))}
                        for row in db.execute(select(model.__table__).order_by(model.id)).mappings()]
    result["sha256"] = fingerprint(result)
    return result


def database_identity(db):
    if db.get_bind().dialect.name == "postgresql":
        return dict(db.execute(text("SELECT current_database() AS database, current_schema() AS schema, "
                                    "inet_server_addr()::text AS address, inet_server_port() AS port")).mappings().one())
    return {"dialect": db.get_bind().dialect.name, "database": db.get_bind().url.database or ":memory:"}


def check_original_records(state, baseline, *, exact):
    expected = {"users": baseline["protected_users"]["rows"], "cards": baseline["protected_cards"]["global_rows"]}
    for name, identifier in [("users", "user_id"), ("cards", "card_id")]:
        actual = {row[identifier]: row["full_row_sha256"] for row in state[name]}
        require(all(actual.get(row[identifier]) == row["full_row_sha256"] for row in expected[name]),
                "protected_records_changed")
        if exact:
            require(len(actual) == len(expected[name]), "database_baseline_changed")


def load_approval(batch, approved_manifest, preflight_path, preflight_sha, recovery_path, recovery_sha):
    try:
        require(approved_manifest == batch["manifest_sha256"], "manifest_not_approved")
        preview = json.loads(private_bytes(preflight_path, preflight_sha))
        recovery = json.loads(private_bytes(recovery_path, recovery_sha))
        require(preview["version"] == recovery["version"] == 1 and preview["mode"] == "dry-run"
                and preview["applied"] is False
                and preview["new_cards"] == batch["manifest"]["cards"]
                and preview["new_users"] == batch["manifest"]["new_users"]
                and preview["manifest_sha256"] == recovery["manifest_sha256"] == approved_manifest
                and preview["runner_sha256"] == recovery["runner_sha256"] == batch["manifest"]["runner_sha256"]
                and preview["input_sha256"] == batch["manifest"]["files"]["input"]["sha256"]
                and recovery["preflight_sha256"] == preflight_sha
                and recovery["database_identity"] == preview["database_identity"], "approval_identity_mismatch")
        restore = recovery["restore"]
        require(restore["status"] == "passed" and restore["snapshot_sha256"] == preview["snapshot_sha256"]
                and restore["database"] != preview["database_identity"]["database"]
                and re.fullmatch(r"hxy_diy_(rehearsal|ops)_[A-Za-z0-9_]+", restore["database"]),
                "restore_not_bound_to_source_snapshot")
        approval = {"preflight": preview, "recovery": recovery}
        approval["content_sha256"] = fingerprint(approval)
        verify_backup(approval)
        return approval
    except BatchError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise BatchError("apply_evidence_invalid") from None


def verify_backup(approval):
    require(approval["content_sha256"] == fingerprint({key: approval[key] for key in ["preflight", "recovery"]}),
            "approval_mutated")
    backup = approval["recovery"]["backup"]
    path = Path(backup["path"])
    metadata = path.lstat()
    require(path.is_absolute() and stat.S_ISREG(metadata.st_mode) and not path.is_symlink()
            and metadata.st_nlink == 1 and metadata.st_size == backup["bytes"] > 5
            and file_sha256(path) == backup["sha256"], "verified_backup_changed")
    with path.open("rb") as stream:
        require(stream.read(5) == b"PGDMP", "invalid_backup_format")


def candidate_records(db, batch):
    records = db.scalars(select(MembershipCard).where(MembershipCard.source == SOURCE,
                        MembershipCard.source_card_key.in_(batch["manifest"]["new_source_keys"]))).all()
    phones = {source_key(row["source_card_id"]): row["phone"] for row in batch["payload"]["cards"]}
    for card in records:
        owner = db.get(User, card.user_id)
        require(card.store_id == STORE_ID and owner is not None
                and owner.phone == phones[card.source_card_key], "candidate_ownership_conflict")
    return records


def execute_batch(sessions, batch, *, apply=False, approval=None):
    require(not apply or approval is not None, "apply_approval_missing")
    if apply:
        verify_backup(approval)
    with sessions() as db:
        try:
            dialect = db.get_bind().dialect.name
            if dialect == "sqlite":
                # An actual outer transaction must exist before the legacy core's SAVEPOINT.
                db.execute(text("BEGIN IMMEDIATE" if apply else "BEGIN"))
            elif dialect == "postgresql":
                if apply:
                    lock_id = int.from_bytes(hashlib.sha256((SOURCE + STORE_CODE).encode()).digest()[:8], "big", signed=True)
                    db.execute(text("SELECT pg_advisory_xact_lock(:identifier)"), {"identifier": lock_id})
                else:
                    db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            store = db.get(Store, STORE_ID)
            require(store is not None and store.store_code == STORE_CODE, "database_store_scope_mismatch")
            state = snapshot(db, batch["baseline"])
            candidates = candidate_records(db, batch)
            receipts = db.scalars(select(AuditLog).where(
                AuditLog.action == "member_card_batch_applied", AuditLog.store_id == STORE_ID,
                AuditLog.detail["manifest_sha256"].as_string() == batch["manifest_sha256"])).all()
            require(len(receipts) <= 1, "ambiguous_batch_receipt")
            if receipts:
                receipt = receipts[0].detail
                owners = {card.user_id for card in candidates}
                original_users = {row["user_id"] for row in batch["baseline"]["protected_users"]["rows"]}
                require(receipt["runner_sha256"] == batch["manifest"]["runner_sha256"]
                        and receipt["input_sha256"] == batch["manifest"]["files"]["input"]["sha256"]
                        and receipt.get("source_sha256") == batch["manifest"]["files"]["source"]["sha256"]
                        and receipt.get("status_evidence_sha256") == batch["manifest"]["files"]["attestation"]["sha256"]
                        and receipt.get("user_ids") == sorted(owners - original_users)
                        and len(receipt["user_ids"]) == batch["manifest"]["new_users"]
                        and len(owners) == batch["manifest"]["people"]
                        and len(candidates) == batch["manifest"]["cards"]
                        and {card.id for card in candidates} == set(receipt["card_ids"]), "committed_batch_incomplete")
                check_original_records(state, batch["baseline"], exact=False)
                replay = core.import_cards(db, batch["payload"], batch["phones"], apply=False)
                require(replay["new_cards"] == replay["new_users"] == 0, "committed_batch_changed")
                return {"mode": "already-applied", "new_cards": 0, "new_users": 0,
                        "manifest_sha256": batch["manifest_sha256"], "applied": False}
            require(not candidates, "partial_or_unowned_candidate_batch")
            check_original_records(state, batch["baseline"], exact=True)
            result = core.import_cards(db, batch["payload"], batch["phones"], apply=False)
            require((result["new_cards"], result["new_users"]) == (batch["manifest"]["cards"], batch["manifest"]["new_users"]),
                    "preview_count_mismatch")
            require(snapshot(db, batch["baseline"]) == state, "preview_changed_records")
            report = {"version": 1, "mode": "dry-run", "manifest_sha256": batch["manifest_sha256"],
                    "runner_sha256": batch["manifest"]["runner_sha256"],
                    "input_sha256": batch["manifest"]["files"]["input"]["sha256"],
                    "database_identity": database_identity(db), "snapshot_sha256": state["sha256"],
                    "created_at_utc": datetime.now(UTC).isoformat(), "new_cards": result["new_cards"],
                    "new_users": result["new_users"], "applied": False}
            if not apply:
                return report
            preview = approval["preflight"]
            age = (datetime.now(UTC) - datetime.fromisoformat(preview["created_at_utc"])).total_seconds()
            require(preview["manifest_sha256"] == batch["manifest_sha256"]
                    and preview["runner_sha256"] == batch["manifest"]["runner_sha256"]
                    and preview["database_identity"] == report["database_identity"]
                    and preview["snapshot_sha256"] == state["sha256"] and -5 <= age <= 3600,
                    "preflight_stale_or_wrong_database")
            result = core.import_cards(db, batch["payload"], batch["phones"], apply=True)
            db.flush()
            after = snapshot(db, batch["baseline"])
            check_original_records(after, batch["baseline"], exact=False)
            created_users = sorted({row["user_id"] for row in after["users"]} - {row["user_id"] for row in state["users"]})
            require(len(created_users) == batch["manifest"]["new_users"]
                    and len(after["cards"]) - len(state["cards"]) == batch["manifest"]["cards"], "unexpected_insert_count")
            inserted = candidate_records(db, batch)
            require({card.id for card in inserted} == set(result["created_card_ids"])
                    and len(inserted) == batch["manifest"]["cards"], "inserted_key_scope_mismatch")
            db.add(AuditLog(actor_type="system", actor_id="member-card-batch", store_id=STORE_ID,
                            action="member_card_batch_applied", entity_type="store", entity_id=str(STORE_ID),
                            detail={"manifest_sha256": batch["manifest_sha256"],
                                    "runner_sha256": batch["manifest"]["runner_sha256"],
                                    "input_sha256": batch["manifest"]["files"]["input"]["sha256"],
                                    "card_ids": result["created_card_ids"], "user_ids": created_users,
                                    "source_sha256": batch["manifest"]["files"]["source"]["sha256"],
                                    "status_evidence_sha256": batch["manifest"]["files"]["attestation"]["sha256"]}))
            db.commit()
            return {**report, "mode": "applied", "applied": True, "created_card_ids": result["created_card_ids"],
                    "created_user_ids": created_users, "protected_old_records_unchanged": True}
        except ValueError as error:
            if isinstance(error, BatchError):
                raise
            raise BatchError("core_rejected_batch") from None
        finally:
            db.rollback()


def main():
    import argparse
    from sqlalchemy.exc import SQLAlchemyError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved-manifest-sha256")
    parser.add_argument("--preflight-file", type=Path)
    parser.add_argument("--preflight-sha256")
    parser.add_argument("--recovery-file", type=Path)
    parser.add_argument("--recovery-sha256")
    args = parser.parse_args()
    try:
        require(not args.apply or args.report is not None, "apply_report_required")
        batch = load_batch(args.manifest, args.manifest_sha256)
        approval = None
        if args.apply:
            require(all([args.approved_manifest_sha256, args.preflight_file, args.preflight_sha256,
                         args.recovery_file, args.recovery_sha256]), "apply_approval_missing")
            approval = load_approval(batch, args.approved_manifest_sha256, args.preflight_file,
                                     args.preflight_sha256, args.recovery_file, args.recovery_sha256)
        with ExitStack() as stack:
            output = None
            if args.report:
                descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                output = stack.enter_context(os.fdopen(descriptor, "wb"))
            report = execute_batch(core.SessionLocal, batch, apply=args.apply, approval=approval)
            encoded = (json.dumps(report, sort_keys=True) + "\n").encode("utf-8")
            if output:
                output.write(encoded)
            print(encoded.decode("utf-8"), end="")
    except BatchError as error:
        parser.exit(1, str(error) + "\n")
    except (SQLAlchemyError, OSError, ValueError, TypeError, KeyError):
        parser.exit(1, "operation_failed_or_commit_unknown; inspect batch audit before retry\n")


if __name__ == "__main__":
    main()
