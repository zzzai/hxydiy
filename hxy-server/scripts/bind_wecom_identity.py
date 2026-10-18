"""Preview or explicitly apply one verified WeCom store staff binding.

Run as a module: python -m scripts.bind_wecom_identity --input /private/input.json
The input and its operator-approved preview must remain outside Git.
"""

import argparse
import hashlib
import json
import re
import secrets
import stat
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.api.admin import hash_password
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import AuditLog, Staff, Store, Technician
from app.models.staff_external_identity import StaffExternalIdentity
from app.services.wecom_staff import WecomProvider, WecomProviderError, canonical_userid, local_binding


class BindingRefused(ValueError):
    pass


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _inspect(db, body, lock=False):
    if not isinstance(body, dict):
        raise BindingRefused("INVALID_INPUT")
    create = body.get("create_test")
    required = {"corp_id", "userid", "store_id"} | ({"create_test"} if create is not None else {"staff_id", "technician_id"})
    if set(body) != required or not settings.wecom_corp_id or body.get("corp_id") != settings.wecom_corp_id:
        raise BindingRefused("INVALID_INPUT")
    integer_keys = required & {"store_id", "staff_id", "technician_id"}
    if create is None and body.get("technician_id") is None:
        integer_keys -= {"technician_id"}
    if any(type(body.get(key)) is not int or body[key] <= 0 for key in integer_keys):
        raise BindingRefused("INVALID_INPUT")
    try:
        userid = canonical_userid(body["userid"])
    except WecomProviderError:
        raise BindingRefused("INVALID_INPUT") from None

    def row(query):
        return db.scalar(query.with_for_update() if lock else query)

    store = row(select(Store).where(Store.id == body["store_id"]))
    if store is None:
        raise BindingRefused("STORE_NOT_FOUND")
    if create is not None:
        if not isinstance(create, dict) or set(create) != {"username", "code", "name"}:
            raise BindingRefused("INVALID_INPUT")
        if any(not isinstance(create[key], str) or not re.fullmatch(r"wecom-test-[A-Za-z0-9_-]{1,21}", create[key]) for key in ("username", "code")):
            raise BindingRefused("INVALID_INPUT")
        if not isinstance(create["name"], str) or not 1 <= len(create["name"]) <= 32 or any(ord(c) < 32 for c in create["name"]):
            raise BindingRefused("INVALID_INPUT")
        staff = row(select(Staff).where(Staff.username == create["username"]))
        tech = row(select(Technician).where(Technician.code == create["code"]))
        if (staff is None) != (tech is None):
            raise BindingRefused("ACCOUNT_CONFLICT")
        if staff and (staff.name != create["name"] or tech.name != create["name"]):
            raise BindingRefused("ACCOUNT_CONFLICT")
    else:
        staff = row(select(Staff).where(Staff.id == body["staff_id"]))
        tech = row(select(Technician).where(Technician.id == body["technician_id"])) if body["technician_id"] is not None else None
        if staff is None or (body["technician_id"] is not None and tech is None):
            raise BindingRefused("ACCOUNT_CONFLICT")
    if staff:
        proposed = StaffExternalIdentity(provider="wecom", corp_id=body["corp_id"], userid=userid, staff_id=staff.id, technician_id=tech.id if tech else None, store_id=store.id, status="active")
        try:
            local_binding(db, proposed)
        except HTTPException:
            raise BindingRefused("ACCOUNT_CONFLICT") from None
    identity = row(select(StaffExternalIdentity).where(StaffExternalIdentity.provider == "wecom", StaffExternalIdentity.corp_id == body["corp_id"], StaffExternalIdentity.userid == userid))
    if identity and (not staff or identity.status != "active" or (identity.staff_id, identity.technician_id, identity.store_id) != (staff.id, tech.id if tech else None, store.id)):
        raise BindingRefused("IDENTITY_CONFLICT")
    if staff:
        account_match = [StaffExternalIdentity.staff_id == staff.id]
        if tech:
            account_match.append(StaffExternalIdentity.technician_id == tech.id)
        other = row(select(StaffExternalIdentity).where(StaffExternalIdentity.provider == "wecom", StaffExternalIdentity.status == "active", or_(*account_match)))
        if other and (identity is None or other.id != identity.id):
            raise BindingRefused("ACCOUNT_CONFLICT")
    if create is not None and staff and identity is None:
        raise BindingRefused("ACCOUNT_CONFLICT")
    plan = {
        "action": "unchanged" if identity else "create_test" if create is not None else "bind_existing",
        "request_sha256": _sha({**body, "userid": userid}),
        "store_id": store.id,
        "staff_id": staff.id if staff else None,
        "technician_id": tech.id if tech else None,
        "credentials_version": staff.credentials_version if staff else None,
        "technician_status": tech.status if tech else None,
    }
    plan["preview_sha256"] = _sha(plan)
    return plan, userid, staff, tech


def prepare_binding(db, body):
    return _inspect(db, body)[0]


def apply_binding(db, body, expected):
    plan, userid, staff, tech = _inspect(db, body, lock=True)
    if plan["action"] == "unchanged":
        return plan
    if expected != plan["preview_sha256"]:
        raise BindingRefused("PREVIEW_CHANGED")
    if plan["action"] == "create_test":
        create = body["create_test"]
        tech = Technician(store_id=body["store_id"], code=create["code"], name=create["name"], status="available")
        db.add(tech)
        db.flush()
        staff = Staff(username=create["username"], name=create["name"], password_hash=hash_password(secrets.token_urlsafe(40)), role="technician", status="active", store_id=body["store_id"], technician_id=tech.id)
        db.add(staff)
        db.flush()
    identity = StaffExternalIdentity(provider="wecom", corp_id=body["corp_id"], userid=userid, staff_id=staff.id, technician_id=tech.id if tech else None, store_id=body["store_id"], status="active")
    db.add(identity)
    db.flush()
    db.add(AuditLog(actor_type="system", actor_id="wecom-binding-cli", store_id=body["store_id"], action="wecom_identity.bind", entity_type="staff_external_identity", entity_id=str(identity.id), detail={"request_sha256": plan["request_sha256"], "staff_id": staff.id, "technician_id": tech.id if tech else None, "created_test_account": plan["action"] == "create_test"}))
    return {"action": "created", "staff_id": staff.id, "technician_id": tech.id if tech else None, "identity_id": identity.id}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expect-preview-sha256")
    args = parser.parse_args()
    try:
        if args.input.is_symlink() or not args.input.is_file() or stat.S_IMODE(args.input.stat().st_mode) & 0o077 or args.input.stat().st_size > 4096:
            raise BindingRefused("PRIVATE_INPUT_REQUIRED")
        body = json.loads(args.input.read_text())
        with SessionLocal.begin() as db:
            preview = prepare_binding(db, body)
            WecomProvider().verify_member(canonical_userid(body["userid"]))
            result = apply_binding(db, body, args.expect_preview_sha256) if args.apply else preview
        print(json.dumps(result, sort_keys=True))
        return 0
    except (BindingRefused, WecomProviderError, SQLAlchemyError, ValueError, OSError):
        # Do not print upstream errors, SQL parameters or private input.
        print(json.dumps({"error": "BINDING_REFUSED", "changed": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
