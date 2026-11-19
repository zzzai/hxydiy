import hashlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.admin import _current_staff, normalize_staff_role
from app.api.technician import current_technician
from app.core.config import settings
from app.db.session import get_db
from app.domain.learning_content import applies_to_store
from app.domain.learning_daily import SHANGHAI, daily_projection, normalize_plan
from app.domain.service_record_status import pending_record_summary
from app.models import AuditLog, ServiceFeedback, Staff, Store
from app.models.operations import Technician
from app.models.staff_learning import LearningCourseVersion, StaffLearningAssignment, StaffLearningEvent
from app.schemas.staff_learning import LearningActionIn, LearningAssignmentIn, LearningCoachIn, LearningWeeklyPlanIn
from app.services.learning_ai import (
    LearningAIError,
    LearningAIProvider,
    coach_messages,
    parse_coach_reply,
    parse_weekly_plan_reply,
    weekly_plan_messages,
)

router = APIRouter(prefix="/staff-learning", tags=["staff-learning"])


def error(status, code, message):
    return HTTPException(status, detail={"code": code, "message": message})


def content_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def actor(authorization, db, request, *, enabled=True):
    if request.query_params:
        raise error(422, "LEARNING_SCOPE_OVERRIDE", "学习范围由登录身份确定")
    staff = _current_staff(authorization, db)
    if not staff.store_id:
        raise error(403, "LEARNING_STORE_REQUIRED", "请进入具体门店工作台")
    role = normalize_staff_role(staff.role, staff.technician_id)
    if role not in {"manager", "technician"}:
        raise error(403, "LEARNING_ROLE_REQUIRED", "当前身份不能查看学习记录")
    if role == "technician":
        current_technician(authorization, db)
    if enabled and not settings.staff_learning_enabled:
        raise error(404, "LEARNING_DISABLED", "学习功能尚未开放")
    return staff, role


def available(course):
    return course.status == "published" and bool(course.approval_reference.strip()) or (
        course.status == "pilot" and settings.environment in {"local", "test"}
    )


def assignable_courses(courses, store_id):
    active = [c for c in courses if available(c) and applies_to_store(c.content, store_id)]
    replaced = {(c.code, c.content["replacesVersion"]) for c in active if "replacesVersion" in c.content}
    eligible = [c for c in active if (c.code, c.version) not in replaced]
    return sorted(eligible, key=lambda c: "storeIds" not in c.content)


def checked_content(course):
    if content_hash(course.content) != course.content_sha256:
        raise error(409, "LEARNING_CONTENT_CHANGED", "课程版本内容需要核验，请联系课程负责人")
    return course.content


def public_course(course):
    source = checked_content(course)
    return {key: source[key] for key in ("id", "version", "title", "category", "minutes", "intro", "sections", "sources")} | {
        "questions": [{key: q[key] for key in ("id", "prompt", "choices")} for q in source["questions"]]
    }


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()


def roster_query(store_id):
    return select(Staff).join(Technician, Staff.technician_id == Technician.id).where(
        Staff.store_id == store_id, Technician.store_id == store_id,
        Staff.role == "technician", Staff.status == "active", Technician.status.in_(["available", "busy"])
    ).order_by(Staff.id)


