"""Behavior checks for the confirmed menu and immutable learning publication."""
import copy
import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import Base, get_db
from app.main import app
from app.domain.membership_pricing import PriceContext
from app.domain.selection_pricing import calculate_selection_pricing
from app.models import AuditLog, PriceBook, Project, Store
from app.models.staff_learning import LearningCourseVersion, StaffLearningAssignment, StaffLearningEvent
from scripts.reconcile_menu_20261101 import RETIRED, load_menu, reconcile_menu
from scripts.publish_staff_learning import reconcile_courses


@pytest.fixture
def db():
    url = os.getenv("MENU_RELEASE_TEST_DATABASE_URL")
    schema = "menu_release_" + uuid.uuid4().hex
    control = None
    if url:
        parsed = make_url(url)
        assert parsed.database == "learning_test" and parsed.host == "learning-postgres-v8"
        control = create_engine(url)
        with control.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Store(id=1, store_code="hxy-anyang-ziwei-001", name="Synthetic store", address="Synthetic"))
        db.add(Store(id=2, store_code="menu-other", name="Other synthetic", address="Synthetic"))
        db.flush()
        for row in load_menu()["items"]:
            if row["existing_code"]:
                db.add(Project(store_id=1, code=row["code"], name="Old name", category=row["project_category"],
                    publication_status="published", summary="Old summary", detail_modules=[], diy_options=[], tags=[]))
        for code in RETIRED:
            db.add(Project(store_id=1, code=code, name="Retired offering", category="bath",
                publication_status="published", detail_modules=[], diy_options=[], tags=[]))
        other = Project(store_id=2, code="other-menu", name="Other store menu", category="bath", publication_status="published")
        db.add(other); db.flush()
        for p in db.scalars(select(Project)):
            for kind, amount in [("store", 9900), ("member", 6900), ("group", 7900)]:
                db.add(PriceBook(project_id=p.id, price_type=kind, amount_cents=amount, version="old"))
        db.commit()
        yield db
    engine.dispose()
    if control is not None:
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()
    engine.dispose()


def test_menu_exact_preview_repeat_and_history(db):
    old = {p.id: (p.project_id, p.price_type, p.amount_cents, p.version) for p in db.scalars(select(PriceBook))}
    groups = {p.id: p.effective_to for p in db.scalars(select(PriceBook).where(PriceBook.price_type == "group"))}
    preview = reconcile_menu(db)
    assert preview["new_projects"] == 3
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
    with pytest.raises(ValueError, match="menu_preview_changed"):
        reconcile_menu(db, apply=True, expected_hash="wrong")
    db.rollback()
    reconcile_menu(db, apply=True, expected_hash=preview["preview_hash"]); db.commit()
    assert {p.id: (p.project_id, p.price_type, p.amount_cents, p.version) for p in db.scalars(select(PriceBook)) if p.id in old} == old
    assert {p.id: p.effective_to for p in db.scalars(select(PriceBook).where(PriceBook.price_type == "group"))} == groups
    assert db.scalar(select(Project).where(Project.code == "other-menu")).name == "Other store menu"
    assert all(db.scalar(select(Project).where(Project.code == code)).publication_status == "archived" for code in RETIRED)
    assert db.scalar(select(func.count()).select_from(Project).where(Project.store_id == 1, Project.publication_status == "published")) == 14
    replay = reconcile_menu(db)
    assert replay["project_changes"] == replay["price_changes"] == []
    reconcile_menu(db, apply=True, expected_hash=replay["preview_hash"]); db.commit()
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 1


def test_menu_drift_and_store_conflicts_stop(db):
    p = db.scalar(select(Project).where(Project.code == "hxy-xiangxiang-60"))
    preview = reconcile_menu(db)
    p.summary = "Another editor changed this"
    db.commit()
    with pytest.raises(ValueError, match="menu_preview_changed"):
        reconcile_menu(db, apply=True, expected_hash=preview["preview_hash"])
    db.rollback()
    p.store_id = 2; db.commit()
    with pytest.raises(ValueError, match="menu_project_store_conflict"):
        reconcile_menu(db)


