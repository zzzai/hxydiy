"""Signed store-entry context for standalone visit feedback."""

import base64
import hashlib
import hmac
import json
import time
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Room, ServicePositionQr


TOKEN_TTL = timedelta(hours=12)


def _error(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": code, "message": message})


def _browser_hash(browser_token: str) -> str:
    return hashlib.sha256(f"browser:{browser_token}".encode()).hexdigest()


def create_visit_feedback_token(room: Room, source: str, browser_token: str, qr_id: int | None = None) -> str:
    payload = {
        "v": 1,
        "store_id": room.store_id,
        "room_id": room.id,
        "qr_id": qr_id,
        "source": source,
        "browser_hash": _browser_hash(browser_token),
        "exp": int(time.time() + TOKEN_TTL.total_seconds()),
    }
    raw = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(
        hmac.new(settings.jwt_secret.encode(), f"vf1.{raw}".encode(), hashlib.sha256).digest()[:16]
    ).decode().rstrip("=")
    return f"vf1.{raw}.{signature}"


def resolve_visit_feedback_token(
    db: Session,
    token: str,
    browser_token: str | None,
) -> tuple[Room, ServicePositionQr | None, str]:
    try:
        version, raw, signature = token.split(".")
        expected = base64.urlsafe_b64encode(
            hmac.new(settings.jwt_secret.encode(), f"{version}.{raw}".encode(), hashlib.sha256).digest()[:16]
        ).decode().rstrip("=")
        if version != "vf1" or not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        raise _error("VISIT_FEEDBACK_TOKEN_INVALID", "到店反馈入口无效，请重新扫码")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise _error("VISIT_FEEDBACK_TOKEN_EXPIRED", "到店反馈入口已过期，请重新扫码")
    if not browser_token or not hmac.compare_digest(payload.get("browser_hash", ""), _browser_hash(browser_token)):
        raise _error("VISIT_FEEDBACK_TOKEN_INVALID", "到店反馈入口与当前浏览器不匹配，请重新扫码")
    room = db.get(Room, int(payload.get("room_id", 0)))
    if (
        not room
        or room.store_id != payload.get("store_id")
        or room.operational_status != "active"
        or room.is_space_container
        or not room.is_service_position
    ):
        raise _error("VISIT_FEEDBACK_TOKEN_INVALID", "到店反馈入口已失效，请重新扫码")
    qr_id = payload.get("qr_id")
    if qr_id is None:
        if settings.environment == "production":
            raise _error("VISIT_FEEDBACK_TOKEN_INVALID", "到店反馈入口已失效，请重新扫码")
        qr = db.scalar(select(ServicePositionQr).where(
            ServicePositionQr.room_id == room.id,
            ServicePositionQr.store_id == room.store_id,
            ServicePositionQr.status == "active",
        ).order_by(ServicePositionQr.id.desc()))
    else:
        if not isinstance(qr_id, int) or isinstance(qr_id, bool):
            raise _error("VISIT_FEEDBACK_TOKEN_INVALID", "到店反馈入口已失效，请重新扫码")
        qr = db.get(ServicePositionQr, qr_id)
        if not qr or qr.room_id != room.id or qr.store_id != room.store_id or qr.source != payload.get("source") or qr.status != "active":
            raise _error("VISIT_FEEDBACK_TOKEN_INVALID", "到店反馈入口已失效，请重新扫码")
    return room, qr, str(payload.get("source") or "store_qr")
