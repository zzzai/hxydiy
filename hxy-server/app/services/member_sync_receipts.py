"""Load allowlisted, redacted member-sync receipts.

The loader never scans arbitrary directories and never reads raw member input.
Only files named by ``index.json`` are opened; the index SHA is checked against
the bytes before JSON parsing. A digest proves integrity, not source truth.
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


def _dir() -> Path:
    configured = settings.member_sync_receipt_dir.strip()
    return Path(configured) if configured else DEFAULT_DIR


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _same_content(left: dict, right: dict) -> bool:
    left = {key: value for key, value in left.items() if key != "_file"}
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(right, sort_keys=True, separators=(",", ":"))


def load_member_sync_receipts(directory: Path | None = None) -> dict:
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

    seen: dict[str, dict] = {}
    for entry in index["receipts"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str) or not isinstance(entry.get("sha256"), str):
            errors.append({"code": "RECEIPT_ENTRY_INVALID", "file": entry.get("file") if isinstance(entry, dict) else None})
            continue
        name = entry["file"]
        if Path(name).name != name or name.startswith(".") or "/" in name or "\\" in name:
            errors.append({"code": "RECEIPT_PATH_REJECTED", "file": name})
            continue
        path = root / name
        if not path.is_file():
            errors.append({"code": "RECEIPT_MISSING", "file": name})
            continue
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            errors.append({"code": "RECEIPT_SHA_MISMATCH", "file": name})
            continue
        try:
            data = json.loads(raw)
        except Exception:
            errors.append({"code": "RECEIPT_JSON_INVALID", "file": name})
            continue
        missing = [field for field in REQUIRED_FIELDS if field not in data]
        if missing:
            errors.append({"code": "RECEIPT_FIELDS_MISSING", "file": name, "missing": missing})
            continue
        if data.get("receipt_version") != 1 or data.get("status") not in STATUSES:
            errors.append({"code": "RECEIPT_SCHEMA_INVALID", "file": name})
            continue
        batch_id = str(data["batch_id"])
        if batch_id in seen:
            if _same_content(seen[batch_id], data):
                continue
            conflicts.append({"code": "RECEIPT_BATCH_CONFLICT", "batch_id": batch_id, "files": [seen[batch_id].get("_file"), name]})
            continue
        data["_file"] = name
        seen[batch_id] = data
        receipts.append(data)

    def moment(item: dict) -> datetime:
        return _parse_time(item.get("successful_submit_at") or item.get("source_verified_at") or item.get("attempt_at")) or datetime.min.replace(tzinfo=UTC)

    successes = [item for item in receipts if item.get("status") in {"success", "no_new"}]
    attempts = [item for item in receipts if item.get("status") in {"success", "no_new", "blocked", "failed"}]
    last_success = max(successes, key=moment) if successes else None
    latest_attempt = max(attempts, key=moment) if attempts else None
    return {
        "available": bool(last_success or latest_attempt),
        "reason": "ok" if (last_success or latest_attempt) else "receipt_unavailable",
        "last_success": last_success,
        "latest_attempt": latest_attempt,
        "receipts": receipts,
        "errors": errors,
        "conflicts": conflicts,
        "trust_note": "回执仅来自 allowlist 索引；SHA 只证明内容完整性，不单独证明来源真实性。",
    }