def test_bundle_is_whole_package_and_cannot_be_submitted(db):
    preview = reconcile_menu(db)
    reconcile_menu(db, apply=True, expected_hash=preview["preview_hash"]); db.commit()
    kit = db.scalar(select(Project).where(Project.code == "hxy-waist-kit-10"))
    prices = list(db.scalars(select(PriceBook).where(PriceBook.project_id == kit.id)))
    assert [(p.price_type, p.amount_cents) for p in prices] == [("store", 128000)]
    assert kit.price_label == "10次/套"
    with pytest.raises(ValueError, match="unavailable"):
        calculate_selection_pricing(db, [{"project_id": kit.id, "quantity": 1, "item_type": "service", "chargeable": True}],
                                    price_context=PriceContext(is_member=False, store_id=1, confirmed_at=datetime.now(UTC), store_timezone="Asia/Shanghai"))


def test_courses_publish_replay_retire_preserves_content(db):
    preview = reconcile_courses(db)
    assert len(preview["changes"]) == 12
    with pytest.raises(ValueError, match="learning_preview_changed"):
        reconcile_courses(db, apply=True, expected_hash="wrong")
    db.rollback()
    reconcile_courses(db, apply=True, expected_hash=preview["preview_hash"]); db.commit()
    frozen = {c.id: (copy.deepcopy(c.content), c.content_sha256) for c in db.scalars(select(LearningCourseVersion))}
    assert reconcile_courses(db)["changes"] == []
    assert db.scalar(select(func.count()).select_from(StaffLearningAssignment)) == 0
    assert db.scalar(select(func.count()).select_from(StaffLearningEvent)) == 0
    retirement = reconcile_courses(db, retire=True)
    reconcile_courses(db, retire=True, apply=True, expected_hash=retirement["preview_hash"]); db.commit()
    assert {c.id: (c.content, c.content_sha256) for c in db.scalars(select(LearningCourseVersion))} == frozen
    assert all(c.status == "retired" for c in db.scalars(select(LearningCourseVersion)))
    with pytest.raises(ValueError, match="retired_version_cannot_be_republished"):
        reconcile_courses(db)


def test_course_content_conflict_is_not_overwritten(db):
    preview = reconcile_courses(db)
    reconcile_courses(db, apply=True, expected_hash=preview["preview_hash"]); db.commit()
    course = db.scalars(select(LearningCourseVersion)).first()
    course.content = dict(course.content, title="Changed outside controlled publisher")
    db.commit()
    with pytest.raises(ValueError, match="immutable_course_version_conflict"):
        reconcile_courses(db)


def test_real_catalog_routes_and_bundle_submission_guard(db):
    preview = reconcile_menu(db)
    reconcile_menu(db, apply=True, expected_hash=preview["preview_hash"])
    db.commit()
    def override():
        with Session(db.bind) as request_db:
            yield request_db
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/projects", params={"store_id": 1})
            assert response.status_code == 200
            items = response.json()["items"]
            assert len(items) == 14 and all(p["content_version"] == "menu-20261101" for p in items)
            expected = {p["code"]: p for p in load_menu()["items"]}
            for item in items:
                prices = {p["price_type"]: p["amount_cents"] for p in item["prices"]}
                source = expected[item["code"]]
                assert prices["store"] == (source["bundle_cents"] or source["store_cents"])
                if source["bundle_cents"] is None:
                    assert prices["member"] == source["member_cents"]
                else:
                    assert "member" not in prices
            other = client.get("/api/v1/projects?store_id=2").json()["items"]
            assert [p["code"] for p in other] == ["other-menu"]
            created = client.post("/api/v1/selection-sessions", json={"store_id": 1, "source": "personal_qr"})
            assert created.status_code == 200, created.text
            result = created.json()
            kit = next(p for p in items if p["code"] == "hxy-waist-kit-10")
            headers = {"X-Selection-Token": result["access_token"]}
            body = {"items": [{"project_id": kit["id"], "quantity": 1, "addon_ids": []}]}
            for action in ("quote", "submit"):
                rejected = client.post(f"/api/v1/selection-sessions/{result['session']['id']}/{action}", headers=headers, json=body)
                assert rejected.status_code == 400
                assert rejected.json()["detail"]["code"] == "DETAIL_ONLY_PROJECT"
            stored = client.get(f"/api/v1/selection-sessions/{result['session']['id']}", headers=headers).json()
            assert stored["status"] == "draft" and stored["items"] == []
    finally:
        app.dependency_overrides.pop(get_db, None)
