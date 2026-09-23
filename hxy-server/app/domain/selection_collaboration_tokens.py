"""Browser-bound capability tokens for one service-position selection draft."""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import PositionOccupancy, Room, SelectionSession, ServicePositionQr


TOKEN_TTL = timedelta(hours=12)
BROWSER_COOKIE = "hxy_browser_token"


@dataclass(frozen=True)
class CollaborationContext:
    session: SelectionSession
    occupancy: PositionOccupancy
    room: Room
    qr: ServicePositionQr
    mode: str


def _error(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": code, "message": message})


def _browser_hash(browser_token: str) -> str:
    return hashlib.sha256(f"selection-collaboration:{browser_token}".encode()).hexdigest()


def create_collaboration_token(
    session: SelectionSession,
    occupancy: PositionOccupancy,
    room: Room,
    qr: ServicePositionQr,
    browser_token: str,
    mode: str,
) -> str:
    payload = {
        "v": 1,
        "session_id": session.id,
        "occupancy_id": occupancy.id,
        "store_id": room.store_id,
        "room_id": room.id,
        "qr_id": qr.id,
        "mode": mode,
        "browser_hash": _browser_hash(browser_token),
        "exp": int(time.time() + TOKEN_TTL.total_seconds()),
    }
    raw = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(
        hmac.new(settings.jwt_secret.encode(), f"sc1.{raw}".encode(), hashlib.sha256).digest()[:16]
    ).decode().rstrip("=")
    return f"sc1.{raw}.{signature}"


def resolve_collaboration_token(
    db: Session,
    token: str,
    browser_token: str | None,
    session_id: str,
) -> CollaborationContext:
    try:
        version, raw, signature = token.split(".")
        expected = base64.urlsafe_b64encode(
            hmac.new(settings.jwt_secret.encode(), f"{version}.{raw}".encode(), hashlib.sha256).digest()[:16]
        ).decode().rstrip("=")
        if version != "sc1" or not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        raise _error("COLLABORATION_TOKEN_INVALID", "共享选购入口无效，请重新扫码")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise _error("COLLABORATION_TOKEN_EXPIRED", "共享选购入口已过期，请重新扫码")
    if not browser_token or not hmac.compare_digest(payload.get("browser_hash", ""), _browser_hash(browser_token)):
        raise _error("COLLABORATION_TOKEN_INVALID", "共享选购入口与当前浏览器不匹配，请重新扫码")
    if payload.get("session_id") != session_id:
        raise _error("COLLABORATION_TOKEN_INVALID", "共享选购入口与当前清单不匹配，请重新扫码")

    session = db.get(SelectionSession, session_id)
    occupancy = db.get(PositionOccupancy, int(payload.get("occupancy_id", 0)))
    room = db.get(Room, int(payload.get("room_id", 0)))
    qr = db.get(ServicePositionQr, int(payload.get("qr_id", 0)))
    mode = str(payload.get("mode") or "")
    if (
        not session
        or not occupancy
        or not room
        or not qr
        or session.store_id != payload.get("store_id")
        or occupancy.store_id != session.store_id
        or occupancy.room_id != room.id
        or occupancy.selection_session_id != session.id
        or qr.store_id != session.store_id
        or qr.room_id != room.id
        or qr.status != "active"
        or mode not in {"shared_draft", "browse_only"}
    ):
        raise _error("COLLABORATION_TOKEN_INVALID", "共享选购入口已失效，请重新扫码")
    if occupancy.active_session_id != session.id or occupancy.active_room_id != room.id:
        raise _error("COLLABORATION_TOKEN_INVALID", "本次共享选购已经结束，请重新扫码")
    return CollaborationContext(session=session, occupancy=occupancy, room=room, qr=qr, mode=mode)
