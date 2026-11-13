from datetime import UTC, datetime, timedelta
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, CouponPosterLink, CouponTemplate, Order, Staff, Store, User, UserCoupon

PREFIX = "/api/v1/admin"


@pytest.fixture
def coupon_admin():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        store = Store(store_code="coupon-contract", name="Contract store", address="Synthetic")
        other = Store(store_code="coupon-contract-other", name="Other store", address="Synthetic")
        db.add_all([store, other]); db.flush()
        admin = Staff(username="coupon-contract-admin", name="Admin", password_hash="unused", role="admin", store_id=store.id, status="active")
        manager = Staff(username="coupon-contract-manager", name="Manager", password_hash="unused", role="manager", store_id=store.id, status="active")
        employee = Staff(username="coupon-contract-employee", name="Employee", password_hash="unused", role="staff", store_id=store.id, status="active")
        customer = User(openid="coupon-contract-customer", nickname="顾客甲", phone="13800138000")
        db.add_all([admin, manager, employee, customer]); db.flush()
        db.add(Order(order_no="COUPON-CONTRACT-1", user_id=customer.id, store_id=store.id, order_type="service",
                     items=[], total_amount_cents=10000, pay_amount_cents=10000, status="paid", pay_status="paid"))
        db.commit()
        ids = {"store": store.id, "other_store": other.id, "admin": admin.id, "manager": manager.id,
               "employee": employee.id, "customer": customer.id}
        headers = {
            "admin": {"Authorization": "Bearer " + create_staff_token(admin.id, admin.role)},
            "manager": {"Authorization": "Bearer " + create_staff_token(manager.id, manager.role)},
            "employee": {"Authorization": "Bearer " + create_staff_token(employee.id, employee.role)},
        }
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, factory, ids, headers
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def create(client, headers, **overrides):
    payload = {
        "code": f"contract-{uuid.uuid4().hex[:12]}", "name": "合同券",
        "coupon_type": "fixed", "amount_cents": 500,
        "min_spend_cents": 1000, "validity_days": 30, "status": "draft",
        "request_id": str(uuid.uuid4()),
    }
    payload.update(overrides)
    return client.post(f"{PREFIX}/coupons", json=payload, headers=headers)


def test_percent_requires_ratio_and_audits_create(coupon_admin):
    client, factory, _, headers = coupon_admin
    missing = create(client, headers["admin"], coupon_type="percent", amount_cents=0, percent_off=None)
    assert missing.status_code == 422, missing.text
    assert missing.json()["detail"]["code"] == "COUPON_CONFIG_INVALID"
    assert any(item["field"] == "percent_off" for item in missing.json()["detail"]["fields"])

    created = create(client, headers["admin"], coupon_type="percent", amount_cents=0, percent_off=20)
    assert created.status_code == 200, created.text
    assert created.json()["data"]["percent_off"] == 20
    assert created.json()["data"]["coupon_type"] == "percent"
    with factory() as db:
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "coupon_template_create"))
        assert audit is not None
        assert audit.entity_id == str(created.json()["data"]["id"])
        assert audit.detail["request_id"]


def test_zero_budget_round_trips_and_is_not_unlimited(coupon_admin):
    client, factory, ids, headers = coupon_admin
    zero = create(client, headers["admin"], code="contract-zero-budget", name="零预算券", budget_cents=0, status="published")
    assert zero.status_code == 200, zero.text
    template_id = zero.json()["data"]["id"]
    listed = client.get(f"{PREFIX}/coupons", headers=headers["admin"]).json()["items"]
    row = next(item for item in listed if item["id"] == template_id)
    assert row["budget_cents"] == 0
    assert row["remaining_budget_cents"] == 0
    assert row["budget_usage_percent"] == 0.0

    issued = client.post(f"{PREFIX}/v2/coupons/{template_id}/issue", json={"user_id": ids["customer"]}, headers=headers["admin"])
    assert issued.status_code == 409, issued.text
    assert issued.json()["detail"]["code"] == "COUPON_BUDGET_EXHAUSTED"
    assert client.get(f"{PREFIX}/coupons", headers=headers["admin"]).json()["items"]


def test_invalid_status_and_update_are_rejected_without_partial_write(coupon_admin):
    client, factory, _, headers = coupon_admin
    invalid_status = create(client, headers["admin"], code="contract-invalid-status", status="deleted")
    assert invalid_status.status_code == 422, invalid_status.text
    invalid_percent = create(client, headers["admin"], coupon_type="percent", amount_cents=0, percent_off=0)
    assert invalid_percent.status_code == 422, invalid_percent.text

    created = create(client, headers["admin"], code="contract-audit-update", name="审计更新券")
    template_id = created.json()["data"]["id"]
    updated = client.post(f"{PREFIX}/coupons/{template_id}", headers=headers["admin"], json={"name": "改名后", "request_id": str(uuid.uuid4())})
    assert updated.status_code == 200, updated.text
    with factory() as db:
        audits = list(db.scalars(select(AuditLog).where(AuditLog.action == "coupon_template_update", AuditLog.entity_id == str(template_id))))
        assert len(audits) == 1
        assert audits[0].detail["changes"]["name"]["before"] == "审计更新券"
        assert audits[0].detail["changes"]["name"]["after"] == "改名后"
        assert "13800138000" not in str(audits[0].detail)


def test_manager_can_read_but_not_write_rules_and_employee_cannot_read(coupon_admin):
    client, _, _, headers = coupon_admin
    assert client.get(f"{PREFIX}/coupons", headers=headers["manager"]).status_code == 200
    denied = create(client, headers["manager"], code="manager-write-denied")
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"]["code"] == "MARKETING_ADMIN_REQUIRED"
    assert client.get(f"{PREFIX}/coupons", headers=headers["employee"]).status_code == 403