def snapshot(db, staff, role):
    query = select(StaffLearningAssignment).where(StaffLearningAssignment.store_id == staff.store_id)
    if role == "technician":
        query = query.where(StaffLearningAssignment.staff_id == staff.id)
    assignments = list(db.scalars(query.order_by(StaffLearningAssignment.assigned_at, StaffLearningAssignment.id)))
    course_ids = {item.course_version_id for item in assignments}
    courses = list(db.scalars(select(LearningCourseVersion).order_by(LearningCourseVersion.code, LearningCourseVersion.version)))
    courses = [c for c in courses if applies_to_store(c.content, staff.store_id) and (available(c) or (c.id in course_ids and c.status == "retired"))]
    if any(item.course_version_id not in {c.id for c in courses} for item in assignments):
        raise error(409, "LEARNING_COURSE_UNAVAILABLE", "已安排的课程暂不可用，请联系课程负责人")
    visible_courses = courses if role == "manager" else [c for c in courses if c.id in course_ids]
    events = list(db.scalars(select(StaffLearningEvent).where(
        StaffLearningEvent.store_id == staff.store_id,
        StaffLearningEvent.assignment_id.in_([item.id for item in assignments])
    ).order_by(StaffLearningEvent.assignment_revision, StaffLearningEvent.created_at, StaffLearningEvent.id))) if assignments else []
    grouped = {}
    for event in events:
        grouped.setdefault(event.assignment_id, []).append(event)
    course_by_id = {c.id: c for c in courses}
    result = []
    daily_tasks = []
    now = datetime.now(UTC)
    for item in assignments:
        course = course_by_id[item.course_version_id]
        history = grouped.get(item.id, [])
        base = {
            "id": item.id, "storeId": item.store_id, "staffId": item.staff_id, "staffName": item.staff_name,
            "courseId": course.code, "courseVersion": course.version, "assignedAt": iso(item.assigned_at),
            "dueAt": None, "revision": item.revision, "sectionsRead": item.sections_read,
            "attempts": [{"id": e.id, **e.payload, "createdAt": iso(e.created_at)} for e in history if e.kind == "submit"],
            "followUps": [{"id": e.id, "managerId": e.actor_id, "managerName": e.actor_name, "note": e.payload["note"], "createdAt": iso(e.created_at)} for e in history if e.kind == "follow_up"],
        }
        # Keep the legacy response; daily clients consume independently scoped tasks.
        result.append(base)
        plans = [e for e in history if e.kind == "assign" and "daily_plan" in e.payload]
        legacy = [e for e in history if not any(k in e.payload for k in ("daily_plan", "daily_plan_id", "daily_plan_replay"))]
        if legacy or not plans:
            daily_tasks.append({**base,
                "attempts": [{"id": e.id, **e.payload, "createdAt": iso(e.created_at)} for e in legacy if e.kind == "submit"],
                "followUps": [{"id": e.id, "managerId": e.actor_id, "managerName": e.actor_name, "note": e.payload["note"], "createdAt": iso(e.created_at)} for e in legacy if e.kind == "follow_up"],
            })
        for plan in plans:
            daily_tasks.append({
                **base, "id": "daily:" + plan.id, "assignmentId": item.id,
                **daily_projection(plan, history, [section["id"] for section in checked_content(course)["sections"]], now),
            })
    return {
        "dailyTasks": daily_tasks, "learningToday": now.astimezone(SHANGHAI).date().isoformat(), "serverNow": now.isoformat(),
        "actor": {"id": staff.id, "storeId": staff.store_id, "role": role, "name": staff.name},
        "assignments": result,
        "courses": [public_course(c) for c in visible_courses],
        "assignableCourses": [{"id": c.code, "version": c.version} for c in assignable_courses(courses, staff.store_id)] if role == "manager" else [],
        "roster": [{"id": s.id, "name": s.name} for s in db.scalars(roster_query(staff.store_id))] if role == "manager" else [],
    }


def lock_actor(db, staff):
    # Consistent lock order: actor row, then assignment row.
    db.scalar(select(Staff).where(Staff.id == staff.id).with_for_update())


def receipt(db, staff, request_id, fingerprint):
    event = db.scalar(select(StaffLearningEvent).where(
        StaffLearningEvent.store_id == staff.store_id, StaffLearningEvent.actor_id == staff.id,
        StaffLearningEvent.request_id == request_id
    ))
    if event and event.fingerprint != fingerprint:
        raise error(409, "LEARNING_REQUEST_REUSED", "提交内容已变化，不能复用之前的提交编号")
    return event


def record(db, staff, assignment, kind, request_id, fingerprint, payload):
    db.add(StaffLearningEvent(id=str(uuid.uuid4()), store_id=staff.store_id, assignment_id=assignment.id,
        actor_id=staff.id, actor_name=staff.name, request_id=request_id, assignment_revision=assignment.revision, fingerprint=fingerprint, kind=kind, payload=payload))


@router.get("/status")
def status(request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)):
    actor(authorization, db, request, enabled=False)
    return {
        "enabled": settings.staff_learning_enabled,
        "ai_coach_enabled": settings.learning_ai_ready,
        "ai_plan_enabled": settings.learning_ai_ready,
    }


@router.get("/bootstrap")
def bootstrap(request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)):
    staff, role = actor(authorization, db, request)
    return snapshot(db, staff, role)


