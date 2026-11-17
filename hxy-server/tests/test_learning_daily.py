import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func

from app.domain.learning_daily import daily_projection, normalize_plan
from app.models.staff_learning import StaffLearningAssignment, StaffLearningEvent
from test_staff_learning_api import learning, COURSE, PREFIX, arrange, read_all, command

NOW = datetime(2026, 11, 17, 10, tzinfo=timezone.utc)


def test_shanghai_deadline_and_date_validation():
    plan = normalize_plan("2026-11-17", "23:59", NOW)
    assert plan == {"learning_date": "2026-11-17", "due_at": "2026-11-17T15:59:00+00:00"}
    for day, clock in [("2026-11-16", "23:59"), ("2026-12-18", "23:59"), ("2026-11-17", "17:59"), ("2026-11-17", "25:00")]:
        with pytest.raises(ValueError):
            normalize_plan(day, clock, NOW)
    with pytest.raises(ValueError):
        normalize_plan("2026-11-17", "23:59", datetime(2026, 11, 17, 16, tzinfo=timezone.utc))


def event(kind, revision, payload, at=NOW):
    return SimpleNamespace(id="event-" + str(revision), kind=kind, assignment_revision=revision,
                           payload=payload, actor_id=9, actor_name="Synthetic", created_at=at)


def test_projection_does_not_credit_old_attempts_and_requires_retry_after_coaching():
    plan = event("assign", 1, {"daily_plan": normalize_plan("2026-11-17", "23:59", NOW)})
    old = event("submit", 0, {"correct": 2, "total": 2, "answers": {}, "review": []})
    result = daily_projection(plan, [old], ["one", "two"], NOW)
    assert result["dailyStatus"] == "not_started" and result["attempts"] == []
    scoped = lambda payload: {**payload, "daily_plan_id": plan.id}
    read = event("mark_section", 2, scoped({"sectionId": "one"}))
    wrong = event("submit", 3, scoped({"correct": 1, "total": 2, "answers": {}, "review": []}))
    coach = event("follow_up", 4, scoped({"note": "Review the example"}))
    result = daily_projection(plan, [old, read, wrong, coach], ["one", "two"], NOW)
    assert result["dailyStatus"] == "needs_retry" and result["sectionsRead"] == ["one"]
    retried = event("submit", 5, scoped({"correct": 2, "total": 2, "answers": {}, "review": []}), NOW + timedelta(hours=7))
    result = daily_projection(plan, [old, read, wrong, coach, retried], ["one", "two"], NOW + timedelta(hours=8))
    assert result["dailyStatus"] == "completed" and result["completedLate"] is True
    assert len(result["attempts"]) == 2 and len(result["followUps"]) == 1


def schedule(data, day=None, clock="23:59", key=None, who="manager", learner="a"):
    client, _, ids, headers, *_ = data
    day = day or (datetime.now(timezone(timedelta(hours=8)))).date().isoformat()
    return client.post(PREFIX + "/assignments", headers=headers[who], json={
        "staff_id": ids[learner], "course_id": COURSE["id"], "course_version": COURSE["version"],
        "request_id": key or str(uuid.uuid4()), "learning_date": day, "due_time": clock})


def daily_action(data, task, kind, who="a", key=None, **payload):
    client, _, _, headers, *_ = data
    return client.post(PREFIX + "/assignments/" + task["assignmentId"] + "/actions", headers=headers[who],
        json={"kind": kind, "daily_plan_id": task["dailyPlanId"], "request_id": key or str(uuid.uuid4()),
              "expected_revision": task["revision"], **payload})


def task_from(response):
    assert response.status_code == 200, response.text
    return next(item for item in response.json()["dailyTasks"] if item.get("dailyPlanId"))


