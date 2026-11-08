"""Signed, short-lived coupon redemption tokens.

The token is a bearer credential for one coupon and one customer. It contains
no customer identity beyond the internal IDs, expires quickly, and is only
accepted by the manager redemption endpoints.
"""

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from fastapi import HTTPException

from app.core.config import settings

REDEEM_SCOPE = "coupon_redeem"
REDEEM_TTL_SECONDS = 300


def create_redeem_token(coupon_id: int, user_id: int) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(seconds=REDEEM_TTL_SECONDS)
    token = jwt.encode(
        {
            "scope": REDEEM_SCOPE,
            "coupon_id": int(coupon_id),
            "user_id": int(user_id),
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": expires_at,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_at


def decode_redeem_token(token: str) -> dict:
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
