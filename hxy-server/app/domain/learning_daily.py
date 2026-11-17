"""Daily learning is projected from append-only events, never historical row rewrites."""
import re
from datetime import UTC, date, datetime, time, timedelta, timezone

SHANGHAI = timezone(timedelta(hours=8))


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def normalize_plan(learning_date, due_time, now):
    day = date.fromisoformat(str(learning_date))
    today = aware(now).astimezone(SHANGHAI).date()
    if not re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", due_time):
        raise ValueError("截止时间格式应为 HH:mm")
    deadline = datetime.combine(day, time.fromisoformat(due_time), SHANGHAI).astimezone(UTC)
    if not today <= day <= today + timedelta(days=30):
        raise ValueError("请选择今天起 30 天内的学习日期")
    if deadline <= aware(now):
        raise ValueError("截止时间必须晚于当前时间")
    return {"learning_date": day.isoformat(), "due_at": deadline.isoformat()}


def daily_projection(plan, events, section_ids, now):
    info = plan.payload["daily_plan"]
    history = sorted(
        (e for e in events if e.payload.get("daily_plan_id") == plan.id),
        key=lambda e: (e.assignment_revision, aware(e.created_at), e.id),
    )
    reads = list(dict.fromkeys(e.payload["sectionId"] for e in history if e.kind == "mark_section"))
    attempts = [{
        "id": e.id, **{k: v for k, v in e.payload.items() if k != "daily_plan_id"},
        "revision": e.assignment_revision, "createdAt": aware(e.created_at).isoformat(),
    } for e in history if e.kind == "submit"]
    followups = [{
        "id": e.id, "managerId": e.actor_id, "managerName": e.actor_name, "note": e.payload["note"],
        "revision": e.assignment_revision, "createdAt": aware(e.created_at).isoformat(),
    } for e in history if e.kind == "follow_up"]
    latest = attempts[-1] if attempts else None
    coaching = followups[-1] if followups else None
    status = "not_started"
    if reads:
        status = "ready" if all(s in reads for s in section_ids) else "in_progress"
    if latest:
        status = "completed" if latest["total"] > 0 and latest["correct"] == latest["total"] else "needs_coaching"
    if coaching and (not latest or coaching["revision"] > latest["revision"]):
        status = "needs_retry"
    if date.fromisoformat(info["learning_date"]) > aware(now).astimezone(SHANGHAI).date():
        status = "scheduled"
    due = datetime.fromisoformat(info["due_at"])
    return {
        "dailyPlanId": plan.id, "learningDate": info["learning_date"], "dueAt": info["due_at"],
        "assignedAt": aware(plan.created_at).isoformat(), "sectionsRead": reads, "attempts": attempts,
        "followUps": followups, "dailyStatus": status,
        "overdue": status != "completed" and aware(now) > due,
        "completedLate": status == "completed" and datetime.fromisoformat(latest["createdAt"]) > due,
    }