def test_daily_full_loop_and_no_old_event_mutation(learning):
    client, factory, ids, headers, *_ = learning
    old = read_all(learning)
    old = command(learning, old, "submit", answers={"q1": 1, "q2": 0}).json()["assignments"][0]
    with factory() as db:
        before = {row.id: (row.kind, row.payload.copy()) for row in db.scalars(select(StaffLearningEvent))}
    task = task_from(schedule(learning))
    assert task["attempts"] == [] and task["sectionsRead"] == [] and task["dailyStatus"] == "not_started"
    assert daily_action(learning, task, "submit", answers={"q1": 1, "q2": 0}).status_code == 422
    task = task_from(daily_action(learning, task, "mark_section", section_id="one"))
    task = task_from(daily_action(learning, task, "mark_section", section_id="two"))
    assert task["dailyStatus"] == "ready"
    request_id = str(uuid.uuid4())
    response = daily_action(learning, task, "submit", key=request_id, answers={"q1": 0, "q2": 0})
    saved = task_from(response)
    assert saved["dailyStatus"] == "needs_coaching" and saved["attempts"][-1]["correct"] == 1
    repeated = task_from(daily_action(learning, task, "submit", key=request_id, answers={"q1": 0, "q2": 0}))
    assert len(repeated["attempts"]) == 1
    assert daily_action(learning, task, "submit", key=request_id, answers={"q1": 1, "q2": 0}).status_code == 409
    saved = task_from(daily_action(learning, saved, "follow_up", who="manager", note="Review and practice again"))
    assert saved["dailyStatus"] == "needs_retry"
    saved = task_from(daily_action(learning, saved, "submit", answers={"q1": 1, "q2": 0}))
    assert saved["dailyStatus"] == "completed" and len(saved["attempts"]) == 2
    assert daily_action(learning, saved, "follow_up", who="manager", note="Cannot reopen a completed task").status_code == 409
    snapshot = client.get(PREFIX + "/bootstrap", headers=headers["a"]).json()
    assert any(item["id"] == old["id"] for item in snapshot["dailyTasks"])
    with factory() as db:
        after = {row.id: (row.kind, row.payload) for row in db.scalars(select(StaffLearningEvent))}
    assert all(after[key] == value for key, value in before.items())


def test_daily_duplicate_and_future_plans_are_separate(learning):
    key = str(uuid.uuid4())
    first = task_from(schedule(learning, key=key))
    assert task_from(schedule(learning, key=key))["id"] == first["id"]
    assert task_from(schedule(learning, who="manager2"))["id"] == first["id"]
    assert schedule(learning, clock="23:58").status_code == 409
    tomorrow = (datetime.now(timezone(timedelta(hours=8))) + timedelta(days=1)).date().isoformat()
    future_response = schedule(learning, day=tomorrow)
    assert future_response.status_code == 200, future_response.text
    tasks = future_response.json()["dailyTasks"]
    assert len(tasks) == 2 and len({task["dailyPlanId"] for task in tasks}) == 2
    future = next(task for task in tasks if task["learningDate"] == tomorrow)
    assert future["dailyStatus"] == "scheduled"
    assert daily_action(learning, future, "mark_section", section_id="one").status_code == 409


@pytest.mark.parametrize("who,kind,payload", [
    ("b", "mark_section", {"section_id": "one"}),
    ("other", "mark_section", {"section_id": "one"}),
    ("manager", "mark_section", {"section_id": "one"}),
    ("a", "follow_up", {"note": "No proxy"}),
    ("other_manager", "follow_up", {"note": "Wrong store"}),
])
def test_daily_permissions(learning, who, kind, payload):
    task = task_from(schedule(learning))
    assert daily_action(learning, task, kind, who=who, **payload).status_code in (403, 404)