@router.post("/assignments")
def assign(body: LearningAssignmentIn, request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)):
    staff, role = actor(authorization, db, request)
    if role != "manager":
        raise error(403, "LEARNING_MANAGER_REQUIRED", "仅店长可安排本店学习")
    values = body.model_dump(mode="json")
    if body.learning_date is None:
        values.pop("learning_date")
        values.pop("due_time")
    fingerprint = content_hash({"kind": "assign", **values})
    lock_actor(db, staff)
    if receipt(db, staff, body.request_id, fingerprint):
        return snapshot(db, staff, role)
    plan = None
    if body.learning_date is not None:
        try:
            plan = normalize_plan(body.learning_date, body.due_time, datetime.now(UTC))
        except ValueError as exc:
            raise error(422, "LEARNING_DATE_INVALID", str(exc))
    learner = db.scalar(roster_query(staff.store_id).where(Staff.id == body.staff_id).with_for_update(of=Staff))
    versions = db.scalars(select(LearningCourseVersion).where(LearningCourseVersion.code == body.course_id))
    course = next((c for c in assignable_courses(versions, staff.store_id) if c.version == body.course_version), None)
    if not learner:
        raise error(404, "LEARNING_STAFF_UNAVAILABLE", "该技师不在本店可安排学习名单中")
    if course is None:
        raise error(409, "LEARNING_COURSE_UNAVAILABLE", "该课程尚未开放安排")
    checked_content(course)
    item = db.scalar(select(StaffLearningAssignment).where(
        StaffLearningAssignment.store_id == staff.store_id, StaffLearningAssignment.staff_id == learner.id,
        StaffLearningAssignment.course_version_id == course.id
    ).with_for_update())
    if not item:
        # A savepoint handles two managers assigning the same course concurrently.
        try:
            with db.begin_nested():
                item = StaffLearningAssignment(id=str(uuid.uuid4()), store_id=staff.store_id, staff_id=learner.id,
                    staff_name=learner.name, course_version_id=course.id, assigned_by=staff.id, revision=0, sections_read=[])
                db.add(item)
                db.flush()
        except IntegrityError:
            item = db.scalar(select(StaffLearningAssignment).where(
                StaffLearningAssignment.store_id == staff.store_id, StaffLearningAssignment.staff_id == learner.id,
                StaffLearningAssignment.course_version_id == course.id
            ))
            if item is None:
                raise
    payload = {}
    if plan is not None:
        existing = next((event for event in db.scalars(select(StaffLearningEvent).where(
            StaffLearningEvent.assignment_id == item.id, StaffLearningEvent.kind == "assign"
        )) if event.payload.get("daily_plan", {}).get("learning_date") == plan["learning_date"]), None)
        if existing:
            if existing.payload["daily_plan"] != plan:
                raise error(409, "LEARNING_DATE_ALREADY_ASSIGNED", "这一天已安排本课，请保留原截止时间")
            payload = {"daily_plan_replay": existing.id}
        else:
            item.revision += 1
            payload = {"daily_plan": plan}
    record(db, staff, item, "assign", body.request_id, fingerprint, payload)
    db.commit()
    return snapshot(db, staff, role)


