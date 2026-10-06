"""Reuse verified current sessions, not arbitrary historical phone records."""

import hashlib
import re
import secrets

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.core.customer_auth import current_customer_id
from app.core.security import decode_token
from app.models import CustomerVerificationCode, User


def phone_digest(phone):
    return hashlib.sha256(phone.encode("utf-8")).hexdigest()


def verified_report_user(authorization, db):
    payload = decode_token(authorization[7:]) if authorization and authorization.startswith("Bearer ") else None
    if not payload or not str(payload.get("sub", "")).isdigit():
        raise HTTPException(401, "请先登录")
    try:
        identifier = current_customer_id(authorization, db)
    except (TypeError, ValueError, KeyError):
        raise HTTPException(401, "请重新登录") from None
    user = db.get(User, identifier)
    valid = False
    if user.phone and re.fullmatch(r"1[3-9]\d{9}", user.phone):
        if "phone_verification" in payload:
            claimed = payload.get("verified_phone_sha256")
            valid = payload["phone_verification"] == "sms-v1" and isinstance(claimed, str) and secrets.compare_digest(claimed, phone_digest(user.phone))
        elif user.last_login_at is not None:
            # These two timestamps are written together only after successful OTP.
            valid = db.scalar(select(CustomerVerificationCode.id).where(
                CustomerVerificationCode.phone == user.phone,
                CustomerVerificationCode.used_at == user.last_login_at,
                CustomerVerificationCode.sent_at <= CustomerVerificationCode.used_at,
                CustomerVerificationCode.expires_at > CustomerVerificationCode.used_at,
                CustomerVerificationCode.attempts < settings.h5_sms_max_attempts,
            ).limit(1)) is not None
    if not valid:
        raise HTTPException(403, detail={"code": "PHONE_VERIFICATION_REQUIRED", "message": "当前会话缺少本人手机号验证，请通过短信登录确认"})
    return user
