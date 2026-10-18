import hashlib
import json
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import HTTPException
from jose import jwt
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Staff, Technician
from app.models.staff_external_identity import StaffExternalIdentity, StaffOAuthAttempt


ATTEMPT_TTL = 300
CALLBACK_PATH = "/api/v1/auth/wecom/callback"
COMPLETE_PATH = "/technician/wecom/complete"
COOKIE_PATH = "/api/v1/auth/wecom"


class WecomProviderError(Exception):
    def __init__(self):
        super().__init__("WeCom verification unavailable")


def auth_error(code="WECOM_AUTHENTICATION_FAILED", status=401):
    return HTTPException(status_code=status, detail={"code": code, "message": "企业微信验证未完成，请重新进入"})


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def canonical_userid(value) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 or any(char.isspace() or ord(char) < 32 for char in value):
        raise WecomProviderError()
    return value.lower()


class WecomProvider:
    """Server-only official HTTPS adapter; urllib does not log credential URLs."""

    def __init__(self):
        self._token = ""
        self._token_deadline = 0.0
        self._token_key = None
        self._token_lock = threading.Lock()

    def _request(self, endpoint: str, params: dict) -> dict:
        try:
            request = Request("https://qyapi.weixin.qq.com/cgi-bin/" + endpoint + "?" + urlencode(params), headers={"Accept": "application/json"})
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read(1024 * 1024))
            if not isinstance(payload, dict) or payload.get("errcode", 0) != 0:
                raise WecomProviderError()
            return payload
        except Exception:
            # Never propagate upstream URLs, tokens, codes, bodies or errmsg.
            raise WecomProviderError() from None

    def _access_token(self) -> str:
        key = (settings.wecom_corp_id, settings.wecom_agent_secret)
        with self._token_lock:
            if key == self._token_key and self._token and time.monotonic() < self._token_deadline:
                return self._token
            if not all(key):
                raise WecomProviderError()
            payload = self._request("gettoken", {"corpid": key[0], "corpsecret": key[1]})
            token, expires = payload.get("access_token"), payload.get("expires_in")
            if not isinstance(token, str) or not token or not isinstance(expires, int) or expires <= 60:
                raise WecomProviderError()
            self._token, self._token_key = token, key
            self._token_deadline = time.monotonic() + expires - 60
            return token

    def exchange_code(self, code: str) -> str:
        payload = self._request("auth/getuserinfo", {"access_token": self._access_token(), "code": code})
        return canonical_userid(payload.get("userid"))

    def verify_member(self, userid: str) -> None:
        token = self._access_token()
        # user/get enforces this application's visibility, including departments.
        # Keep the same app Secret/token; never fall back to a directory token.
        member = self._request("user/get", {"access_token": token, "userid": userid})
        if canonical_userid(member.get("userid")) != userid or member.get("status") != 1:
            raise WecomProviderError()
        application = self._request("agent/get", {"access_token": token, "agentid": settings.wecom_agent_id})
        if str(application.get("agentid")) != settings.wecom_agent_id or application.get("close") != 0:
            raise WecomProviderError()


_provider = WecomProvider()


def get_wecom_provider() -> WecomProvider:
    return _provider


def configured_urls() -> tuple[str, str]:
    if not settings.wecom_staff_enabled:
        raise auth_error("WECOM_DISABLED", 503)
    base, callback = urlsplit(settings.h5_public_base_url), urlsplit(settings.wecom_callback_url)
    if (not settings.wecom_corp_id or not settings.wecom_agent_id or not settings.wecom_agent_secret
        or base.scheme != "https" or not base.netloc or base.username or base.password
        or callback.scheme != base.scheme or callback.netloc != base.netloc or callback.username or callback.password
        or callback.path != CALLBACK_PATH or callback.query or callback.fragment):
        raise auth_error("WECOM_CONFIGURATION_UNAVAILABLE", 503)
    return settings.wecom_callback_url, f"{base.scheme}://{base.netloc}{COMPLETE_PATH}"


def attempt_cookie(attempt_id: str) -> str:
    return "wecom_attempt_" + attempt_id


def begin_attempt(db: Session, nonce: str):
    callback, _ = configured_urls()
    state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    attempt = StaffOAuthAttempt(id=str(uuid4()), state_hash=digest(state), nonce_hash=digest(nonce), browser_hash=digest(browser), expires_at=datetime.now(timezone.utc) + timedelta(seconds=ATTEMPT_TTL))
    db.add(attempt)
    db.commit()
    query = urlencode({"appid": settings.wecom_corp_id, "redirect_uri": callback, "response_type": "code", "scope": "snsapi_base", "agentid": settings.wecom_agent_id, "state": state})
    return attempt, browser, "https://open.weixin.qq.com/connect/oauth2/authorize?" + query + "#wechat_redirect"


def browser_matches(attempt: StaffOAuthAttempt, cookies) -> bool:
    secret = cookies.get(attempt_cookie(attempt.id), "")
    return bool(secret) and secrets.compare_digest(attempt.browser_hash, digest(secret))