@router.post("/assignments/{assignment_id}/actions")
def action(assignment_id: str, body: LearningActionIn, request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)):
    staff, role = actor(authorization, db, request)
    if (body.kind == "follow_up") != (role == "manager"):
        raise error(403, "LEARNING_ACTION_FORBIDDEN", "不能替技师答题或修改他人的跟进记录")
    lock_actor(db, staff)
    query = select(StaffLearningAssignment).where(
        StaffLearningAssignment.id == assignment_id, StaffLearningAssignment.store_id == staff.store_id
    )
    if role == "technician":
        query = query.where(StaffLearningAssignment.staff_id == staff.id)
    item = db.scalar(query.with_for_update())
    if not item:
        raise error(404, "LEARNING_TASK_NOT_FOUND", "学习任务不存在或不属于当前身份")
    values = body.model_dump()
    if body.daily_plan_id is None:
        values.pop("daily_plan_id")
    fingerprint = content_hash({"assignment_id": assignment_id, **values})
    if receipt(db, staff, body.request_id, fingerprint):
        return snapshot(db, staff, role)
    if item.revision != body.expected_revision:
        raise error(409, "LEARNING_REVISION_CONFLICT", "记录已更新，请刷新进度后重试")
    course = db.get(LearningCourseVersion, item.course_version_id)
    if not course or not available(course) or not applies_to_store(course.content, staff.store_id):
        raise error(409, "LEARNING_COURSE_UNAVAILABLE", "课程已停止新的学习操作")
    content = checked_content(course)
    payload = {}
    sections_read = item.sections_read
    if body.daily_plan_id:
        history = list(db.scalars(select(StaffLearningEvent).where(StaffLearningEvent.assignment_id == item.id)))
        plan = next((event for event in history if event.id == body.daily_plan_id and event.kind == "assign" and "daily_plan" in event.payload), None)
        if plan is None:
            raise error(404, "LEARNING_DAILY_TASK_NOT_FOUND", "每日任务不存在或不属于当前学习记录")
        daily = daily_projection(plan, history, [section["id"] for section in content["sections"]], datetime.now(UTC))
        if daily["dailyStatus"] == "scheduled":
            raise error(409, "LEARNING_DATE_NOT_STARTED", "请在安排的学习日期开始学习")
        if body.kind == "follow_up" and (not daily["attempts"] or daily["dailyStatus"] == "completed"):
            raise error(409, "LEARNING_COACHING_NOT_REQUIRED", "请在有错题的练习后记录辅导建议")
        sections_read = daily["sectionsRead"]
    if body.kind == "mark_section":
        ids = [section["id"] for section in content["sections"]]
        if body.section_id not in ids or any(value not in sections_read for value in ids[:ids.index(body.section_id)]):
            raise error(422, "LEARNING_SECTION_ORDER", "请先学习前面的内容")
        if not body.daily_plan_id:
            item.sections_read = list(dict.fromkeys([*item.sections_read, body.section_id]))
        payload = {"sectionId": body.section_id}
    elif body.kind == "submit":
        questions = content["questions"]
        if any(section["id"] not in sections_read for section in content["sections"]):
            raise error(422, "LEARNING_READING_REQUIRED", "请先读完本课内容")
        if set(body.answers) != {q["id"] for q in questions} or any(not 0 <= body.answers[q["id"]] < len(q["choices"]) for q in questions):
            raise error(422, "LEARNING_ANSWERS_INCOMPLETE", "请完整回答本课题目")
        payload = {"answers": body.answers, "correct": sum(body.answers[q["id"]] == q["answer"] for q in questions),
            "total": len(questions), "review": [{"questionId": q["id"], "answer": q["answer"], "explanation": q["explanation"]} for q in questions]}
    else:
        payload = {"note": body.note.strip()}
    if body.daily_plan_id:
        payload["daily_plan_id"] = body.daily_plan_id
    item.revision += 1
    record(db, staff, item, body.kind, body.request_id, fingerprint, payload)
    db.commit()
    return snapshot(db, staff, role)


def _ai_count(db, action: str, *, staff_id: int | None = None, store_id: int | None = None) -> int:
    since = datetime.now(UTC) - timedelta(hours=24)
    query = select(func.count(AuditLog.id)).where(AuditLog.action == action, AuditLog.created_at >= since)
    if staff_id is not None:
        query = query.where(AuditLog.actor_type == "staff", AuditLog.actor_id == str(staff_id))
    if store_id is not None:
        query = query.where(AuditLog.store_id == store_id)
    return int(db.scalar(query) or 0)


def _ai_audit(
    db,
    staff,
    action: str,
    status: str,
    *,
    entity_id: str,
    code: str = "",
    course_code: str = "",
    latency_ms: int = 0,
    usage: dict | None = None,
    question_chars: int = 0,
    grounded: bool | None = None,
) -> None:
    detail = {
        "status": status,
        "code": code,
        "course_code": course_code,
        "latency_ms": latency_ms,
        "usage": usage or {},
        "question_chars": question_chars,
    }
    if grounded is not None:
        detail["grounded"] = grounded
    db.add(AuditLog(
        actor_type="staff",
        actor_id=str(staff.id),
        action=action,
        entity_type="staff_learning",
        entity_id=entity_id,
        store_id=staff.store_id,
        detail=detail,
    ))


def _ai_unavailable(exc: LearningAIError):
    return error(exc.status_code, exc.code, exc.message)


