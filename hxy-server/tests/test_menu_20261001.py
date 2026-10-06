from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, Order, PriceBook, Project, SelectionSession, Staff, Store, User
from app.seed import seed
from app.domain.confirmed_menu import MENU, contract_modules, menu_spec
from app.api.admin import create_staff_token
from scripts.apply_confirmed_menu import apply_menu, plan_menu, authorize, states


@pytest.fixture
def catalog():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions() as db:
        seed(db)
        store = db.scalar(select(Store))
        staff = Staff(username="menu-manager", name="Test", role="manager", store_id=store.id,
                      status="active", password_hash="not-used")
        db.add_all([staff, Staff(username="menu-headquarters", name="HQ", role="admin", store_id=None,
                                status="active", password_hash="not-used")])
        db.commit()
        staff_id, store_id = staff.id, store.id

    def override():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, sessions, staff_id, store_id
    app.dependency_overrides.clear()
    engine.dispose()


def test_catalog_exposes_included_services_and_package_unit_from_database(catalog):
    client, sessions, _, _ = catalog
    with sessions() as db:
        spa = db.scalar(select(Project).where(Project.code == "hxy-spa-60"))
        row = next(row for row in MENU if row[0] == spa.code)
        spa.detail_modules = contract_modules(spa.detail_modules, menu_spec(row))
        db.commit()
        identifier = spa.id
    response = client.get(f"/api/v1/projects/{identifier}")
    assert response.status_code == 200
    assert response.json()["service_spec"]["included_services"] == [
        {"code": "hxy-qiqing-30", "name": "现煮草本泡", "quantity": 1}]


def headquarters(db):
    return db.scalar(select(Staff).where(Staff.username == "menu-headquarters"))


def install(catalog):
    _, sessions, staff_id, store_id = catalog
    with sessions.begin() as db:
        plan = plan_menu(db, store_id)
        result = apply_menu(db, store_id, headquarters(db), plan["plan_sha256"])
    return result


def test_menu_prices_ids_blank_package_prices_and_idempotency(catalog):
    client, sessions, staff_id, store_id = catalog
    with sessions() as db:
        ids = {project.code: project.id for project in db.scalars(select(Project))}
        before = states(db, store_id)
        preview = plan_menu(db, store_id)
        assert [change["code"] for change in preview["changes"]] == sorted(change["code"] for change in preview["changes"])
        assert states(db, store_id) == before
        assert db.scalar(select(AuditLog)) is None
    result = install(catalog)
    listing = client.get(f"/api/v1/projects?store_id={store_id}").json()["items"]
    assert [project["code"] for project in listing] == [row[0] for row in MENU]
    for row, project in zip(MENU, listing):
        assert project["id"] == ids.get(row[0], project["id"])
        assert (project["name"], project["duration_min"]) == (row[1], row[3])
        assert {price["price_type"]: price["amount_cents"] for price in project["prices"]} == {
            key: value for key, value in zip(("store", "group", "member"), row[4]) if value is not None}
    package = next(project for project in listing if project["code"] == "hxy-taoke-60")
    assert package["prices"] == [{"price_type": "store", "amount_cents": 98000}]
    assert (package["service_spec"]["sale_unit"], package["service_spec"]["services_per_unit"],
            package["service_spec"]["service_duration_min"]) == ("package", 10, 60)
    with sessions.begin() as db:
        repeated = apply_menu(db, store_id, headquarters(db), "stale-but-already-applied")
        assert repeated["changed"] == 0
        assert len(db.scalars(select(AuditLog)).all()) == 1
        assert db.get(Project, ids["hxy-baguan-1"]).independently_visible
        assert db.get(Project, ids["hxy-guasha-1"]).independently_visible
        assert db.get(Project, ids["hxy-oil-back-30"]).publication_status == "archived"
        assert db.get(Project, ids["hxy-cupping-scraping-1"]).publication_status == "archived"
        old_package_price = db.scalar(select(PriceBook).where(PriceBook.project_id == package["id"], PriceBook.price_type == "member"))
        assert old_package_price.amount_cents == 98000 and old_package_price.effective_to is not None
    assert result["audit_id"]


