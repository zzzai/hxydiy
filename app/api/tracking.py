"""用户行为埋点上报接口（前端批量 POST）。"""

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import EventLog

router = APIRouter(tags=["tracking"])


class TrackEvent(BaseModel):
    event: str = Field(min_length=1, max_length=32)
    page: str = Field(default="", max_length=64)
    data: dict = Field(default_factory=dict)
    ts: str | None = Field(default=None, max_length=64)


class TrackBatch(BaseModel):
    events: list[TrackEvent] = Field(max_length=50)


@router.post("/events")
def track_events(
    body: TrackBatch,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """批量接收埋点事件（游客 user_id 为空；单批上限 50 条）。"""
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        payload = decode_token(authorization[7:])
        if payload:
            user_id = int(payload["sub"])

    for ev in body.events:
        data = dict(ev.data or {})
        if ev.ts:
            data["client_ts"] = ev.ts
        db.add(EventLog(
            user_id=user_id,
            event=ev.event,
            page=ev.page,
            data=data,
        ))
    db.commit()
    return {"code": 0, "accepted": len(body.events)}
