from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = settings.jwt_algorithm


def create_access_token(user_id: str, openid: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "openid": openid,
        "token_type": "customer",
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("token_type") != "customer":
        return None
    return payload
