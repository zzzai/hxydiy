"""Scoped export import. Run as a module; never log raw records or credentials."""

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.models import AuditLog, MembershipCard, Store, User


def aware_time(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(UTC)
    except (TypeError, ValueError):
        raise ValueError("record requires an original timezone-aware date") from None


def import_cards(db, payload, allowed_phones, *, apply=False):
    source = payload.get("source")
    if not isinstance(source, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", source):
        raise ValueError("invalid source")
    store = db.scalar(select(Store).where(Store.store_code == payload.get("store_code")))
    if store is None:
        raise ValueError("unknown target store")
    rows = payload.get("cards")
    if not isinstance(rows, list) or not rows or len(rows) > 100:
        raise ValueError("invalid card batch")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("invalid card record")
    if {row.get("phone") for row in rows} != allowed_phones:
        raise ValueError("batch must match the exact authorized phone set")
    plans, seen = [], set()
    for row in rows:
        phone = row.get("phone")
        if not isinstance(phone, str) or not re.fullmatch(r"1[3-9]\d{9}", phone):
            raise ValueError("invalid phone")
        if row.get("allow_cross_store") is not False:
            raise ValueError("store-only scope must be explicit")
        status = row.get("status")
        if status not in {"active", "disabled"}:
            raise ValueError("source card status must be explicitly verified")
        if row.get("source_card_type") != "储值消费卡":
            raise ValueError("unconfirmed source card classification")
        name = row.get("card_name")
        if name == "荷小悦年度权益会员卡":
            kind = "annual"
        elif name == "荷小悦会员卡":
            kind = "stored"
        else:
            raise ValueError("unknown source card name")
        balance = row.get("balance_cents")
        if type(balance) is not int or not 0 <= balance <= 2**31 - 1:
            raise ValueError("balance must be nonnegative integer cents")
        start = aware_time(row.get("started_at"))
        expiry = aware_time(row["expires_at"]) if row.get("expires_at") else None
        if kind == "annual" and expiry is None:
            raise ValueError("annual card requires original expiry")
        if kind == "annual":
            original_start = datetime.fromisoformat(row["started_at"])
            try:
                anniversary = original_start.replace(year=original_start.year + 1)
            except ValueError:
                anniversary = original_start.replace(year=original_start.year + 1, day=28)
            if expiry > anniversary:
                raise ValueError("annual entitlement cannot exceed one original year")
        if expiry is not None and expiry <= start:
            raise ValueError("expiry must follow activation")
        card_id = row.get("source_card_id")
        if not isinstance(card_id, str) or not card_id.strip():
            raise ValueError("original source card identifier required")
        key = hashlib.sha256((store.store_code + "\0" + card_id).encode()).hexdigest()
        if key in seen:
            raise ValueError("duplicate source card in batch")
        seen.add(key)
        existing = db.scalar(select(MembershipCard).where(
            MembershipCard.source == source, MembershipCard.source_card_key == key,
        ).with_for_update())
        user = db.scalar(select(User).where(User.phone == phone).with_for_update())
        if existing:
            if user is None or existing.user_id != user.id or existing.store_id != store.id:
                raise ValueError("source card ownership conflict")
            old_start = existing.started_at.replace(tzinfo=UTC) if existing.started_at.tzinfo is None else existing.started_at.astimezone(UTC)
            old_expiry = existing.expires_at
            if old_expiry is not None:
                old_expiry = old_expiry.replace(tzinfo=UTC) if old_expiry.tzinfo is None else old_expiry.astimezone(UTC)
            original = (existing.card_type, old_start, old_expiry,
                        existing.balance_cents, existing.status)
            if original != (kind, start, expiry, balance, status):
                raise ValueError("snapshot changed; manual update policy required")
        plans.append((phone, key, kind, start, expiry, balance, status, user, existing))
    new_cards = sum(existing is None for *_, existing in plans)
    new_users = len({phone for phone, *_, user, existing in plans if user is None})
    report = {"store_id": store.id, "people": len(allowed_phones), "cards": len(plans),
              "new_users": new_users, "new_cards": new_cards, "applied": apply,
              "balance_realtime": False, "created_card_ids": []}
    if not apply:
        return report
    now = datetime.now(UTC)
    with db.begin_nested():
        for phone, key, kind, start, expiry, balance, status, user, existing in plans:
            if existing:
                continue
            user = db.scalar(select(User).where(User.phone == phone))
            if user is None:
                user = User(openid="import_" + hashlib.sha256(phone.encode()).hexdigest()[:56], phone=phone)
                db.add(user); db.flush()
            card = MembershipCard(user_id=user.id, store_id=store.id, source=source,
                                  source_card_key=key, card_type=kind, started_at=start,
                                  expires_at=expiry, balance_cents=balance, status=status, observed_at=now)
            db.add(card); db.flush()
            report["created_card_ids"].append(card.id)
        if new_cards:
            db.add(AuditLog(actor_type="system", actor_id="member-card-import", store_id=store.id,
                            action="member_cards_imported", entity_type="store", entity_id=str(store.id),
                            detail={"source": source, "card_ids": report["created_card_ids"], "balance_realtime": False,
                                    "classification_basis": "user_confirmed_card_classes_20260928"}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--phones-file", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-file", type=Path)
    parser.add_argument("--backup-sha256")
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
        phones = set(args.phones_file.read_text(encoding="utf-8-sig").split())
        if len(phones) != 19:
            raise ValueError("production batch requires exactly 19 authorized people")
        if args.apply:
            if not args.backup_file or not args.backup_sha256 or not args.backup_file.is_file():
                raise ValueError("verified database backup file and SHA256 required before apply")
            if args.backup_file.stat().st_size == 0:
                raise ValueError("empty backup rejected")
            with args.backup_file.open("rb") as backup:
                digest = hashlib.file_digest(backup, "sha256").hexdigest()
            if digest != args.backup_sha256:
                raise ValueError("backup SHA256 mismatch")
        with SessionLocal.begin() as db:
            report = import_cards(db, payload, phones, apply=args.apply)
        print(json.dumps(report, ensure_ascii=False))
    except ValueError as exc:
        parser.exit(1, str(exc) + "\n")
    except (SQLAlchemyError, OSError, TypeError, KeyError):
        parser.exit(1, "import rejected; no sensitive diagnostics displayed\n")


if __name__ == "__main__":
    main()