def test_real_http_confirmation_includes_gift_but_does_not_discount_paid_foot_bath(catalog):
    client, sessions, staff_id, store_id = catalog
    install(catalog)
    listing = client.get(f"/api/v1/projects?store_id={store_id}").json()["items"]
    ids = {item["code"]: item["id"] for item in listing}
    created = client.post("/api/v1/selection-sessions", json={"store_id": store_id, "source": "personal_qr"}).json()
    key, access = created["session"]["id"], created["access_token"]
    body = {"items": [{"project_id": ids["hxy-spa-60"]}, {"project_id": ids["hxy-qiqing-30"]}]}
    quoted = client.post(f"/api/v1/selection-sessions/{key}/quote", json=body, headers={"X-Selection-Token": access})
    assert quoted.status_code == 200, quoted.text
    assert quoted.json()["pricing"]["payable_total_cents"] == 15890
    submitted = client.post(f"/api/v1/selection-sessions/{key}/revisions", json=body,
                            headers={"X-Selection-Token": access, "Idempotency-Key": "new-menu-gift"})
    assert submitted.status_code == 200, submitted.text
    confirmed = client.post(f"/api/v1/admin/v2/selection-sessions/{key}/confirm",
                            headers={"Authorization": "Bearer " + create_staff_token(staff_id, "manager")})
    assert confirmed.status_code == 200, confirmed.text
    with sessions() as db:
        session = db.get(SelectionSession, key)
        frozen_items, frozen_prices = session.items, session.pricing_snapshot
        assert len(frozen_items) == 2
        assert frozen_items[0]["service_spec"]["included_services"][0]["quantity"] == 1
        assert frozen_prices["payable_total_cents"] == 15890
        spa = db.get(Project, ids["hxy-spa-60"])
        spa.detail_modules = []
        db.commit()
    retry = client.post(f"/api/v1/admin/v2/selection-sessions/{key}/confirm",
                        headers={"Authorization": "Bearer " + create_staff_token(staff_id, "manager")})
    assert retry.status_code == 200
    with sessions() as db:
        session = db.get(SelectionSession, key)
        assert session.items == frozen_items and session.pricing_snapshot == frozen_prices


def test_stale_preview_permissions_and_compensation_preserve_history(catalog):
    _, sessions, staff_id, store_id = catalog
    with sessions.begin() as db:
        before = states(db, store_id)
        plan = plan_menu(db, store_id)
        db.add(User(id=9876, openid="menu-history"))
        db.flush()
        db.add(Order(order_no="menu-history", order_type="service", user_id=9876, store_id=store_id,
                     status="completed", pay_amount_cents=1990, items=[{"project_id": 1, "price_cents": 1990}]))
        db.add(Staff(username="menu-other", name="Other", role="staff", store_id=store_id, password_hash="not-used"))
    with sessions.begin() as db:
        ordinary = db.scalar(select(Staff).where(Staff.username == "menu-other"))
        with pytest.raises(ValueError, match="headquarters"):
            apply_menu(db, store_id, ordinary, plan["plan_sha256"])
        db.scalar(select(Project).where(Project.code == "hxy-tuina-70")).summary = "newly changed"
    with sessions.begin() as db:
        with pytest.raises(ValueError, match="preview changed"):
            apply_menu(db, store_id, headquarters(db), plan["plan_sha256"])
        assert db.scalar(select(AuditLog)) is None
        db.scalar(select(Project).where(Project.code == "hxy-tuina-70")).summary = before["hxy-tuina-70"]["fields"]["summary"]
    result = install(catalog)
    with sessions.begin() as db:
        rollback = plan_menu(db, store_id, rollback_audit=result["audit_id"])
        apply_menu(db, store_id, headquarters(db), rollback["plan_sha256"], rollback_audit=result["audit_id"])
        order = db.scalar(select(Order).where(Order.order_no == "menu-history"))
        assert (order.status, order.pay_amount_cents, order.items) == ("completed", 1990, [{"project_id": 1, "price_cents": 1990}])
        for code, old in before.items():
            current = states(db, store_id)[code]
            assert current["id"] == old["id"] and current["fields"] == old["fields"] and current["prices"] == old["prices"]
        assert apply_menu(db, store_id, headquarters(db), "replay", rollback_audit=result["audit_id"])["changed"] == 0


