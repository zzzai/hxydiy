from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.catalog import get_project
from app.db.session import Base, get_db
from app.main import app
from app.models import Project
from app.seed import PROJECTS, seed


def _project(code: str):
    return next(item for item in PROJECTS if item[0] == code)


def test_final_menu_contains_confirmed_projects_and_prices():
    expected = {
        "hxy-qiqing-30": ("草本泡脚", 30, 3990, 2990, 2990),
        "hxy-xiangxiang-60": ("草本沐足", 60, 8900, 7900, 6900),
        "hxy-xiaoqi-90": ("招牌草本沐足", 90, 12900, 9900, 8900),
        "hxy-tuina-70": ("荷小推", 70, 9900, 7900, 6900),
        "hxy-spa-60": ("舒享精油 SPA", 60, 11900, 9900, 8900),
        "hxy-spa-90": ("深享精油 SPA", 90, 17900, 15900, 13900),
        "hxy-taoke-60": ("功夫调理", 60, None, None, 98000),
        "hxy-caier-30": ("采耳", 30, 8900, 6900, 5900),
        "hxy-baguan-1": ("拔罐", None, 5900, 3900, 2900),
        "hxy-guasha-1": ("刮痧", None, 5900, 3900, 2900),
        "hxy-head-30": ("头疗", 30, 7900, 5900, 4900),
        "hxy-jubu-30": ("局部推拿", 30, 7900, 5900, 4900),
        "hxy-foot-refine-1": ("足部精修", None, 6900, 3900, 3900),
        "hxy-oil-back-30": ("精油开背", 30, 9900, None, 6900),
        "hxy-cupping-scraping-1": ("拔罐/刮痧", None, 5900, None, 2900),
    }
    assert len(PROJECTS) == len(expected)
    for code, (name, duration, store, group, member) in expected.items():
        row = _project(code)
        assert row[3] == name
        assert row[4] == duration
        assert row[6:9] == (store, group, member)


def test_spa_60_uses_dedicated_project_visual():
    row = _project("hxy-spa-60")
    assert row[9] == "/assets/projects/hxy-spa-60.webp"
    assert row[9] != _project("hxy-spa-90")[9]


def test_final_menu_order_matches_spreadsheet_rows():
    assert [item[0] for item in PROJECTS] == [
        "hxy-qiqing-30",
        "hxy-xiangxiang-60",
        "hxy-xiaoqi-90",
        "hxy-tuina-70",
        "hxy-spa-60",
        "hxy-spa-90",
        "hxy-taoke-60",
        "hxy-head-30",
        "hxy-foot-refine-1",
        "hxy-oil-back-30",
        "hxy-caier-30",
        "hxy-jubu-30",
        "hxy-cupping-scraping-1",
        "hxy-baguan-1",
        "hxy-guasha-1",
    ]


def test_counted_addons_are_marked_without_service_minutes():
    assert _project("hxy-baguan-1")[4] is None
    assert _project("hxy-guasha-1")[4] is None
    assert _project("hxy-foot-refine-1")[4] is None
    assert _project("hxy-cupping-scraping-1")[4] is None


def test_combined_cupping_scraping_requires_one_free_care_choice():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed(db)
        project = db.scalar(select(Project).where(Project.code == "hxy-cupping-scraping-1"))
        detail = get_project(project.id, db)
        assert len(detail.option_groups) == 1
        group = detail.option_groups[0]
        assert group["selection_mode"] == "single"
        assert group["required"] is True
        assert {choice["name"] for choice in group["choices"]} == {"拔罐护理", "刮痧护理"}
        assert all(choice["charge_mode"] == "free" for choice in group["choices"])
    engine.dispose()


def test_combined_care_choice_is_required_and_snapshot_names_selected_method():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    with session_local() as db:
        seed(db)
        project = db.scalar(select(Project).where(Project.code == "hxy-cupping-scraping-1"))
        store_id, project_id = project.store_id, project.id

    def override_get_db():
        with session_local() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            catalog = client.get(f"/api/v1/projects/{project_id}").json()
            choice_id = next(choice["id"] for choice in catalog["option_groups"][0]["choices"]
                             if choice["name"] == "刮痧护理")
            created = client.post("/api/v1/selection-sessions", json={"store_id": store_id, "source": "personal_qr"})
            assert created.status_code == 200, created.text
            session_id = created.json()["session"]["id"]
            headers = {"X-Selection-Token": created.json()["access_token"], "Idempotency-Key": "aux-choice-test"}
            base = {"project_id": project_id, "catalog_version_id": catalog["catalog_version_id"]}
            missing = client.post(f"/api/v1/selection-sessions/{session_id}/revisions",
                                  headers=headers, json={"items": [base]})
            assert missing.status_code == 409, missing.text
            assert missing.json()["detail"]["code"] == "OPTION_GROUP_REQUIRED"
            selected = client.post(f"/api/v1/selection-sessions/{session_id}/revisions",
                                   headers=headers, json={"items": [{**base, "option_choice_ids": [choice_id]}]})
            assert selected.status_code == 200, selected.text
            item = selected.json()["snapshot"]["items"][0]
            assert item["catalog_selection"]["preference_snapshots"][0]["name"] == "刮痧护理"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
