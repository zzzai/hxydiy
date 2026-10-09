import pytest
import os
import uuid
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import make_url

from app.db.session import Base
from app.models import MemberPlan, Order, PriceBook, Project, Store, User
from app.seed import seed
from scripts.reconcile_menu_20261007 import reconcile_menu
from scripts.reconcile_member_plans_20261008 import reconcile_member_plans


@pytest.fixture
def db():
    url = os.getenv("HXY_MENU_TEST_POSTGRES_URL")
    control = None
    if url:
        if make_url(url).database != "menu_20261007_test":
            raise ValueError("isolated_menu_database_required")
        schema = "menu_test_" + uuid.uuid4().hex
        control = create_engine(url, isolation_level="AUTOCOMMIT")
        with control.connect() as connection:
            connection.execute(text(f"CREATE SCHEMA {schema}"))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        seed(db)
        db.add(Project(store_id=1, code="hxy-nvshen-60", name="Old", category="bath",
                       duration_min=60, publication_status="published"))
        db.add(MemberPlan(code="stored", name="Old stored", price_cents=50000,
                          benefits=["Old"], status="published"))
        db.commit()
        reconcile_member_plans(db, apply=True, expected_hash=reconcile_member_plans(db)["preview_hash"])
        db.commit()
        yield db
    engine.dispose()
    if control:
        with control.connect() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        control.dispose()


def rows(db, table):
    return list(db.execute(text(f"SELECT * FROM {table} ORDER BY id")))


def test_preview_is_readonly_and_apply_requires_exact_preview(db):
    before = {name: rows(db, name) for name in ["projects", "price_book", "member_plans"]}
    report = reconcile_menu(db)
    db.commit()
    assert report["changed_projects"] == 14
    assert {name: rows(db, name) for name in before} == before
    with pytest.raises(ValueError, match="preview_hash"):
        reconcile_menu(db, apply=True, expected_hash="invalid")
    db.rollback()
    assert rows(db, "price_book") == before["price_book"]


def test_menu_prices_units_and_flows_match_images(db):
    preview = reconcile_menu(db)
    reconcile_menu(db, apply=True, expected_hash=preview["preview_hash"])
    db.commit()
    from app.api.catalog import _current_project_prices
    expected = {
        "hxy-qiqing-30": ("现煮草本泡", None, 2990, 2590),
        "hxy-xiangxiang-60": ("精选草本泡", 60, 9900, 6900),
        "hxy-xiaoqi-90": ("招牌草本泡", 90, 12900, 8900),
        "hxy-nvshen-60": ("女神草本足护", None, 11900, 7900),
        "hxy-tuina-70": ("荷小推", 80, 12900, 8900),
        "hxy-spa-60": ("舒压SPA", 60, 12900, 8900),
        "hxy-spa-90": ("安神SPA", 90, 18900, 13900),
        "hxy-head-30": ("头疗", 30, 7900, 4900),
        "hxy-caier-30": ("采耳", None, 8900, 5900),
        "hxy-oil-back-30": ("精油开背", 30, 9900, 6900),
        "hxy-jubu-30": ("局部推拿", None, 7900, 4900),
        "hxy-foot-refine-1": ("足部精修", None, 6900, 3900),
        "hxy-cupping-scraping-1": ("拔罐/刮痧", None, 5900, 2900),
        "hxy-taoke-60": ("功夫调理", 60, None, 98000),
    }
    for code, (name, duration, store, member) in expected.items():
        project = db.scalar(select(Project).where(Project.code == code))
        prices = {p["price_type"]: p["amount_cents"] for p in _current_project_prices(db, project.id)}
        assert (project.name, project.duration_min, prices.get("store"), prices["member"]) == (name, duration, store, member)
    tuina = db.scalar(select(Project).where(Project.code == "hxy-tuina-70"))
    assert "60分钟" in tuina.summary and "艾灸20分钟" in tuina.summary
    assert "泡" not in tuina.summary
    selected = db.scalar(select(Project).where(Project.code == "hxy-xiangxiang-60"))
    assert "手臂及足底按摩" in selected.summary
    spa = db.scalar(select(Project).where(Project.code == "hxy-spa-90"))
    assert "精油SPA70分钟" in spa.summary and "砭石球背部温通10分钟" in spa.summary
    kit = db.scalar(select(Project).where(Project.code == "hxy-taoke-60"))
    assert kit.price_label == "10次/套"


def test_group_prices_old_orders_and_published_graphs_are_preserved(db):
    db.add(User(id=100, openid="synthetic-history"))
    db.add(Order(id=100, order_no="HISTORY", order_type="service", user_id=100, store_id=1,
                 items=[{"name": "Old", "unit_price_cents": 1}], status="completed"))
    db.commit()
    group_before = list(db.execute(text("SELECT * FROM price_book WHERE price_type='group' ORDER BY id")))
    preserved = {name: rows(db, name) for name in ["orders", "project_catalog_versions", "project_option_groups", "project_option_choices"]}
    project_before = {p.code: (p.id, p.image_url, p.current_published_version_id) for p in db.scalars(select(Project))}
    preview = reconcile_menu(db)
    reconcile_menu(db, apply=True, expected_hash=preview["preview_hash"])
    db.commit()
    assert list(db.execute(text("SELECT * FROM price_book WHERE price_type='group' ORDER BY id"))) == group_before
    assert {name: rows(db, name) for name in preserved} == preserved
    assert {p.code: (p.id, p.image_url, p.current_published_version_id) for p in db.scalars(select(Project))} == project_before
    second = reconcile_menu(db)
    assert second["changed_projects"] == second["prices_added"] == second["changed_plans"] == 0


