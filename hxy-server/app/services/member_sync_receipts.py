"""Load allowlisted, redacted member-sync receipts.

The loader never scans arbitrary directories and never reads raw member input.
Only files named by ``index.json`` are opened; the index SHA is checked against
the bytes before JSON parsing. A digest proves integrity, not source truth.

Batch identity is scoped by ``(store_id, batch_id)``. A conflict invalidates
that batch for the affected store instead of silently keeping the first file.
Addressing/verification/submission events are calculated separately so a
``no_new`` verification can never overwrite the last successful submission.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.config import settings

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "content" / "member_sync_receipts"
REQUIRED_FIELDS = ("receipt_version", "receipt_id", "batch_id", "status", "store_id")
STATUSES = {"success", "no_new", "blocked", "failed", "invalid"}
NOTE_REQUIRED = ("note_version", "note_id", "batch_id", "store_id", "current_status")
NOTE_STATUSES = {"authorized_pending_resume", "paused_by_user", "waiting_login", "waiting_authorization", "protection_failed", "evidence_conflict", "unknown"}


def _dir() -> Path:
    configured = settings.member_sync_receipt_dir.strip()
    return Path(configured) if configured else DEFAULT_DIR


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Never guess a timezone for a naive source timestamp.
    return parsed if parsed.tzinfo is not None else None


def _canonical(value: dict) -> str:
    return json.dumps({key: item for key, item in value.items() if key != "_file"}, sort_keys=True, separators=(",", ":"))


def _event_time(item: dict, kind: str) -> datetime | None:
    if kind == "submit":
        fields = ("successful_submit_at",)
    elif kind == "verify":
        fields = ("source_verified_at", "successful_submit_at")
    else:
        # A later source check must not outrank the attempt's own timestamp.
        fields = ("attempt_at", "source_verified_at", "successful_submit_at")
    for field in fields:
        parsed = _parse_time(item.get(field))
        if parsed is not None:
            return parsed
    return None


def _sort_time(item: dict, kind: str) -> tuple[datetime, str]:
    return (_event_time(item, kind) or datetime.min.replace(tzinfo=UTC), str(item.get("receipt_id") or item.get("batch_id") or ""))


def _validated_entry(root: Path, entry: Any, errors: list[dict]) -> tuple[dict | None, str | None]:
    if not isinstance(entry, dict) or not isinstance(entry.get("file"), str) or not isinstance(entry.get("sha256"), str):
        errors.append({"code": "RECEIPT_ENTRY_INVALID", "store_id": None})
        return None, None
    name = entry["file"]
    if Path(name).name != name or name.startswith(".") or "/" in name or "\\" in name:
        errors.append({"code": "RECEIPT_PATH_REJECTED", "store_id": None})
        return None, None
    path = root / name
    if not path.is_file():
        errors.append({"code": "RECEIPT_MISSING", "store_id": None})
        return None, None
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        errors.append({"code": "RECEIPT_SHA_MISMATCH", "store_id": None})
        return None, None
    try:
        data = json.loads(raw)
    except Exception:
        errors.append({"code": "RECEIPT_JSON_INVALID", "store_id": None})
        return None, None
    if not isinstance(data, dict):
        errors.append({"code": "RECEIPT_SHAPE_INVALID", "store_id": None})
        return None, None
    missing = [field for field in REQUIRED_FIELDS if field not in data]
    if missing:
        errors.append({"code": "RECEIPT_FIELDS_MISSING", "store_id": data.get("store_id") if isinstance(data.get("store_id"), int) else None, "missing": missing})
        return None, None
    if data.get("receipt_version") != 1 or data.get("status") not in STATUSES or not isinstance(data.get("store_id"), int):
        errors.append({"code": "RECEIPT_SCHEMA_INVALID", "store_id": data.get("store_id") if isinstance(data.get("store_id"), int) else None})
        return None, None
    data["_file"] = name
    return data, name


def _load_notes(root: Path, entries: Any, errors: list[dict]) -> tuple[list[dict], list[dict]]:
    notes: list[dict] = []
    conflicts: list[dict] = []
    if entries is None:
        return notes, conflicts
    if not isinstance(entries, list):
        errors.append({"code": "RECEIPT_NOTES_INVALID", "store_id": None})
        return notes, conflicts
    seen: dict[tuple[int, str], dict] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str) or not isinstance(entry.get("sha256"), str):
            errors.append({"code": "RECEIPT_NOTE_ENTRY_INVALID", "store_id": None})
            continue
        name = entry["file"]
        if Path(name).name != name or name.startswith(".") or "/" in name or "\\" in name:
            errors.append({"code": "RECEIPT_NOTE_PATH_REJECTED", "store_id": None})
            continue
        path = root / name
        if not path.is_file():
            errors.append({"code": "RECEIPT_NOTE_MISSING", "store_id": None})
            continue
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            errors.append({"code": "RECEIPT_NOTE_SHA_MISMATCH", "store_id": None})
            continue
        try:
            data = json.loads(raw)
        except Exception:
            errors.append({"code": "RECEIPT_NOTE_JSON_INVALID", "store_id": None})
            continue
        if not isinstance(data, dict):
            errors.append({"code": "RECEIPT_NOTE_SHAPE_INVALID", "store_id": None})
            continue
        missing = [field for field in NOTE_REQUIRED if field not in data]
        if missing:
            errors.append({"code": "RECEIPT_NOTE_FIELDS_MISSING", "store_id": data.get("store_id") if isinstance(data.get("store_id"), int) else None, "missing": missing})
            continue
        if data.get("note_version") != 1 or data.get("current_status") not in NOTE_STATUSES or not isinstance(data.get("store_id"), int):
            errors.append({"code": "RECEIPT_NOTE_SCHEMA_INVALID", "store_id": data.get("store_id") if isinstance(data.get("store_id"), int) else None})
            continue
        key = (int(data["store_id"]), str(data["batch_id"]))
        if key in seen:
            if _canonical(seen[key]) == _canonical(data):
                continue
            prior = seen.pop(key)
            if prior in notes:
                notes.remove(prior)
            conflicts.append({"code": "RECEIPT_NOTE_CONFLICT", "store_id": key[0], "batch_id": key[1]})
            continue
        if any(item.get("store_id") == key[0] and item.get("batch_id") == key[1] for item in conflicts):
            continue
        data["_file"] = name
        seen[key] = data
        notes.append(data)
    return notes, conflicts


def _store_view(
    store_id: int,
    receipts: list[dict],
    conflicts: list[dict],
    errors: list[dict],
    notes: list[dict],
) -> dict:
    store_receipts = [item for item in receipts if item.get("store_id") == store_id]
    store_conflicts = [item for item in conflicts if item.get("store_id") == store_id]
    store_errors = [item for item in errors if item.get("store_id") in (None, store_id)]
    store_notes = [item for item in notes if item.get("store_id") == store_id]

    submissions = [item for item in store_receipts if item.get("status") == "success"]
    verifications = [item for item in store_receipts if item.get("status") in {"success", "no_new"} and (
        item.get("verification_complete") is not False
        and _event_time(item, "verify") is not None
    )]
    attempts = [item for item in store_receipts if item.get("status") in {"success", "no_new", "blocked", "failed"}]
    last_success = max(submissions, key=lambda item: _sort_time(item, "submit")) if submissions else None
    last_verification = max(verifications, key=lambda item: _sort_time(item, "verify")) if verifications else None
    latest_attempt = max(attempts, key=lambda item: _sort_time(item, "attempt")) if attempts else None

    notes_by_key = {(item["store_id"], item["batch_id"]): item for item in store_notes}
    for item in (last_success, last_verification, latest_attempt):
        if item is not None:
            note = notes_by_key.get((store_id, item.get("batch_id")))
            if note:
                expected = note.get("source_keyset_sha256")
                if expected and expected != item.get("source_keyset_sha256"):
                    note = None
            if note:
                item["current_processing"] = {
                    "note_id": note.get("note_id"),
                    "current_status": note.get("current_status"),
                    "current_status_label": note.get("current_status_label"),
                    "current_status_detail": note.get("current_status_detail"),
                    "authorization_status": note.get("authorization_status"),
                    "authorization_scope": note.get("authorization_scope"),
                    "authorization_recorded_at": note.get("authorization_recorded_at"),
                    "paused_at": note.get("paused_at"),
                    "time_status": note.get("time_status") or ("未记录" if not note.get("authorization_recorded_at") else "已记录"),
                    "not_import_authorization": True,
                }

    has_conflict = bool(store_conflicts)
    if store_conflicts:
        current_state = "conflict"
        reason = "receipt_conflict"
    elif latest_attempt is not None:
        current_state = "blocked" if latest_attempt.get("status") in {"blocked", "failed"} else "verified"
        reason = "ok"
    elif last_success is not None:
        current_state = "verified"
        reason = "ok"
    elif last_verification is not None:
        current_state = "verified_no_new"
        reason = "ok"
    else:
        current_state = "no_store_receipt"
        reason = "no_store_receipt"

    # Conflict details are sanitized for the API: no filenames or evidence bodies.
    sanitized_conflicts = [{"code": item.get("code"), "batch_id": item.get("batch_id"), "store_id": item.get("store_id")} for item in store_conflicts]
    sanitized_errors = [{"code": item.get("code"), **({"missing": item.get("missing")} if item.get("missing") else {})} for item in store_errors]
    return {
        "available": bool(store_receipts),
        "has_receipt": bool(store_receipts),
        "has_conflict": has_conflict,
        "current_state": current_state,
        "reason": reason,
        "last_success": last_success,
        "last_verification": last_verification,
        "latest_attempt": latest_attempt,
        "receipts": store_receipts,
        "errors": sanitized_errors,
        "conflicts": sanitized_conflicts,
        "trust_note": "回执仅来自 allowlist 索引；SHA 只证明内容完整性，不单独证明来源真实性；冲突批次不作为可信结果。",
    }


def load_member_sync_receipts(directory: Path | None = None, store_id: int | None = None) -> dict:
    root = directory or _dir()
    errors: list[dict] = []
    conflicts: list[dict] = []
    receipts: list[dict] = []
    index_path = root / "index.json"
    if not index_path.is_file():
        return {"available": False, "reason": "receipt_index_missing", "receipts": [], "errors": errors, "conflicts": conflicts}
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {"available": False, "reason": "receipt_index_invalid", "receipts": [], "errors": errors, "conflicts": conflicts}
    if index.get("schema_version") != 1 or not isinstance(index.get("receipts"), list):
        return {"available": False, "reason": "receipt_index_invalid", "receipts": [], "errors": errors, "conflicts": conflicts}

    by_key: dict[tuple[int, str], dict] = {}
    for entry in index["receipts"]:
        data, _ = _validated_entry(root, entry, errors)
        if data is None:
            continue
        key = (int(data["store_id"]), str(data["batch_id"]))
        if key in by_key:
            if _canonical(by_key[key]) == _canonical(data):
                continue
            prior = by_key.pop(key)
            if prior in receipts:
                receipts.remove(prior)
            conflicts.append({"code": "RECEIPT_BATCH_CONFLICT", "store_id": key[0], "batch_id": key[1], "files": [prior.get("_file"), data.get("_file")]})
            continue
        if any(item.get("store_id") == key[0] and item.get("batch_id") == key[1] for item in conflicts):
            continue
        by_key[key] = data
        receipts.append(data)

    notes, note_conflicts = _load_notes(root, index.get("status_notes"), errors)
    conflicts.extend(note_conflicts)
    if store_id is not None:
        return _store_view(store_id, receipts, conflicts, errors, notes)

    # No store requested: deterministic aggregate, not used by the scoped route.
    aggregate_conflicts = [{key: value for key, value in item.items() if key != "files"} for item in conflicts]
    return {
        "available": bool(receipts or notes),
        "reason": "ok" if (receipts or notes) else "receipt_unavailable",
        "last_success": None,
        "last_verification": None,
        "latest_attempt": None,
        "receipts": receipts,
        "errors": [{key: value for key, value in item.items() if key != "file"} for item in errors],
        "conflicts": aggregate_conflicts,
        "trust_note": "回执仅来自 allowlist 索引；SHA 只证明内容完整性，不单独证明来源真实性；冲突批次不作为可信结果。",
    }
