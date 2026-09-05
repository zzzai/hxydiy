from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.models import User


def current_customer_id(authorization: str | None, db: Session, *, optional: bool = False) -> int | None:
    if not authorization or not authorization.startswith("Bearer "):
        if optional:
            return None
        raise HTTPException(status_code=401, detail="请先登录")
    payload = decode_token(authorization[7:])
    if not payload:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    if int(payload.get("login_version", 1)) != int(user.customer_login_version or 1):
        raise HTTPException(status_code=401, detail={
            "code": "SESSION_REPLACED",
            "message": "账号已在另一台设备登录，请重新登录",
        })
    return user.id