@router.post("/coach")
def coach(
    body: LearningCoachIn,
    request: Request,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    staff, role = actor(authorization, db, request)
    if role != "technician":
        raise error(403, "LEARNING_COACH_FORBIDDEN", "AI 学习教练只对学习中的技师开放")
    if not settings.learning_ai_ready:
        raise error(503, "LEARNING_AI_DISABLED", "AI 学习教练暂未启用")
    item = db.scalar(select(StaffLearningAssignment).where(
        StaffLearningAssignment.id == body.assignment_id,
        StaffLearningAssignment.store_id == staff.store_id,
        StaffLearningAssignment.staff_id == staff.id,
    ))
    if item is None:
        raise error(404, "LEARNING_TASK_NOT_FOUND", "学习任务不存在或不属于当前身份")
    course = db.get(LearningCourseVersion, item.course_version_id)
    if not course or not available(course) or not applies_to_store(course.content, staff.store_id):
        raise error(409, "LEARNING_COURSE_UNAVAILABLE", "课程已停止新的学习操作")
    content = checked_content(course)
    section_ids = {section.get("id") for section in content.get("sections") or [] if isinstance(section, dict)}
    if body.section_id is not None and body.section_id not in section_ids:
        raise error(422, "LEARNING_SECTION_UNKNOWN", "章节不属于当前课程")
    if _ai_count(db, "learning_ai_coach", staff_id=staff.id) >= settings.learning_ai_coach_daily_limit:
        raise error(429, "LEARNING_AI_RATE_LIMITED", "今天的 AI 提问次数已用完，请明天再试")

    started = time.monotonic()
    try:
        reply = LearningAIProvider().chat(coach_messages(
            content.get("title") or course.code, content, body.section_id, body.question.strip(),
        ))
        parsed = parse_coach_reply(reply.content, content)
    except LearningAIError as exc:
        _ai_audit(
            db, staff, "learning_ai_coach", "error", entity_id=body.assignment_id, code=exc.code,
            course_code=course.code, latency_ms=int((time.monotonic() - started) * 1000),
            question_chars=len(body.question),
        )
        db.commit()
        raise _ai_unavailable(exc) from exc
    _ai_audit(
        db, staff, "learning_ai_coach", "success", entity_id=body.assignment_id,
        course_code=course.code, latency_ms=int((time.monotonic() - started) * 1000),
        usage=reply.usage, question_chars=len(body.question), grounded=parsed["grounded"],
    )
    db.commit()
    return {
        "answer": parsed["answer"],
        "citations": parsed["citations"],
        "grounded": parsed["grounded"],
        "usage": reply.usage,
    }


def _weekly_plan_payload(db, staff: Staff, lookback_days: int) -> dict:
    now = datetime.now(UTC)
    roster = list(db.scalars(roster_query(staff.store_id)))
    courses = assignable_courses(db.scalars(
        select(LearningCourseVersion).order_by(LearningCourseVersion.code, LearningCourseVersion.version)
    ), staff.store_id)
    if not roster or not courses:
        return {"roster": roster, "courses": courses, "payload": None}

    assignments = list(db.scalars(select(StaffLearningAssignment).where(
        StaffLearningAssignment.store_id == staff.store_id,
    )))
    assignment_ids = [item.id for item in assignments]
    events = list(db.scalars(select(StaffLearningEvent).where(
        StaffLearningEvent.store_id == staff.store_id,
        StaffLearningEvent.assignment_id.in_(assignment_ids),
    ).order_by(StaffLearningEvent.created_at, StaffLearningEvent.id))) if assignment_ids else []
    latest_submit: dict[str, StaffLearningEvent] = {}
    for event in events:
        if event.kind == "submit":
            latest_submit[event.assignment_id] = event
    assignment_by_staff: dict[int, list[StaffLearningAssignment]] = {}
    for item in assignments:
        assignment_by_staff.setdefault(item.staff_id, []).append(item)

    pending = pending_record_summary(db, staff.store_id, now)
    pending_by_technician = {
        row["technician_id"]: int(row["count"]) for row in pending.get("technicians") or []
    }
    since = now - timedelta(days=lookback_days)
    feedback_rows = list(db.scalars(select(ServiceFeedback).where(
        ServiceFeedback.store_id == staff.store_id,
        ServiceFeedback.rating <= 3,
        ServiceFeedback.created_at >= since,
    ).order_by(ServiceFeedback.created_at.desc()).limit(200)))
    tag_counts: dict[str, int] = {}
    for feedback in feedback_rows:
        for tag in feedback.tags or []:
            if isinstance(tag, str) and tag.strip():
                tag_counts[tag.strip()] = tag_counts.get(tag.strip(), 0) + 1

    course_by_id = {course.id: course for course in courses}
    technicians = []
    for member in roster:
        learning = []
        for item in assignment_by_staff.get(member.id, []):
            course = course_by_id.get(item.course_version_id)
            if course is None:
                continue
            latest = latest_submit.get(item.id)
            payload = latest.payload if latest is not None else {}
            correct = int(payload.get("correct") or 0)
            total = int(payload.get("total") or 0)
            learning.append({
                "course_id": course.code,
                "course_version": course.version,
                "sections_read": len(item.sections_read or []),
                "latest_correct": correct,
                "latest_total": total,
                "wrong_count": max(total - correct, 0),
            })
        technicians.append({
            "staff_id": member.id,
            "name": member.name,
            "learning": learning,
            "pending_record_count": pending_by_technician.get(member.technician_id, 0),
        })
    store = db.get(Store, staff.store_id)
    payload = {
        "store": {"id": staff.store_id, "name": store.name if store else ""},
        "courses": [
            {"course_id": course.code, "course_version": course.version,
             "title": course.content.get("title") or course.code,
             "category": course.content.get("category") or "", "minutes": course.content.get("minutes") or ""}
            for course in courses
        ],
        "technicians": technicians,
        "low_score_reviews": {
            "window_days": lookback_days,
            "count": len(feedback_rows),
            "tags": [{"tag": tag, "count": count} for tag, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:10]],
        },
    }
    return {"roster": roster, "courses": courses, "payload": payload}