def local_binding(db: Session, identity: StaffExternalIdentity | None) -> Staff:
    if not identity or identity.provider != "wecom" or identity.corp_id != settings.wecom_corp_id or identity.status != "active":
        raise auth_error()
    staff = db.get(Staff, identity.staff_id)
    tech = db.get(Technician, identity.technician_id)
    if (not staff or staff.status != "active" or staff.role != "technician" or staff.technician_id != identity.technician_id
        or not tech or tech.status not in {"available", "busy"}
        or staff.store_id != identity.store_id or tech.store_id != identity.store_id):
        raise auth_error()
    if staff.temporary_expires_at is not None and datetime.now(timezone.utc) >= utc(staff.temporary_expires_at):
        raise auth_error()
    return staff


def complete_callback(db: Session, state: str, code: str, cookies, provider: WecomProvider) -> None:
    configured_urls()
    if not state or not code or len(state) > 256 or len(code) > 1024:
        return
    attempt = db.scalar(select(StaffOAuthAttempt).where(StaffOAuthAttempt.state_hash == digest(state)))
    now = datetime.now(timezone.utc)
    if not attempt or not browser_matches(attempt, cookies) or now >= utc(attempt.expires_at):
        return
    claimed = db.execute(update(StaffOAuthAttempt).where(StaffOAuthAttempt.id == attempt.id, StaffOAuthAttempt.status == "pending", StaffOAuthAttempt.expires_at > now).values(status="processing").execution_options(synchronize_session=False))
    db.commit()
    if claimed.rowcount != 1:
        return
    try:
        userid = canonical_userid(provider.exchange_code(code))
        provider.verify_member(userid)
        identity = db.scalar(select(StaffExternalIdentity).where(StaffExternalIdentity.provider == "wecom", StaffExternalIdentity.corp_id == settings.wecom_corp_id, StaffExternalIdentity.userid == userid).with_for_update())
        staff = local_binding(db, identity)
        identity.provider_verified_at = datetime.now(timezone.utc)
        db.execute(update(StaffOAuthAttempt).where(StaffOAuthAttempt.id == attempt.id, StaffOAuthAttempt.status == "processing").values(status="ready", identity_id=identity.id, binding_version=identity.binding_version, credentials_version=int(staff.credentials_version or 1)))
        db.commit()
    except (WecomProviderError, HTTPException):
        db.rollback()
        db.execute(update(StaffOAuthAttempt).where(StaffOAuthAttempt.id == attempt.id, StaffOAuthAttempt.status == "processing").values(status="failed"))
        db.commit()


def exchange_attempt(db: Session, attempt_id: str, nonce: str, cookies, provider: WecomProvider) -> dict:
    configured_urls()
    now = datetime.now(timezone.utc)
    attempt = db.get(StaffOAuthAttempt, attempt_id)
    if (not attempt or not browser_matches(attempt, cookies) or not secrets.compare_digest(attempt.nonce_hash, digest(nonce))
        or attempt.status != "ready" or now >= utc(attempt.expires_at)):
        raise auth_error()
    claimed = db.execute(update(StaffOAuthAttempt).where(StaffOAuthAttempt.id == attempt.id, StaffOAuthAttempt.status == "ready", StaffOAuthAttempt.expires_at > now).values(status="used").execution_options(synchronize_session=False))
    db.commit()
    if claimed.rowcount != 1:
        raise auth_error()
    identity = db.get(StaffExternalIdentity, attempt.identity_id)
    staff = local_binding(db, identity)
    if identity.binding_version != attempt.binding_version or int(staff.credentials_version or 1) != attempt.credentials_version:
        raise auth_error()
    verify_identity_proof(db, identity, provider)
    payload = {"sub": str(staff.id), "token_type": "staff", "role": "technician", "auth_method": "wecom", "external_identity_id": identity.id, "binding_version": identity.binding_version, "credentials_version": int(staff.credentials_version or 1), "exp": now + timedelta(hours=12)}
    return {"token": jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), "staff": {"id": staff.id, "name": staff.name, "role": "technician", "store_id": staff.store_id, "technician_id": staff.technician_id}, "auth_method": "wecom"}


def verify_identity_proof(db: Session, identity: StaffExternalIdentity, provider: WecomProvider) -> None:
    now = datetime.now(timezone.utc)
    if identity.provider_verified_at is not None and timedelta(0) <= now - utc(identity.provider_verified_at) < timedelta(seconds=ATTEMPT_TTL):
        return
    try:
        provider.verify_member(identity.userid)
    except WecomProviderError:
        raise auth_error() from None
    identity.provider_verified_at = now
    db.commit()


def validate_wecom_session(db: Session, payload: dict, staff: Staff) -> None:
    configured_urls()
    if payload.get("token_type") != "staff" or payload.get("role") != "technician":
        raise auth_error()
    identity = db.get(StaffExternalIdentity, int(payload["external_identity_id"]))
    resolved = local_binding(db, identity)
    if resolved.id != staff.id or identity.binding_version != payload.get("binding_version"):
        raise auth_error()
    verify_identity_proof(db, identity, get_wecom_provider())
