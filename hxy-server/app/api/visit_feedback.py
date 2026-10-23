"""Standalone feedback from a store or signed service-position entry."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.occupancies import ANONYMOUS_COOKIE, _browser_customer, _verify_position_qr_token
from app.core.config import settings
from app.core.customer_auth import current_customer_id
from app.db.session import get_db
from app.domain.feedback_validation import validate_feedback_tags
from app.domain.visit_feedback_tokens import (
    create_store_visit_feedback_token, create_visit_feedback_token,
    resolve_store_visit_feedback_token, resolve_visit_feedback_token,
)
from app.models import EventLog, Room, Store, VisitFeedback


router = APIRouter(tags=["visit-feedback"])
RATE_LIMIT_COUNT = 5
RATE_LIMIT_WINDOW = timedelta(hours=1)


class VisitFeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visit_feedback_token: str = Field(min_length=32, max_length=2048)
    rating: int = Field(ge=1, le=5)
    tags: list[str] = Field(default_factory=list, max_length=3)
    note: str = Field(default="", max_length=300)


class VisitFeedbackEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: int = Field(gt=0)
    position_code: str = Field(min_length=1, max_length=64)
    source: str = Field(pattern="^(personal_qr|room_qr)$")
    entry_token: str = Field(min_length=16, max_length=2048)


class StoreVisitFeedbackEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: int = Field(strict=True, gt=0, le=2**31 - 1)


class StoreVisitFeedbackEntryOut(BaseModel):
    visit_feedback_token: str
    store_id: int
    store_name: str


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_key(value: str | None) -> str:
    if not value or not 8 <= len(value) <= 128 or any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise _error(400, "IDEMPOTENCY_KEY_INVALID", "提交标识无效，请重新提交")
    return value


def _result(row: VisitFeedback) -> dict:
    return {
        "id": row.id,
        "feedback_type": "visit_feedback",
        "rating": row.rating,
        "tags": row.tags or [],
        "note": row.note,
        "submitted": True,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _lock_submission_scope(
    db: Session, identity_hash: str, room_id: int | None, qr_id: int | None,
    *, store_id: int | None = None,
) -> None:
    """Serialize one shared rate-limit scope across PostgreSQL workers."""
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    scope = f"{identity_hash}:{room_id}:{qr_id or 0}"
    if store_id is not None:
        scope = f"store:{store_id}:{scope}"
    raw = hashlib.sha256(scope.encode()).digest()[:8]
    lock_key = int.from_bytes(raw, byteorder="big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})


@router.post("/visit-feedback/store-entry", response_model=StoreVisitFeedbackEntryOut)
def enter_store_visit_feedback(
    body: StoreVisitFeedbackEntryIn,
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    if authorization is not None:
        if not authorization.startswith("Bearer "):
            raise _error(401, "CUSTOMER_SESSION_INVALID", "登录已失效，请重新登录")
        current_customer_id(authorization, db)
    store = db.get(Store, body.store_id)
    if not store or store.status != "open":
        raise _error(404, "STORE_UNAVAILABLE", "门店暂不可用")
    _, browser_token, _ = _browser_customer(db, request)
    db.commit()
    response.set_cookie(
        ANONYMOUS_COOKIE,
        browser_token,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        max_age=60 * 60 * 24 * 365 * 2,
        path="/",
    )
    return {
        "visit_feedback_token": create_store_visit_feedback_token(store.id, browser_token),
        "store_id": store.id,
        "store_name": store.name,
    }


@router.post("/visit-feedback/entry")
def enter_visit_feedback(
    body: VisitFeedbackEntryIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    qr = _verify_position_qr_token(db, body.entry_token, body.store_id, body.position_code, body.source)
    if qr is None:
        raise _error(403, "QR_BINDING_INVALID", "请使用门店服务位二维码进入")
    room = db.get(Room, qr.room_id)
    if not room or room.operational_status != "active":
        raise _error(404, "POSITION_UNAVAILABLE", "服务位暂不可用")
    _, browser_token, _ = _browser_customer(db, request)
    db.commit()
    response.set_cookie(
        ANONYMOUS_COOKIE,
        browser_token,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        max_age=60 * 60 * 24 * 365 * 2,
        path="/",
    )
    return {
        "visit_feedback_token": create_visit_feedback_token(room, qr.source, browser_token, qr.id),
        "store_id": room.store_id,
        "position_code": room.code,
        "position_label": room.customer_label,
    }


@router.post("/visit-feedback")
def submit_visit_feedback(
    body: VisitFeedbackIn,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    key = _validate_key(idempotency_key)
    validate_feedback_tags(body.rating, body.tags)
    browser_token = request.cookies.get(ANONYMOUS_COOKIE)
    store_scope = body.visit_feedback_token.startswith("vfs1.")
    if store_scope:
        store = resolve_store_visit_feedback_token(db, body.visit_feedback_token, browser_token)
        store_id, room_id, qr_id, entry_source = store.id, None, None, "store_qr"
    else:
        room, qr, entry_source = resolve_visit_feedback_token(db, body.visit_feedback_token, browser_token)
        store_id, room_id, qr_id = room.store_id, room.id, qr.id if qr else None

    customer_id = None
    if authorization is not None:
        if not authorization.startswith("Bearer "):
            raise _error(401, "CUSTOMER_SESSION_INVALID", "登录已失效，请重新登录")
        customer_id = current_customer_id(authorization, db)
        identity_hash = _hash(f"customer:{customer_id}")
    else:
        if not browser_token:
            raise _error(403, "VISIT_FEEDBACK_TOKEN_INVALID", "到店反馈入口与当前浏览器不匹配，请重新扫码")
        identity_hash = _hash(f"browser:{browser_token}")

    _lock_submission_scope(db, identity_hash, room_id, qr_id, store_id=store_id if store_scope else None)

    normalized_note = body.note.strip()
    fingerprint_payload = {
        "qr_id": qr_id,
        "room_id": room_id,
        "rating": body.rating,
        "tags": body.tags,
        "note": normalized_note,
    }
    if store_scope:
        fingerprint_payload.update(scope="store", store_id=store_id)
    fingerprint = _hash(json.dumps(fingerprint_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    key_hash = _hash(key)
    existing = db.scalar(select(VisitFeedback).where(
        VisitFeedback.identity_hash == identity_hash,
        VisitFeedback.idempotency_key_hash == key_hash,
    ))
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise _error(409, "IDEMPOTENCY_KEY_REUSED", "该提交标识已用于其他反馈")
        return _result(existing)

    cutoff = datetime.now(timezone.utc) - RATE_LIMIT_WINDOW
    recent_count = db.scalar(select(func.count()).select_from(VisitFeedback).where(
        VisitFeedback.identity_hash == identity_hash,
        VisitFeedback.store_id == store_id,
        VisitFeedback.service_position_qr_id == qr_id,
        VisitFeedback.room_id == room_id,
        VisitFeedback.created_at >= cutoff,
    )) or 0
    if recent_count >= RATE_LIMIT_COUNT:
        raise HTTPException(
            status_code=429,
            detail={"code": "FEEDBACK_RATE_LIMITED", "message": "提交过于频繁，请稍后再试"},
            headers={"Retry-After": str(int(RATE_LIMIT_WINDOW.total_seconds()))},
        )

    feedback = VisitFeedback(
        store_id=store_id,
        room_id=room_id,
        service_position_qr_id=qr_id,
        customer_id=customer_id,
        source=entry_source,
        identity_hash=identity_hash,
        idempotency_key_hash=key_hash,
        request_fingerprint=fingerprint,
        rating=body.rating,
        tags=body.tags,
        note=normalized_note,
    )
    db.add(feedback)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(VisitFeedback).where(
            VisitFeedback.identity_hash == identity_hash,
            VisitFeedback.idempotency_key_hash == key_hash,
        ))
        if existing and existing.request_fingerprint == fingerprint:
            return _result(existing)
        raise _error(409, "IDEMPOTENCY_KEY_REUSED", "该提交标识已用于其他反馈")
    db.add(EventLog(
        user_id=customer_id,
        store_id=store_id,
        event="visit_feedback_submit_success",
        page="visit_feedback",
        data={"rating_bucket": "low" if body.rating <= 2 else "mid" if body.rating == 3 else "high"},
    ))
    db.commit()
    db.refresh(feedback)
    return _result(feedback)