def test_coupon_ledger_paginates_and_effective_expiry_is_reported(coupon_admin):
    client, factory, ids, headers = coupon_admin
    created = create(client, headers["admin"], code="contract-page", name="分页券", amount_cents=100, budget_cents=None)
    template_id = created.json()["data"]["id"]
    now = datetime.now(UTC)
    with factory.begin() as db:
        for index in range(52):
            db.add(UserCoupon(
                user_id=ids["customer"], template_id=template_id,
                status="unused" if index < 51 else "used",
                claimed_at=now - timedelta(days=index % 5),
                expire_at=(now - timedelta(days=1)) if index == 0 else (now + timedelta(days=30)),
            ))
    first = client.get(f"{PREFIX}/v2/coupons/{template_id}/redemptions", headers=headers["admin"])
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["total"] == 52
    assert len(body["items"]) == 50
    second = client.get(f"{PREFIX}/v2/coupons/{template_id}/redemptions?page=2", headers=headers["admin"])
    assert len(second.json()["items"]) == 2
    expired = client.get(f"{PREFIX}/v2/coupons/{template_id}/redemptions?status=expired", headers=headers["admin"]).json()
    assert expired["total"] == 1
    assert expired["items"][0]["status"] == "expired"
    listed = next(item for item in client.get(f"{PREFIX}/coupons", headers=headers["admin"]).json()["items"] if item["id"] == template_id)
    assert listed["issued_count"] == 52
    assert listed["used_count"] == 1
    assert listed["expired_count"] == 1
    assert listed["unused_count"] == 50


def test_redemption_history_uses_real_redemption_time(coupon_admin):
    client, factory, ids, headers = coupon_admin
    created = create(client, headers["admin"], code=f"half-price-50-s{ids['store']}", name="历史券", coupon_type="percent", amount_cents=0, percent_off=50, status="published")
    template_id = created.json()["data"]["id"]
    with factory() as db:
        customer = db.get(User, ids["customer"])
        coupon = UserCoupon(user_id=customer.id, template_id=template_id, status="unused",
                            claimed_at=datetime.now(UTC) - timedelta(days=40),
                            expire_at=datetime.now(UTC) + timedelta(days=20))
        db.add(coupon); db.flush()
        db.add(AuditLog(actor_type="staff", actor_id=str(ids["admin"]), store_id=ids["store"],
                        action="manager_redeem_coupon", entity_type="user_coupon", entity_id=str(coupon.id),
                        detail={"coupon_id": coupon.id}))
        coupon.status = "used"
        db.commit()
    history = client.get(f"{PREFIX}/v2/manager/coupons/history?days=30", headers=headers["manager"])
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["summary"]["redeemed"] == 1
    assert any(item["kind"] == "redeemed" and item["coupon_id"] for item in body["items"])


def test_admin_operations_read_models_are_scoped_and_audited(coupon_admin):
    client, factory, ids, headers = coupon_admin
    created = create(client, headers["admin"], code="contract-ops", name="运营券", status="published")
    template_id = created.json()["data"]["id"]
    with factory() as db:
        coupon = UserCoupon(user_id=ids["customer"], template_id=template_id, status="unused",
                            claimed_at=datetime.now(UTC) - timedelta(days=1), expire_at=datetime.now(UTC) + timedelta(days=59))
        db.add(coupon); db.flush()
        db.add(CouponPosterLink(store_id=ids["store"], template_id=template_id, created_by_staff_id=ids["admin"],
                                request_id=str(uuid.uuid4()), expires_at=datetime.now(UTC) + timedelta(days=30), coupon_id=coupon.id))
        db.commit()
    overview = client.get(f"{PREFIX}/v2/coupons/overview", headers=headers["admin"])
    assert overview.status_code == 200, overview.text
    assert overview.json()["posters"]["claimed"] == 1
    posters = client.get(f"{PREFIX}/v2/coupons/posters", headers=headers["admin"])
    assert posters.status_code == 200, posters.text
    assert posters.json()["items"][0]["claimed"] is True
    poster_id = posters.json()["items"][0]["id"]
    link = client.get(f"{PREFIX}/v2/coupons/posters/{poster_id}/link", headers=headers["admin"])
    assert link.status_code == 200, link.text
    assert link.json()["link"].startswith("https://diy.hexiaoyue.com/")
    assert link.json()["poster_id"] == poster_id
    ledger = client.get(f"{PREFIX}/v2/coupons/ledger", headers=headers["admin"])
    assert ledger.status_code == 200, ledger.text
    assert ledger.json()["items"][0]["phone_masked"] == "138****8000"
    redemption = client.get(f"{PREFIX}/v2/coupons/redemptions", headers=headers["admin"])
    assert redemption.status_code == 200, redemption.text
    assert redemption.json()["total"] == 0
    exported = client.get(f"{PREFIX}/v2/coupons/export?dataset=ledger", headers=headers["admin"])
    assert exported.status_code == 200, exported.text
    assert "手机号(脱敏)" in exported.text
    assert "13800138000" not in exported.text
    assert "=" not in exported.text.splitlines()[1] if len(exported.text.splitlines()) > 1 else True
    with factory() as db:
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "export_coupon_records"))
        assert audit is not None and audit.detail["phone_mode"] == "masked"
    # A manager may read the same store, but another store's id is rejected.
    assert client.get(f"{PREFIX}/v2/coupons/overview", headers=headers["manager"]).status_code == 200
    other = client.get(f"{PREFIX}/v2/coupons/overview?store_id={ids['other_store']}", headers=headers["manager"])
    assert other.status_code == 403
