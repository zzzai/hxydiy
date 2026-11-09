"""店长每日经营：区域照片、晨会录音、转写、团队考核与总部抽检。"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func, select
from sqlalchemy.orm import Session

from app.api.admin import _current_staff
from app.api.admin_v2 import _audit, _require_admin, _require_headquarters_admin, _resolve_target_store_id
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models import (
    DailyAreaPhoto,
    DailyMeetingRecording,
    DailyStoreCheckin,
    LearningCourseVersion,
    MediaAsset,
    Staff,
    StaffLearningAssignment,
    StaffLearningEvent,
    TrainingAssessment,
)
from app.services.asr import AsrError, AsrNotConfigured, transcribe_audio
from app.services.media_storage import MediaStorageError, get_media_storage

router = APIRouter(prefix="/admin/v2/manager/daily", tags=["manager-daily"])
hq_router = APIRouter(prefix="/admin/v2/headquarters/assessments", tags=["headquarters-assessments"])

AREA_LABELS = {
    "restroom": "卫生间",
    "water_room": "打水房",
    "cashier": "收银台",
    "rest_area": "休息区",
    "foot_area": "足疗区",
}
RETENTION_DAYS = 90
SHANGHAI = ZoneInfo("Asia/Shanghai")


class AreaPhotoIn(BaseModel):
    area: str
    media_id: int = Field(gt=0)
    note: str = Field(default="", max_length=300)
    captured_at: datetime | None = None


class MeetingIn(BaseModel):
    media_id: int = Field(gt=0)
    duration_seconds: int = Field(ge=1, le=7200)
    title: str = Field(default="晨会", max_length=80)
    attendees: str = Field(default="", max_length=300)


class AssessmentIn(BaseModel):
    course_name: str = Field(min_length=1, max_length=120)
    kind: str = "practical"
    result: str = "passed"
    note: str = Field(default="", max_length=500)
    assignment_id: str | None = None


class SpotCheckIn(BaseModel):
    hq_status: str
    note: str = Field(default="", max_length=500)


def _today() -> date:
    return datetime.now(SHANGHAI).date()


def _parse_day(value: str | None) -> date:
    if not value:
        return _today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail={"code": "DATE_INVALID", "message": "日期格式无效"}) from None


def _checkin(db: Session, store_id: int, manager_id: int, business_date: date, *, create: bool) -> DailyStoreCheckin | None:
    item = db.scalar(select(DailyStoreCheckin).where(
        DailyStoreCheckin.store_id == store_id,
        DailyStoreCheckin.business_date == business_date,
    ).with_for_update())
    if item is None and create:
        item = DailyStoreCheckin(store_id=store_id, business_date=business_date, manager_staff_id=manager_id)
        db.add(item)
        db.flush()
    return item


def _media_url(media: MediaAsset) -> str:
    try:
        storage = get_media_storage(settings)
        return storage.url(media.object_key) or f"/api/v1/admin/media/{media.id}/content"
    except MediaStorageError:
        return f"/api/v1/admin/media/{media.id}/content"


def _media_view(media: MediaAsset | None) -> dict | None:
    if not media or media.deleted_at:
        return None
    return {
        "id": media.id,
        "url": _media_url(media),
        "content_type": media.content_type,
        "media_type": media.media_type,
        "size_bytes": media.size_bytes,
        "created_at": media.created_at.isoformat() if media.created_at else None,
    }


def _meeting_view(db: Session, item: DailyMeetingRecording) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "attendees": item.attendees,
        "duration_seconds": item.duration_seconds,
        "transcript_status": item.transcript_status,
        "transcript_text": item.transcript_text,
        "summary_text": item.summary_text,
        "error_message": item.error_message,
        "retention_until": item.retention_until.isoformat(),
        "media": _media_view(db.get(MediaAsset, item.media_id)),
        "created_at": item.created_at.isoformat(),
    }


def _daily_view(db: Session, checkin: DailyStoreCheckin | None, business_date: date) -> dict:
    if checkin is None:
        return {
            "business_date": business_date.isoformat(),
            "checkin_id": None,
            "status": "draft",
            "submitted_at": None,
            "areas": [{"key": key, "label": label, "done": False, "photo": None} for key, label in AREA_LABELS.items()],
            "meetings": [],
            "completion": {"areas_done": 0, "areas_total": 5, "has_meeting": False, "submitted": False},
        }
    photos = {item.area: item for item in db.scalars(select(DailyAreaPhoto).where(DailyAreaPhoto.checkin_id == checkin.id))}
    meetings = list(db.scalars(select(DailyMeetingRecording).where(
        DailyMeetingRecording.checkin_id == checkin.id,
    ).order_by(DailyMeetingRecording.created_at.desc())))
    areas = []
    for key, label in AREA_LABELS.items():
        photo = photos.get(key)
        areas.append({
            "key": key,
            "label": label,
            "done": photo is not None,
            "photo": {
                "id": photo.id,
                "media": _media_view(db.get(MediaAsset, photo.media_id)),
                "note": photo.note,
                "captured_at": photo.captured_at.isoformat() if photo.captured_at else None,
            } if photo else None,
        })
    return {
        "business_date": business_date.isoformat(),
        "checkin_id": checkin.id,
        "status": checkin.status,
        "submitted_at": checkin.submitted_at.isoformat() if checkin.submitted_at else None,
        "areas": areas,
        "meetings": [_meeting_view(db, item) for item in meetings],
        "completion": {
            "areas_done": len(photos),
            "areas_total": 5,
            "has_meeting": bool(meetings),
            "submitted": checkin.status == "submitted",
        },
    }


def _purge_expired(db: Session, store_id: int) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
    old_checkins = list(db.scalars(select(DailyStoreCheckin).where(
        DailyStoreCheckin.store_id == store_id,
        DailyStoreCheckin.created_at < cutoff,
    )))
    for checkin in old_checkins:
        photos = list(db.scalars(select(DailyAreaPhoto).where(DailyAreaPhoto.checkin_id == checkin.id)))
        meetings = list(db.scalars(select(DailyMeetingRecording).where(DailyMeetingRecording.checkin_id == checkin.id)))
        for item in [*photos, *meetings]:
            media = db.get(MediaAsset, item.media_id)
            if media and not media.deleted_at:
                try:
                    get_media_storage(settings).delete(media.object_key)
                except MediaStorageError:
                    pass
                media.deleted_at = datetime.now(UTC)
            db.delete(item)
        db.delete(checkin)
    if old_checkins:
        db.commit()


def _process_meeting(meeting_id: int) -> None:
    with SessionLocal() as db:
        item = db.get(DailyMeetingRecording, meeting_id)
        if not item:
            return
        item.transcript_status = "transcribing"
        item.error_message = ""
        db.commit()
        media = db.get(MediaAsset, item.media_id)
        try:
            if not media or media.deleted_at:
                raise AsrError("录音文件不存在")
            text = transcribe_audio(_media_url(media))
            item.transcript_text = text
            item.summary_text = text[:240]
            item.transcript_status = "transcribed"
            item.error_message = ""
        except AsrNotConfigured:
            item.transcript_status = "not_configured"
            item.error_message = "转写服务未配置，请联系总部配置腾讯云 ASR 密钥"
        except (AsrError, MediaStorageError) as exc:
            item.transcript_status = "failed"
            item.error_message = str(exc)[:500]
        db.commit()


@router.get("")
def get_daily(
    on_date: str | None = Query(None, alias="date"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _resolve_target_store_id(db, staff, None)
    _purge_expired(db, store_id)
    business_date = _parse_day(on_date)
    item = _checkin(db, store_id, staff.id, business_date, create=True)
    db.commit()
    return _daily_view(db, item, business_date)


@router.post("/photos")
def save_area_photo(
    body: AreaPhotoIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _resolve_target_store_id(db, staff, None)
    if body.area not in AREA_LABELS:
        raise HTTPException(status_code=422, detail={"code": "AREA_INVALID", "message": "巡检区域无效"})
    media = db.get(MediaAsset, body.media_id)
    if not media or media.deleted_at or media.store_id != store_id or media.media_type != "image":
        raise HTTPException(status_code=404, detail={"code": "MEDIA_NOT_FOUND", "message": "照片不存在"})
    checkin = _checkin(db, store_id, staff.id, _today(), create=True)
    assert checkin is not None
    photo = db.scalar(select(DailyAreaPhoto).where(
        DailyAreaPhoto.checkin_id == checkin.id, DailyAreaPhoto.area == body.area,
    ))
    if photo:
        photo.media_id = media.id
        photo.note = body.note.strip()
        photo.captured_at = body.captured_at or datetime.now(UTC)
        photo.created_by_staff_id = staff.id
    else:
        photo = DailyAreaPhoto(
            checkin_id=checkin.id, area=body.area, media_id=media.id, note=body.note.strip(),
            captured_at=body.captured_at or datetime.now(UTC), created_by_staff_id=staff.id,
        )
        db.add(photo)
    if checkin.status == "submitted":
        checkin.status = "draft"
        checkin.submitted_at = None
    _audit(db, staff, "manager_daily_area_photo", "daily_checkin", str(checkin.id), {
        "store_id": store_id, "area": body.area, "media_id": media.id,
    })
    db.commit()
    return _daily_view(db, checkin, checkin.business_date)


@router.post("/meeting")
def save_meeting(
    body: MeetingIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _resolve_target_store_id(db, staff, None)
    media = db.get(MediaAsset, body.media_id)
    if not media or media.deleted_at or media.store_id != store_id or media.media_type != "audio":
        raise HTTPException(status_code=404, detail={"code": "MEDIA_NOT_FOUND", "message": "录音不存在"})
    checkin = _checkin(db, store_id, staff.id, _today(), create=True)
    assert checkin is not None
    now = datetime.now(UTC)
    item = DailyMeetingRecording(
        checkin_id=checkin.id, media_id=media.id, title=body.title.strip() or "晨会",
        attendees=body.attendees.strip(), duration_seconds=body.duration_seconds,
        transcript_status="transcribing" if settings.asr_ready else "not_configured",
        asr_provider=settings.asr_provider if settings.asr_ready else "",
        retention_until=now + timedelta(days=RETENTION_DAYS), created_by_staff_id=staff.id,
    )
    db.add(item)
    db.flush()
    if settings.asr_ready:
        background.add_task(_process_meeting, item.id)
    else:
        item.error_message = "转写服务未配置，请联系总部配置腾讯云 ASR 密钥"
    _audit(db, staff, "manager_daily_meeting", "daily_meeting", str(item.id), {
        "store_id": store_id, "media_id": media.id, "duration_seconds": body.duration_seconds,
    })
    db.commit()
    return _daily_view(db, checkin, checkin.business_date)


@router.post("/meetings/{meeting_id}/retry-transcribe")
def retry_transcribe(
    meeting_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _resolve_target_store_id(db, staff, None)
    item = db.get(DailyMeetingRecording, meeting_id)
    if not item:
        raise HTTPException(status_code=404, detail={"code": "MEETING_NOT_FOUND", "message": "录音不存在"})
    checkin = db.get(DailyStoreCheckin, item.checkin_id)
    if not checkin or checkin.store_id != store_id:
        raise HTTPException(status_code=404, detail={"code": "MEETING_NOT_FOUND", "message": "录音不存在"})
    if not settings.asr_ready:
        raise HTTPException(status_code=409, detail={"code": "ASR_NOT_CONFIGURED", "message": "转写服务未配置"})
    item.transcript_status = "transcribing"
    item.error_message = ""
    db.commit()
    background.add_task(_process_meeting, item.id)
    return {"ok": True}


@router.post("/submit")
def submit_daily(db: Session = Depends(get_db), authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _resolve_target_store_id(db, staff, None)
    checkin = _checkin(db, store_id, staff.id, _today(), create=True)
    assert checkin is not None
    photos = int(db.scalar(select(sa_func.count()).select_from(DailyAreaPhoto).where(
        DailyAreaPhoto.checkin_id == checkin.id,
    )) or 0)
    meetings = int(db.scalar(select(sa_func.count()).select_from(DailyMeetingRecording).where(
        DailyMeetingRecording.checkin_id == checkin.id,
    )) or 0)
    if photos < 5 or meetings < 1:
        raise HTTPException(status_code=409, detail={
            "code": "DAILY_INCOMPLETE", "message": "请先完成 5 个区域照片和晨会录音",
            "areas_done": photos, "has_meeting": meetings > 0,
        })
    checkin.status = "submitted"
    checkin.submitted_at = datetime.now(UTC)
    _audit(db, staff, "manager_daily_submit", "daily_checkin", str(checkin.id), {"store_id": store_id})
    db.commit()
    return _daily_view(db, checkin, checkin.business_date)


@router.get("/history")
def daily_history(
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _resolve_target_store_id(db, staff, None)
    since = _today() - timedelta(days=days - 1)
    items = list(db.scalars(select(DailyStoreCheckin).where(
        DailyStoreCheckin.store_id == store_id, DailyStoreCheckin.business_date >= since,
    ).order_by(DailyStoreCheckin.business_date.desc())))
    return {"items": [{
        "business_date": item.business_date.isoformat(),
        "status": item.status,
        "submitted_at": item.submitted_at.isoformat() if item.submitted_at else None,
    } for item in items]}


def _team_staff(db: Session, store_id: int) -> list[Staff]:
    return list(db.scalars(select(Staff).where(
        Staff.store_id == store_id,
        Staff.status == "active",
        Staff.technician_id.is_not(None),
        Staff.role.in_(("manager", "technician")),
    ).order_by(Staff.id)))


def _learning_progress(db: Session, assignment: StaffLearningAssignment) -> dict:
    course = db.get(LearningCourseVersion, assignment.course_version_id)
    sections = (course.content or {}).get("sections", []) if course else []
    total = max(1, len(sections))
    done = len([item for item in (assignment.sections_read or []) if item in {section.get("id") for section in sections}])
    submits = list(db.scalars(select(StaffLearningEvent).where(
        StaffLearningEvent.assignment_id == assignment.id,
        StaffLearningEvent.kind == "submit",
    ).order_by(StaffLearningEvent.created_at.desc())))
    latest = submits[0].payload if submits else {}
    score = latest.get("correct")
    return {
        "assignment_id": assignment.id,
        "course": course.code if course else "",
        "course_version": course.version if course else "",
        "title": ((course.content or {}).get("title") if course else "") or (course.code if course else "学习任务"),
        "progress": round(done / total * 100),
        "sections_done": done,
        "sections_total": total,
        "submitted": bool(submits),
        "score": score,
        "total_questions": latest.get("total"),
    }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _team_view(db: Session, store_id: int) -> dict:
    people = _team_staff(db, store_id)
    now = datetime.now(UTC)
    rows = []
    for person in people:
        assignments = list(db.scalars(select(StaffLearningAssignment).where(
            StaffLearningAssignment.store_id == store_id,
            StaffLearningAssignment.staff_id == person.id,
        ).order_by(StaffLearningAssignment.assigned_at.desc())))
        latest = _learning_progress(db, assignments[0]) if assignments else None
        due = _aware(assignments[0].assigned_at) + timedelta(days=7) if assignments else None
        complete = bool(latest and latest["submitted"] and (latest["score"] or 0) >= (latest["total_questions"] or 1))
        overdue = bool(assignments and not complete and due and due < now)
        assessments = list(db.scalars(select(TrainingAssessment).where(
            TrainingAssessment.store_id == store_id,
            TrainingAssessment.staff_id == person.id,
        ).order_by(TrainingAssessment.created_at.desc())))
        latest_assessment = assessments[0] if assessments else None
        rows.append({
            "staff_id": person.id,
            "name": person.name,
            "role": person.role,
            "technician_id": person.technician_id,
            "progress": latest["progress"] if latest else 0,
            "learning": latest,
            "complete": complete,
            "overdue": overdue,
            "due_at": due.isoformat() if due else None,
            "assessment": {
                "id": latest_assessment.id,
                "course_name": latest_assessment.course_name,
                "kind": latest_assessment.kind,
                "result": latest_assessment.result,
                "hq_status": latest_assessment.hq_status,
                "manager_confirmed_at": latest_assessment.manager_confirmed_at.isoformat() if latest_assessment.manager_confirmed_at else None,
                "hq_note": latest_assessment.hq_note,
            } if latest_assessment else None,
        })
    return {
        "summary": {
            "staff_count": len(rows),
            "on_track": sum(1 for row in rows if row["complete"] and not row["overdue"]),
            "overdue": sum(1 for row in rows if row["overdue"]),
        },
        "technicians": rows,
    }


@router.get("/team")
def get_team(db: Session = Depends(get_db), authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    _require_admin(staff)
    store_id = _resolve_target_store_id(db, staff, None)
    return _team_view(db, store_id)


@router.post("/team/{staff_id}/assessments")
def confirm_assessment(
    staff_id: int,
    body: AssessmentIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    manager = _current_staff(authorization, db)
    _require_admin(manager)
    store_id = _resolve_target_store_id(db, manager, None)
    target = db.get(Staff, staff_id)
    if not target or target.store_id != store_id:
        raise HTTPException(status_code=404, detail={"code": "STAFF_NOT_FOUND", "message": "技师不存在"})
    if body.kind not in {"theory", "practical"} or body.result not in {"passed", "failed"}:
        raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_INVALID", "message": "考核类型或结果无效"})
    item = TrainingAssessment(
        store_id=store_id, staff_id=target.id, assignment_id=body.assignment_id,
        course_name=body.course_name.strip(), kind=body.kind, result=body.result,
        manager_staff_id=manager.id, manager_note=body.note.strip(),
        manager_confirmed_at=datetime.now(UTC), hq_status="pending",
    )
    db.add(item)
    _audit(db, manager, "manager_training_assessment", "training_assessment", "pending", {
        "store_id": store_id, "staff_id": target.id, "result": body.result, "hq_status": "pending",
    })
    db.commit()
    return _team_view(db, store_id)


@hq_router.get("")
def hq_assessments(
    status: str = Query("pending"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_headquarters_admin(staff)
    query = select(TrainingAssessment).order_by(TrainingAssessment.created_at.desc()).limit(200)
    if status in {"pending", "passed", "returned"}:
        query = query.where(TrainingAssessment.hq_status == status)
    rows = list(db.scalars(query))
    people = {item.id: item.name for item in db.scalars(select(Staff).where(Staff.id.in_({row.staff_id for row in rows})))} if rows else {}
    return {"items": [{
        "id": row.id, "store_id": row.store_id, "staff_id": row.staff_id,
        "staff_name": people.get(row.staff_id, ""), "course_name": row.course_name,
        "kind": row.kind, "result": row.result, "hq_status": row.hq_status,
        "manager_note": row.manager_note, "manager_confirmed_at": row.manager_confirmed_at.isoformat() if row.manager_confirmed_at else None,
        "hq_note": row.hq_note, "hq_reviewed_at": row.hq_reviewed_at.isoformat() if row.hq_reviewed_at else None,
    } for row in rows]}


@hq_router.post("/{assessment_id}/spot-check")
def spot_check(
    assessment_id: int,
    body: SpotCheckIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_headquarters_admin(staff)
    if body.hq_status not in {"passed", "returned"}:
        raise HTTPException(status_code=422, detail={"code": "HQ_STATUS_INVALID", "message": "抽检结果无效"})
    item = db.get(TrainingAssessment, assessment_id)
    if not item:
        raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_NOT_FOUND", "message": "考核记录不存在"})
    item.hq_status = body.hq_status
    item.hq_reviewer_staff_id = staff.id
    item.hq_note = body.note.strip()
    item.hq_reviewed_at = datetime.now(UTC)
    if body.hq_status == "passed":
        item.result = "passed"
    elif item.result == "passed":
        item.result = "failed"
    _audit(db, staff, "hq_training_spot_check", "training_assessment", str(item.id), {
        "store_id": item.store_id, "hq_status": body.hq_status,
    })
    db.commit()
    return {"id": item.id, "hq_status": item.hq_status, "result": item.result}