@router.post("/weekly-plan")
def weekly_plan(
    body: LearningWeeklyPlanIn,
    request: Request,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    staff, role = actor(authorization, db, request)
    if role != "manager":
        raise error(403, "LEARNING_PLAN_FORBIDDEN", "只有店长可以生成周计划")
    if not settings.learning_ai_ready:
        raise error(503, "LEARNING_AI_DISABLED", "AI 周计划暂未启用")
    data = _weekly_plan_payload(db, staff, body.lookback_days)
    if not data["roster"] or not data["courses"] or data["payload"] is None:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "lookback_days": body.lookback_days,
            "suggestions": [],
            "data_basis": {"technicians": 0, "courses": len(data["courses"]), "low_score_reviews": 0},
            "disclaimer": "当前没有可安排的技师或课程，未调用 AI。",
        }
    if _ai_count(db, "learning_ai_weekly_plan", store_id=staff.store_id) >= settings.learning_ai_plan_daily_limit:
        raise error(429, "LEARNING_AI_RATE_LIMITED", "今天的周计划生成次数已用完，请明天再试")

    started = time.monotonic()
    try:
        reply = LearningAIProvider().chat(weekly_plan_messages(data["payload"]))
        suggestions = parse_weekly_plan_reply(reply.content)
    except LearningAIError as exc:
        _ai_audit(
            db, staff, "learning_ai_weekly_plan", "error", entity_id=str(staff.store_id), code=exc.code,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        db.commit()
        raise _ai_unavailable(exc) from exc

    roster_by_id = {member.id: member for member in data["roster"]}
    course_by_key = {(course.code, course.version): course for course in data["courses"]}
    validated = []
    seen = set()
    for suggestion in suggestions:
        member = roster_by_id.get(suggestion["staff_id"])
        course = course_by_key.get((suggestion["course_id"], suggestion["course_version"]))
        if member is None or course is None:
            continue
        key = (member.id, course.code, course.version)
        if key in seen:
            continue
        seen.add(key)
        validated.append({
            **suggestion,
            "staff_name": member.name,
            "title": course.content.get("title") or course.code,
            "priority": int(suggestion["priority"]),
        })
    if not validated and suggestions:
        _ai_audit(
            db, staff, "learning_ai_weekly_plan", "invalid", entity_id=str(staff.store_id),
            code="LEARNING_AI_INVALID_PLAN", latency_ms=int((time.monotonic() - started) * 1000),
        )
        db.commit()
        raise error(502, "LEARNING_AI_INVALID_PLAN", "AI 没有生成可用的周计划，请重试")
    _ai_audit(
        db, staff, "learning_ai_weekly_plan", "success", entity_id=str(staff.store_id),
        latency_ms=int((time.monotonic() - started) * 1000), usage=reply.usage,
    )
    db.commit()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "lookback_days": body.lookback_days,
        "suggestions": validated[:8],
        "data_basis": {
            "technicians": len(data["roster"]),
            "courses": len(data["courses"]),
            "low_score_reviews": data["payload"]["low_score_reviews"]["count"],
        },
        "disclaimer": "AI 生成草稿，请店长确认后再安排；不会自动分配。" if validated else "AI 未发现本周需要优先安排的课程。",
    }
