from datetime import datetime, timedelta, timezone
import hashlib

from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = settings.jwt_algorithm


def create_access_token(user_id: str, openid: str, login_version: int = 1, *, verified_phone: str | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "openid": openid,
        "token_type": "customer",
        "login_version": int(login_version),
        "exp": expire,
    }
    if verified_phone is not None:
        payload.update(phone_verification="sms-v1", verified_phone_sha256=hashlib.sha256(verified_phone.encode("utf-8")).hexdigest())
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("token_type") != "customer":
        return None
    return payload
