"""用户行为埋点上报接口（前端批量 POST）。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import EventLog

router = APIRouter(tags=["tracking"])


class TrackEvent(BaseModel):
    event: str
    page: str = ""
    data: dict = {}
    ts: str | None = None


class TrackBatch(BaseModel):
    events: list[TrackEvent]


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

    events = body.events[:50]
    for ev in events:
        db.add(EventLog(
            user_id=user_id,
            event=ev.event[:32],
            page=ev.page[:64],
            data=ev.data or {},
        ))
    db.commit()
    return {"code": 0, "accepted": len(events)}
