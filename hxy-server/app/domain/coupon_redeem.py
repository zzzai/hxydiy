"""Short signed coupon codes.

Coupon links and redemption QRs carry compact HMAC-signed codes instead of
long JWTs, so the printed/shared QR stays simple. The legacy JWT format is
still accepted for links generated before this change.
"""

from datetime import UTC, datetime, timedelta
import base64
import hashlib
import hmac

from jose import JWTError, jwt
from fastapi import HTTPException

from app.core.config import settings

REDEEM_SCOPE = "coupon_redeem"
REDEEM_TTL_SECONDS = 300
CLAIM_SCOPE = "coupon_claim"
CLAIM_TTL_DAYS = 60
GUEST_SCOPE = "guest_coupon"
GUEST_TTL_DAYS = 60


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _sign(payload: str) -> str:
    digest = hmac.new(settings.jwt_secret.encode(), payload.encode(), hashlib.sha256).digest()
    return _b64(digest[:12])


def _compact(prefix: str, first: int, second: int, expires_at: datetime) -> str:
    payload = f"{prefix}.{int(first)}.{int(second)}.{int(expires_at.timestamp())}"
    return f"{payload}.{_sign(payload)}"


def _parse_compact(value: str, prefix: str, *, error_code: str, message: str) -> tuple[int, int]:
    parts = value.split(".")
    if len(parts) != 5 or parts[0] != prefix:
        raise HTTPException(status_code=400, detail={"code": error_code, "message": message})
    payload = ".".join(parts[:4])
    if not hmac.compare_digest(parts[4], _sign(payload)):
        raise HTTPException(status_code=400, detail={"code": error_code, "message": message})
    try:
        first = int(parts[1])
        second = int(parts[2])
        expires = int(parts[3])
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": error_code, "message": message}) from None
    if expires <= int(datetime.now(UTC).timestamp()):
        raise HTTPException(status_code=400, detail={"code": error_code, "message": message})
    return first, second


def create_redeem_token(coupon_id: int, user_id: int) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(seconds=REDEEM_TTL_SECONDS)
    return _compact("r", coupon_id, user_id, expires_at), expires_at


def decode_redeem_token(token: str) -> dict:
    if token.startswith("r."):
        coupon_id, user_id = _parse_compact(
            token, "r", error_code="COUPON_CODE_INVALID", message="核销码无效或已过期",
        )
        return {"coupon_id": coupon_id, "user_id": user_id}
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=400, detail={"code": "COUPON_CODE_INVALID", "message": "核销码无效或已过期"}) from None
    if payload.get("scope") != REDEEM_SCOPE:
        raise HTTPException(status_code=400, detail={"code": "COUPON_CODE_INVALID", "message": "核销码无效或已过期"})
    coupon_id = payload.get("coupon_id")
    user_id = payload.get("user_id")
    if type(coupon_id) is not int or type(user_id) is not int:
        raise HTTPException(status_code=400, detail={"code": "COUPON_CODE_INVALID", "message": "核销码无效或已过期"})
    return {"coupon_id": coupon_id, "user_id": user_id}


def create_claim_token(store_id: int, template_id: int) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(days=CLAIM_TTL_DAYS)
    return _compact("c", store_id, template_id, expires_at), expires_at


def create_poster_token(poster_id: int, store_id: int, expires_at: datetime) -> str:
    return _compact("p", poster_id, store_id, expires_at)


def decode_claim_token(token: str) -> dict:
    if token.startswith("p."):
        poster_id, store_id = _parse_compact(
            token, "p", error_code="COUPON_LINK_INVALID", message="领券链接无效或已过期",
        )
        return {"poster_id": poster_id, "store_id": store_id}
    if token.startswith("c."):
        store_id, template_id = _parse_compact(
            token, "c", error_code="COUPON_LINK_INVALID", message="领券链接无效或已过期",
        )
        return {"store_id": store_id, "template_id": template_id}
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=400, detail={"code": "COUPON_LINK_INVALID", "message": "领券链接无效或已过期"}) from None
    if payload.get("scope") != CLAIM_SCOPE:
        raise HTTPException(status_code=400, detail={"code": "COUPON_LINK_INVALID", "message": "领券链接无效或已过期"})
    store_id = payload.get("store_id")
    template_id = payload.get("template_id")
    if type(store_id) is not int or type(template_id) is not int:
        raise HTTPException(status_code=400, detail={"code": "COUPON_LINK_INVALID", "message": "领券链接无效或已过期"})
    return {"store_id": store_id, "template_id": template_id}


def create_guest_token(coupon_id: int, user_id: int) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(days=GUEST_TTL_DAYS)
    return _compact("g", coupon_id, user_id, expires_at), expires_at


def decode_guest_token(token: str) -> dict:
    coupon_id, user_id = _parse_compact(
        token, "g", error_code="COUPON_GUEST_INVALID", message="领券记录无效或已过期",
    )
    return {"coupon_id": coupon_id, "user_id": user_id}