def test_daily_scope_and_plan_belongs_to_task(learning):
    client, factory, ids, headers, *_ = learning
    first = task_from(schedule(learning))
    second = task_from(schedule(learning, learner="b"))
    other = next(task for task in client.get(PREFIX + "/bootstrap", headers=headers["manager"]).json()["dailyTasks"] if task["staffId"] == ids["b"])
    forged = {**first, "dailyPlanId": other["dailyPlanId"]}
    assert daily_action(learning, forged, "mark_section", section_id="one").status_code == 404
    assert client.get(PREFIX + "/bootstrap", headers=headers["other_manager"]).json()["dailyTasks"] == []
    assert schedule(learning, learner="other").status_code == 404
    assert schedule(learning, who="a").status_code == 403
    assert client.get(PREFIX + "/bootstrap?learning_date=2026-11-17", headers=headers["a"]).status_code == 422


def test_concurrent_same_day_assignment_creates_one_plan(learning):
    from concurrent.futures import ThreadPoolExecutor
    client, factory, ids, headers, _, postgres = learning
    if not postgres:
        pytest.skip("Row locking requires isolated PostgreSQL")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(schedule, learning, who=who) for who in ("manager", "manager2")]
        responses = [future.result() for future in futures]
    assert all(response.status_code == 200 for response in responses), [r.text for r in responses]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(StaffLearningAssignment)) == 1
        plans = [row for row in db.scalars(select(StaffLearningEvent)) if row.payload.get("daily_plan")]
        assert len(plans) == 1


def test_team_view_follows_daily_progress_instead_of_old_perfect_score(learning):
    from app.api.manager_daily import _team_view
    client, factory, ids, headers, *_ = learning
    old = read_all(learning)
    assert command(learning, old, "submit", answers={"q1": 1, "q2": 0}).status_code == 200
    task = task_from(schedule(learning))
    with factory() as db:
        row = next(r for r in _team_view(db, task["storeId"])["technicians"] if r["staff_id"] == ids["a"])
        assert row["complete"] is False
        assert row["progress"] == 0
        assert row["due_at"] == task["dueAt"]
    for section in ("one", "two"):
        task = task_from(daily_action(learning, task, "mark_section", section_id=section))
    task = task_from(daily_action(learning, task, "submit", answers={"q1": 0, "q2": 0}))
    task = task_from(daily_action(learning, task, "follow_up", who="manager", note="Practice again"))
    with factory() as db:
        row = next(r for r in _team_view(db, task["storeId"])["technicians"] if r["staff_id"] == ids["a"])
        assert row["progress"] == 100
        assert row["complete"] is False
    task = task_from(daily_action(learning, task, "submit", answers={"q1": 1, "q2": 0}))
    with factory() as db:
        row = next(r for r in _team_view(db, task["storeId"])["technicians"] if r["staff_id"] == ids["a"])
        assert row["complete"] is True


def test_stale_revision_and_invalid_daily_request_are_zero_write(learning):
    client, factory, ids, headers, *_ = learning
    task = task_from(schedule(learning))
    newer = task_from(daily_action(learning, task, "mark_section", section_id="one"))
    with factory() as db:
        before = db.scalar(select(func.count()).select_from(StaffLearningEvent))
    assert daily_action(learning, task, "mark_section", section_id="two").status_code == 409
    assert daily_action(learning, newer, "submit", answers={"q1": True, "q2": 0}).status_code == 422
    body = {"staff_id": ids["a"], "course_id": COURSE["id"], "course_version": COURSE["version"],
            "request_id": str(uuid.uuid4()), "due_time": "23:59"}
    assert client.post(PREFIX + "/assignments", headers=headers["manager"], json=body).status_code == 422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(StaffLearningEvent)) == before


def test_invalid_past_date_does_not_create_a_course_folder(learning):
    yesterday = (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=1)).date().isoformat()
    response = schedule(learning, day=yesterday)
    assert response.status_code == 422
    with learning[1]() as db:
        assert db.scalar(select(func.count()).select_from(StaffLearningAssignment)) == 0
        assert db.scalar(select(func.count()).select_from(StaffLearningEvent)) == 0