def test_plan_copy_changes_no_membership_or_wallet_facts(db):
    before = {name: rows(db, name) for name in ["users", "membership_cards", "membership_benefit_grants", "recharges"]}
    monthly = db.scalar(select(MemberPlan).where(MemberPlan.code == "monthly"))
    old_monthly = (monthly.name, monthly.price_cents, list(monthly.benefits), monthly.status)
    preview = reconcile_menu(db)
    reconcile_menu(db, apply=True, expected_hash=preview["preview_hash"])
    db.commit()
    assert {name: rows(db, name) for name in before} == before
    assert (monthly.name, monthly.price_cents, monthly.benefits, monthly.status) == old_monthly
    annual = db.scalar(select(MemberPlan).where(MemberPlan.code == "annual"))
    stored = db.scalar(select(MemberPlan).where(MemberPlan.code == "stored"))
    assert (annual.price_cents, stored.price_cents) == (9900, 50000)
    assert any("任意主项" in value and "门店价" in value for value in annual.benefits)
    assert any("29.9" in value and "1盒" in value for value in stored.benefits)


def test_unknown_kit_store_price_stops_without_closing_it(db):
    kit = db.scalar(select(Project).where(Project.code == "hxy-taoke-60"))
    db.add(PriceBook(project_id=kit.id, price_type="store", amount_cents=128000))
    db.commit()
    with pytest.raises(ValueError, match="kit_store_price_conflict"):
        reconcile_menu(db)
    assert db.scalar(select(PriceBook).where(PriceBook.project_id == kit.id, PriceBook.price_type == "store")).effective_to is None


def test_missing_project_stops_without_creating_or_reusing_ids(db):
    female = db.scalar(select(Project).where(Project.code == "hxy-nvshen-60"))
    female.code = "other-code"
    db.commit()
    with pytest.raises(ValueError, match="menu_project_missing"):
        reconcile_menu(db)


def test_price_change_after_preview_refuses_stale_apply(db):
    preview = reconcile_menu(db)
    project = db.scalar(select(Project).where(Project.code == "hxy-qiqing-30"))
    db.add(PriceBook(project_id=project.id, price_type="store", amount_cents=1))
    db.commit()
    before = rows(db, "price_book")
    with pytest.raises(ValueError, match="preview_hash"):
        reconcile_menu(db, apply=True, expected_hash=preview["preview_hash"])
    db.rollback()
    assert rows(db, "price_book") == before


def test_custom_detail_stops_instead_of_publishing_conflicting_copy(db):
    project = db.scalar(select(Project).where(Project.code == "hxy-tuina-70"))
    project.detail_modules = [{"type": "text", "body": "Old promise"}]
    db.commit()
    with pytest.raises(ValueError, match="custom_detail"):
        reconcile_menu(db)
    assert project.name == "荷小推"


def test_public_detail_exposes_new_summary_units_and_member_only_kit(db):
    from fastapi.testclient import TestClient
    from app.db.session import get_db
    from app.main import app
    preview = reconcile_menu(db)
    reconcile_menu(db, apply=True, expected_hash=preview["preview_hash"])
    db.commit()
    def override():
        yield db
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            kit = db.scalar(select(Project).where(Project.code == "hxy-taoke-60"))
            response = client.get(f"/api/v1/projects/{kit.id}")
            assert response.status_code == 200
            body = response.json()
            assert body["price_label"] == "10次/套"
            assert body["prices"] == [{"price_type": "member", "amount_cents": 98000}]
            local = db.scalar(select(Project).where(Project.code == "hxy-jubu-30"))
            body = client.get(f"/api/v1/projects/{local.id}").json()
            assert body["duration_min"] is None and body["price_label"] == "次"
            assert "腰臀" in body["summary"]
    finally:
        app.dependency_overrides.clear()


def test_cli_apply_without_backup_or_hash_refuses_before_db(monkeypatch):
    from scripts.reconcile_menu_20261007 import main
    monkeypatch.setattr("sys.argv", ["reconcile_menu_20261007", "--apply"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_menu_refuses_membership_drift_without_rewriting_plans(db):
    annual = db.scalar(select(MemberPlan).where(MemberPlan.code == "annual"))
    annual.benefits = ["Changed independently"]
    db.commit()
    before = {name: rows(db, name) for name in ["projects", "price_book", "member_plans"]}
    preview = reconcile_menu(db)
    assert preview["changed_plans"] == 1
    with pytest.raises(ValueError, match="membership_plan_drift"):
        reconcile_menu(db, apply=True, expected_hash=preview["preview_hash"])
    db.rollback()
    assert {name: rows(db, name) for name in before} == before


def test_cli_apply_requires_actual_backup_sha(monkeypatch, tmp_path, capsys):
    from scripts.reconcile_menu_20261007 import main
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"synthetic-backup")
    monkeypatch.setattr("sys.argv", ["reconcile_menu_20261007", "--apply", "--expected-hash", "x",
                                   "--backup-reference", str(backup), "--backup-sha256", "0" * 64])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "backup SHA256 mismatch" in capsys.readouterr().err


def test_correctly_hashed_proof_file_is_not_a_database_dump(monkeypatch, tmp_path, capsys):
    import hashlib
    from scripts import reconcile_menu_20261007 as tool

    proof = tmp_path / "proof.txt"
    proof.write_bytes(b"backup verified")
    digest = hashlib.sha256(proof.read_bytes()).hexdigest()
    monkeypatch.setattr("sys.argv", ["reconcile_menu_20261007", "--apply", "--expected-hash", "x",
                                   "--backup-reference", str(proof), "--backup-sha256", digest])
    monkeypatch.setattr(tool, "SessionLocal", lambda: pytest.fail("proof file accepted as actual dump"))
    with pytest.raises(SystemExit) as error:
        tool.main()
    assert error.value.code == 2
    assert "PostgreSQL custom-format dump" in capsys.readouterr().err