def test_authenticated_tool_scope_and_legacy_catalog_metadata(catalog):
    client, sessions, staff_id, store_id = catalog
    with sessions() as db:
        operator = headquarters(db)
        assert authorize(db, create_staff_token(operator.id, "admin"), store_id).id == operator.id
        with pytest.raises(ValueError, match="headquarters"):
            authorize(db, create_staff_token(staff_id, "manager"), store_id)
        project = db.scalar(select(Project).where(Project.code == "hxy-spa-60"))
        identifier = project.id
    assert client.get(f"/api/v1/projects/{identifier}").json()["service_spec"] is None


def test_basic_catalog_edit_preserves_controlled_service_spec(catalog):
    client, sessions, _, _ = catalog
    install(catalog)
    with sessions() as db:
        project = db.scalar(select(Project).where(Project.code == "hxy-spa-60"))
        identifier, operator_id = project.id, headquarters(db).id
    headers = {"Authorization": "Bearer " + create_staff_token(operator_id, "admin")}
    response = client.patch(f"/api/v1/admin/v2/projects/{identifier}", headers=headers,
                            json={"detail_modules": [{"type": "text", "title": "介绍", "body": "Updated image copy"}]})
    assert response.status_code == 200, response.text
    detail = client.get(f"/api/v1/projects/{identifier}").json()
    assert detail["service_spec"]["included_services"][0]["code"] == "hxy-qiqing-30"
    assert detail["detail_modules"] == [{"type": "text", "title": "介绍", "body": "Updated image copy"}]
    rejected = client.patch(f"/api/v1/admin/v2/projects/{identifier}", headers=headers,
                            json={"detail_modules": [{"type": "service_contract", "spec": {}}]})
    assert rejected.status_code == 422


def test_cli_apply_requires_verified_backup_before_database_access(monkeypatch, tmp_path):
    from scripts import apply_confirmed_menu as tool
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"isolated backup fixture")
    monkeypatch.setattr("sys.argv", ["tool", "--store-id", "1", "--store-code", "test", "--apply",
                                   "--expected-plan", "a" * 64, "--backup-file", str(backup), "--backup-sha256", "wrong"])
    monkeypatch.setattr(tool, "SessionLocal", lambda: pytest.fail("invalid backup must not access database"))
    with pytest.raises(SystemExit) as rejected:
        tool.main()
    assert rejected.value.code == 2


def test_real_http_package_remains_detail_only_with_whole_package_price(catalog):
    client, sessions, _, store_id = catalog
    install(catalog)
    with sessions() as db:
        identifier = db.scalar(select(Project.id).where(Project.code == "hxy-taoke-60"))
    created = client.post("/api/v1/selection-sessions", json={"store_id": store_id, "source": "personal_qr"}).json()
    response = client.post(f"/api/v1/selection-sessions/{created['session']['id']}/quote",
        headers={"X-Selection-Token": created["access_token"]},
        json={"items": [{"project_id": identifier, "quantity": 1}]})
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "DETAIL_ONLY_PROJECT"
    detail = client.get(f"/api/v1/projects/{identifier}").json()
    assert detail["prices"] == [{"price_type": "store", "amount_cents": 98000}]
    assert detail["service_spec"]["services_per_unit"] == 10


def test_compensation_rejects_later_edits_and_inactive_headquarters(catalog):
    _, sessions, _, store_id = catalog
    result = install(catalog)
    with sessions.begin() as db:
        project = db.scalar(select(Project).where(Project.code == "hxy-spa-60"))
        project.summary = "Later authorized catalog edit"
    with sessions() as db:
        before = states(db, store_id)
        with pytest.raises(ValueError, match="renewed review"):
            plan_menu(db, store_id, rollback_audit=result["audit_id"])
        operator = headquarters(db)
        operator.status = "disabled"
        with pytest.raises(ValueError, match="active staff"):
            apply_menu(db, store_id, operator, "unused")
        assert states(db, store_id) == before
