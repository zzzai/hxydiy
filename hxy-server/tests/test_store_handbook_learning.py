import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.api.staff_learning import _weekly_plan_payload, content_hash
from app.domain.learning_content import load_package
from app.models import Staff, Store
from app.models.staff_learning import LearningCourseVersion
from scripts.publish_staff_learning import DEFAULT_MANIFEST, reconcile_courses
from test_learning_daily import daily_action
from test_staff_learning_api import PREFIX, learning

HANDBOOK = DEFAULT_MANIFEST.with_name("store-handbook-20261119-manifest.json")
HERBAL = "menu-20261101-01"
OLD = "20261102-v1"
CURRENT = "20261119-v1.1"


def publish(db, manifest):
    preview = reconcile_courses(db, manifest)
    reconcile_courses(db, manifest, apply=True, expected_hash=preview["preview_hash"])
    db.commit()
    return preview


def test_handbook_daily_workflow_preserves_history_and_scope(learning):
    client, factory, ids, headers, *_ = learning
    def view(who):
        result = client.get(PREFIX + "/bootstrap", headers=headers[who])
        assert result.status_code == 200, result.text
        return result.json()

    def assign(learner, version, manager="manager"):
        today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        return client.post(PREFIX + "/assignments", headers=headers[manager], json={
            "staff_id": ids[learner], "course_id": HERBAL, "course_version": version,
            "learning_date": today, "due_time": "23:59", "request_id": str(uuid.uuid4())})

    def task(learner, version=CURRENT, who="manager"):
        return next(t for t in view(who)["dailyTasks"] if t["staffId"] == ids[learner] and t["courseVersion"] == version)

    def read_and_submit(version, course, answers):
        for section in course["sections"]:
            response = daily_action(learning, task("a", version, "a"), "mark_section", section_id=section["id"])
            assert response.status_code == 200, response.text
        response = daily_action(learning, task("a", version, "a"), "submit", answers=answers)
        assert response.status_code == 200, response.text

    with factory() as db:
        db.get(Store, 1).store_code = "hxy-anyang-ziwei-001"
        publish(db, DEFAULT_MANIFEST)
        prior = {c.id: (c.status, c.content_sha256, content_hash(c.content)) for c in db.scalars(select(LearningCourseVersion))}
    old = next(c for c in load_package(DEFAULT_MANIFEST)[1] if c["id"] == HERBAL)
    assert assign("a", OLD).status_code == 200
    read_and_submit(OLD, old, {q["id"]: q["answer"] for q in old["questions"]})
    history = task("a", OLD)
    assert history["dailyStatus"] == "completed"

    with factory() as db:
        preview = publish(db, HANDBOOK)
        assert len(preview["changes"]) == 8 and all(c["before"] is None for c in preview["changes"])
        assert reconcile_courses(db, HANDBOOK)["changes"] == []
        assert prior == {c.id: (c.status, c.content_sha256, content_hash(c.content))
                         for c in db.scalars(select(LearningCourseVersion).where(LearningCourseVersion.id.in_(prior)))}

    catalog = view("manager")
    offered = [c for c in catalog["assignableCourses"] if c["version"] == CURRENT]
    assert len(offered) == 8
    assert {"id": HERBAL, "version": OLD} not in catalog["assignableCourses"]
    other = view("other_manager")
    assert all(c["version"] != CURRENT for c in other["courses"])
    assert {"id": HERBAL, "version": OLD} in other["assignableCourses"]
    with factory() as db:
        for manager, expected in (("manager", 8), ("other_manager", 0)):
            plans = _weekly_plan_payload(db, db.get(Staff, ids[manager]), 7)["courses"]
            assert sum(c.version == CURRENT for c in plans) == expected
            overview = client.get("/api/v1/admin/v2/learning/overview", headers=headers[manager])
            assert overview.status_code == 200, overview.text
            assert sum(c["version"] == CURRENT for c in overview.json()["courses"]) == expected
    assert assign("other", CURRENT, "other_manager").status_code == 409
    assert assign("b", OLD).status_code == 409
    assert all(c["version"] != CURRENT for c in view("a")["courses"])
    assert assign("a", CURRENT).status_code == assign("b", CURRENT).status_code == 200

    current = next(c for c in load_package(HANDBOOK)[1] if c["id"] == HERBAL)
    shown = next(c for c in view("a")["courses"] if c["version"] == CURRENT)
    assert all(set(q) == {"id", "prompt", "choices"} for q in shown["questions"])
    correct = {q["id"]: q["answer"] for q in current["questions"]}
    wrong = {**correct, "v11-q25": (correct["v11-q25"] + 1) % 3}
    read_and_submit(CURRENT, current, wrong)
    a = task("a")
    assert a["dailyStatus"] == "needs_coaching" and task("b")["dailyStatus"] == "not_started"
    assert len(view("a")["dailyTasks"]) == 2 and len(view("b")["dailyTasks"]) == 1
    result = a["attempts"][0]
    misses = [r for r in result["review"] if result["answers"][r["questionId"]] != r["answer"]]
    assert [m["questionId"] for m in misses] == ["v11-q25"] and "第45分钟" in misses[0]["explanation"]
    assert daily_action(learning, a, "follow_up", who="manager", note="请重新摆四张时间卡").status_code == 200
    assert task("a", who="a")["dailyStatus"] == "needs_retry"
    assert daily_action(learning, task("a", who="a"), "submit", answers=correct).status_code == 200
    done = task("a")
    assert done["dailyStatus"] == "completed" and [r["correct"] for r in done["attempts"]] == [3, 4]
    assert done["followUps"][-1]["note"] == "请重新摆四张时间卡"
    assert history == task("a", OLD) and task("b")["attempts"] == []
