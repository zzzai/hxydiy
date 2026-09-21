"""Standalone feedback from a verified in-store QR entry."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.occupancies import ANONYMOUS_COOKIE
from app.core.customer_auth import current_customer_id
from app.db.session import get_db
from app.domain.feedback_validation import validate_feedback_tags
from app.domain.visit_feedback_tokens import resolve_visit_feedback_token
from app.models import EventLog, VisitFeedback


router = APIRouter(tags=["visit-feedback"])
RATE_LIMIT_COUNT = 5
RATE_LIMIT_WINDOW = timedelta(hours=1)


class VisitFeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visit_feedback_token: str = Field(min_length=32, max_length=2048)
    rating: int = Field(ge=1, le=5)
    tags: list[str] = Field(default_factory=list, max_length=3)
    note: str = Field(default="", max_length=300)


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


def _lock_submission_scope(db: Session, identity_hash: str, room_id: int, qr_id: int | None) -> None:
    """Serialize one shared rate-limit scope across PostgreSQL workers."""
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    raw = hashlib.sha256(f"{identity_hash}:{room_id}:{qr_id or 0}".encode()).digest()[:8]
    lock_key = int.from_bytes(raw, byteorder="big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})


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
    room, qr, entry_source = resolve_visit_feedback_token(db, body.visit_feedback_token, browser_token)

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

    _lock_submission_scope(db, identity_hash, room.id, qr.id if qr else None)

    normalized_note = body.note.strip()
    fingerprint = _hash(json.dumps({
        "qr_id": qr.id if qr else None,
        "room_id": room.id,
        "rating": body.rating,
        "tags": body.tags,
        "note": normalized_note,
    }, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
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
        VisitFeedback.service_position_qr_id == (qr.id if qr else None),
        VisitFeedback.room_id == room.id,
        VisitFeedback.created_at >= cutoff,
    )) or 0
    if recent_count >= RATE_LIMIT_COUNT:
        raise HTTPException(
            status_code=429,
            detail={"code": "FEEDBACK_RATE_LIMITED", "message": "提交过于频繁，请稍后再试"},
            headers={"Retry-After": str(int(RATE_LIMIT_WINDOW.total_seconds()))},
        )

    feedback = VisitFeedback(
        store_id=room.store_id,
        room_id=room.id,
        service_position_qr_id=qr.id if qr else None,
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
        store_id=room.store_id,
        event="visit_feedback_submit_success",
        page="visit_feedback",
        data={"rating_bucket": "low" if body.rating <= 2 else "mid" if body.rating == 3 else "high"},
    ))
    db.commit()
    db.refresh(feedback)
    return _result(feedback)
