from datetime import UTC, datetime, timedelta
import csv
import io
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
from app.models.membership import MembershipCard

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


def test_membership_overview_is_read_only_and_marks_unknown_sync(coupon_admin):
    client, factory, ids, headers = coupon_admin
    with factory.begin() as db:
        db.add(MembershipCard(user_id=ids["customer"], store_id=ids["store"], source="synthetic",
                              source_card_key="synthetic-card-1", card_type="annual",
                              started_at=datetime.now(UTC) - timedelta(days=1),
                              expires_at=datetime.now(UTC) + timedelta(days=300), status="active"))
    response = client.get(f"{PREFIX}/v2/membership/overview", headers=headers["manager"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cards"]["active"] == 1
    assert body["sync_status"]["state"] == "receipt_available_paused"
    assert "暂缓" in body["sync_status"]["label"]
    assert body["receipt"]["last_success"]["new_cards"] == 3
    assert body["receipt"]["latest_attempt"]["status"] == "blocked"
    assert "全手机号" not in str(body)
    assert client.get(f"{PREFIX}/v2/membership/overview?store_id={ids['other_store']}", headers=headers["manager"]).status_code == 403


def test_coupon_reports_support_beijing_natural_day_without_changing_utc_days(coupon_admin):
    client, factory, ids, headers = coupon_admin
    created = create(client, headers["admin"], code="contract-date-boundary", name="边界券", amount_cents=100, status="published")
    template_id = created.json()["data"]["id"]
    with factory.begin() as db:
        # 2026-11-11T15:59Z is 2026-11-11 23:59 Beijing; 16:01Z is 2026-11-12 00:01 Beijing.
        before = UserCoupon(user_id=ids["customer"], template_id=template_id, status="unused",
                            claimed_at=datetime(2026, 11, 11, 15, 59, tzinfo=UTC),
                            expire_at=datetime(2027, 1, 11, tzinfo=UTC))
        after = UserCoupon(user_id=ids["customer"], template_id=template_id, status="used",
                           claimed_at=datetime(2026, 11, 11, 16, 1, tzinfo=UTC),
                           expire_at=datetime(2027, 1, 11, tzinfo=UTC))
        db.add_all([before, after]); db.flush()
        db.add_all([
            AuditLog(actor_type="staff", actor_id=str(ids["admin"]), store_id=ids["store"],
                     action="manager_redeem_coupon", entity_type="user_coupon", entity_id=str(before.id),
                     created_at=datetime(2026, 11, 11, 15, 59, tzinfo=UTC), detail={}),
            AuditLog(actor_type="staff", actor_id=str(ids["admin"]), store_id=ids["store"],
                     action="manager_redeem_coupon", entity_type="user_coupon", entity_id=str(after.id),
                     created_at=datetime(2026, 11, 11, 16, 1, tzinfo=UTC), detail={}),
        ])
    day = client.get(f"{PREFIX}/v2/coupons/overview?start_date=2026-11-12&end_date=2026-11-12", headers=headers["admin"])
    assert day.status_code == 200, day.text
    period = day.json()["period"]
    assert period["mode"] == "asia_shanghai_natural_day"
    assert period["timezone"] == "Asia/Shanghai"
    assert period["issued"] == 1
    assert period["redeemed_events"] == 1
    rolling = client.get(f"{PREFIX}/v2/coupons/overview?days=30", headers=headers["admin"]).json()["period"]
    assert rolling["mode"] == "utc_rolling_days"
    incomplete = client.get(f"{PREFIX}/v2/coupons/overview?start_date=2026-11-12", headers=headers["admin"])
    assert incomplete.status_code == 422
    redemptions = client.get(f"{PREFIX}/v2/coupons/redemptions?start_date=2026-11-12&end_date=2026-11-12", headers=headers["admin"])
    assert redemptions.status_code == 200, redemptions.text
    assert redemptions.json()["total"] == 1
    assert redemptions.json()["period"]["timezone"] == "Asia/Shanghai"


def test_coupon_csv_export_protects_formulas_and_preserves_filters(coupon_admin):
    client, factory, ids, headers = coupon_admin
    formulas = ["=1+1", "+1+1", "-1+1", "@SUM(1,1)", " =1+1", "\t=1+1", "\r=1+1", "\n=1+1"]
    normal_name = '中文,含"引号"\n换行'
    template_ids = []
    for index, name in enumerate([*formulas, normal_name]):
        response = create(client, headers["admin"], code=f"csv-formula-{index}", name=name,
                          amount_cents=100, status="published")
        assert response.status_code == 200, response.text
        template_ids.append(response.json()["data"]["id"])

    # One template carries enough rows to exceed the normal 50-row page.
    bulk_id = template_ids[0]
    with factory.begin() as db:
        for index in range(55):
            db.add(UserCoupon(user_id=ids["customer"], template_id=bulk_id, status="unused",
                              claimed_at=datetime(2026, 11, 11, 16, 1, tzinfo=UTC),
                              expire_at=datetime(2027, 1, 11, tzinfo=UTC)))
        for index, name in enumerate([*formulas[1:], normal_name], start=1):
            db.add(UserCoupon(user_id=ids["customer"], template_id=template_ids[index], status="unused",
                              claimed_at=datetime(2026, 11, 11, 16, 1, tzinfo=UTC),
                              expire_at=datetime(2027, 1, 11, tzinfo=UTC)))
        # Customer display names are another allowed text field and must be protected too.
        formula_users = []
        for index, name in enumerate(formulas[:3]):
            user = User(openid=f"csv-formula-user-{index}", nickname=name, phone=f"1390013900{index}")
            formula_users.append(user)
        db.add_all(formula_users); db.flush()
        for user in formula_users:
            db.add(UserCoupon(user_id=user.id, template_id=template_ids[-1], status="unused",
                              claimed_at=datetime(2026, 11, 11, 16, 1, tzinfo=UTC),
                              expire_at=datetime(2027, 1, 11, tzinfo=UTC)))
        # A normal negative numeric ID must not be altered by formula protection.
        db.add(UserCoupon(user_id=ids["customer"], template_id=template_ids[-1], status="used",
                          claimed_at=datetime(2026, 11, 11, 16, 1, tzinfo=UTC),
                          expire_at=datetime(2027, 1, 11, tzinfo=UTC), used_order_id=-5))
    exported = client.get(f"{PREFIX}/v2/coupons/export?dataset=ledger&template_id={bulk_id}", headers=headers["admin"])
    assert exported.status_code == 200, exported.text
    rows = list(csv.reader(io.StringIO(exported.text.lstrip("\ufeff"))))
    assert len(rows) == 56
    assert all(len(row) == 9 for row in rows)
    # Template name cell is protected and still readable.
    assert all(row[1].startswith("'") for row in rows[1:])
    assert all(row[1] == "'" + formulas[0] for row in rows[1:])

    all_export = client.get(f"{PREFIX}/v2/coupons/export?dataset=ledger", headers=headers["admin"])
    all_rows = list(csv.reader(io.StringIO(all_export.text.lstrip("\ufeff"))))
    assert len(all_rows) >= 56 + len(formulas) + 1
    by_name = {row[1]: row for row in all_rows[1:]}
    for formula in formulas:
        assert ("'" + formula) in by_name
    assert normal_name in by_name
    assert any(row[2] == "'" + formulas[0] for row in all_rows[1:])
    assert any(row[2] == "'" + formulas[1] for row in all_rows[1:])
    assert any(row[2] == "'" + formulas[2] for row in all_rows[1:])
    # CSV parser returns the exact original Chinese, comma, quote and newline.
    assert by_name[normal_name][2] == "顾客甲"
    assert any(row[8] == "-5" for row in all_rows[1:])

    filtered = client.get(
        f"{PREFIX}/v2/coupons/export?dataset=ledger&template_id={bulk_id}&status=unused"
        f"&start_date=2026-11-12&end_date=2026-11-12", headers=headers["admin"])
    filtered_rows = list(csv.reader(io.StringIO(filtered.text.lstrip("\ufeff"))))
    assert len(filtered_rows) == 56
    assert filtered.status_code == 200

    with factory() as db:
        export_audit = db.scalar(select(AuditLog).where(AuditLog.action == "export_coupon_records").order_by(AuditLog.id.desc()))
        assert export_audit is not None
        assert export_audit.detail["row_count"] == len(filtered_rows) - 1
        assert export_audit.detail["phone_mode"] == "masked"
        assert export_audit.detail["period_mode"] == "asia_shanghai_natural_day"

    assert client.get(f"{PREFIX}/v2/coupons/export?dataset=ledger", headers=headers["employee"]).status_code == 403


def test_coupon_redemption_csv_uses_redemption_time_and_is_audited(coupon_admin):
    client, factory, ids, headers = coupon_admin
    created = create(client, headers["admin"], code="csv-redemption-time", name="核销导出券",
                     amount_cents=100, status="published")
    template_id = created.json()["data"]["id"]
    with factory.begin() as db:
        early = UserCoupon(user_id=ids["customer"], template_id=template_id, status="used",
                           claimed_at=datetime(2026, 10, 1, tzinfo=UTC),
                           expire_at=datetime(2026, 12, 1, tzinfo=UTC))
        late = UserCoupon(user_id=ids["customer"], template_id=template_id, status="used",
                          claimed_at=datetime(2026, 11, 11, 16, 1, tzinfo=UTC),
                          expire_at=datetime(2027, 1, 1, tzinfo=UTC))
        db.add_all([early, late]); db.flush()
        db.add_all([
            AuditLog(actor_type="staff", actor_id=str(ids["admin"]), store_id=ids["store"],
                     action="manager_redeem_coupon", entity_type="user_coupon", entity_id=str(early.id),
                     created_at=datetime(2026, 11, 11, 15, 59, tzinfo=UTC), detail={}),
            AuditLog(actor_type="staff", actor_id=str(ids["admin"]), store_id=ids["store"],
                     action="manager_redeem_coupon", entity_type="user_coupon", entity_id=str(late.id),
                     created_at=datetime(2026, 11, 11, 16, 1, tzinfo=UTC), detail={}),
        ])
    response = client.get(
        f"{PREFIX}/v2/coupons/export?dataset=redemptions&template_id={template_id}"
        f"&start_date=2026-11-12&end_date=2026-11-12", headers=headers["admin"])
    assert response.status_code == 200, response.text
    rows = list(csv.reader(io.StringIO(response.text.lstrip("\ufeff"))))
    assert len(rows) == 2
    assert len(rows[0]) == 7
    assert rows[1][2] == str(late.id)
    with factory() as db:
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "export_coupon_records").order_by(AuditLog.id.desc()))
        assert audit and audit.detail["dataset"] == "redemptions"
        assert audit.detail["row_count"] == 1
        assert audit.detail["period_mode"] == "asia_shanghai_natural_day"


def test_member_sync_receipts_endpoint_is_scoped_and_does_not_infer_sync(coupon_admin):
    client, factory, ids, headers = coupon_admin
    response = client.get(f"{PREFIX}/v2/member-sync/receipts", headers=headers["manager"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is True
    assert body["store_id"] == ids["store"]
    assert body["last_success"]["batch_id"] == "MEMBER-SYNC-ZHB-20261106-3CARDS"
    assert body["latest_attempt"]["status"] == "blocked"
    assert body["latest_attempt"]["applied"] is False
    assert body["latest_attempt"]["business_writes"] == 0
    assert body["current_effective_cards"] == 0
    assert body["last_success"]["manifest_sha256"]
    assert body["latest_attempt"]["source_keyset_sha256"]
    assert client.get(f"{PREFIX}/v2/member-sync/receipts", headers=headers["employee"]).status_code == 403
    other = client.get(f"{PREFIX}/v2/member-sync/receipts?store_id={ids['other_store']}", headers=headers["manager"])
    assert other.status_code == 403


def test_member_receipt_loader_honors_allowlist_integrity_and_conflicts(tmp_path):
    import json
    from hashlib import sha256
    from app.services.member_sync_receipts import load_member_sync_receipts

    def receipt(batch, status, when, cards=0):
        return {"receipt_version": 1, "receipt_id": batch.lower(), "batch_id": batch, "status": status,
                "store_id": 1, "successful_submit_at": when, "source_verified_at": when,
                "new_cards": cards, "new_users": cards, "applied": status == "success"}

    def put(name, data):
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        (tmp_path / name).write_bytes(raw)
        return {"file": name, "sha256": sha256(raw).hexdigest()}

    entries = []
    entries.append(put("success.json", receipt("B-SUCCESS", "success", "2026-11-05T16:11:43Z", 3)))
    entries.append(put("no-new.json", receipt("B-NO-NEW", "no_new", "2026-11-06T10:00:00Z", 0)))
    entries.append(put("blocked.json", receipt("B-BLOCKED", "blocked", "2026-11-13T02:45:12Z", 15)))
    (tmp_path / "index.json").write_text(json.dumps({"schema_version": 1, "receipts": entries}))
    result = load_member_sync_receipts(tmp_path, store_id=1)
    assert result["available"] is True
    assert result["last_success"]["batch_id"] == "B-SUCCESS"
    assert result["last_verification"]["batch_id"] == "B-NO-NEW"
    assert result["latest_attempt"]["batch_id"] == "B-BLOCKED"
    assert result["errors"] == [] and result["conflicts"] == []

    # Missing field is rejected, not filled with zero.
    bad = receipt("B-BAD", "success", "2026-11-07T00:00:00Z")
    bad.pop("batch_id")
    entries_bad = entries + [put("bad.json", bad)]
    (tmp_path / "index.json").write_text(json.dumps({"schema_version": 1, "receipts": entries_bad}))
    result = load_member_sync_receipts(tmp_path, store_id=1)
    assert any(item["code"] == "RECEIPT_FIELDS_MISSING" for item in result["errors"])

    # Digest mismatch is rejected.
    (tmp_path / "no-new.json").write_bytes(b"tampered")
    result = load_member_sync_receipts(tmp_path, store_id=1)
    assert any(item["code"] == "RECEIPT_SHA_MISMATCH" for item in result["errors"])

    # Same batch and same content is idempotent; different content conflicts.
    same = put("success-copy.json", receipt("B-SUCCESS", "success", "2026-11-05T16:11:43Z", 3))
    conflict = put("success-conflict.json", receipt("B-SUCCESS", "success", "2026-11-05T16:11:43Z", 99))
    (tmp_path / "index.json").write_text(json.dumps({"schema_version": 1, "receipts": [entries[0], same, conflict]}))
    result = load_member_sync_receipts(tmp_path, store_id=1)
    assert any(item["code"] == "RECEIPT_BATCH_CONFLICT" for item in result["conflicts"])
    assert len(result["receipts"]) == 0

    # Missing index is an explicit unavailable state, not "no data".
    empty = tmp_path / "empty"; empty.mkdir()
    assert load_member_sync_receipts(empty, store_id=1)["reason"] == "receipt_index_missing"


def _receipt_fixture(tmp_path, records, notes=None):
    import json
    from hashlib import sha256
    entries = []
    for name, data in records:
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        (tmp_path / name).write_bytes(raw)
        entries.append({"file": name, "sha256": sha256(raw).hexdigest()})
    note_entries = []
    for name, data in (notes or []):
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        (tmp_path / name).write_bytes(raw)
        note_entries.append({"file": name, "sha256": sha256(raw).hexdigest()})
    index = {"schema_version": 1, "receipts": entries}
    if note_entries:
        index["status_notes"] = note_entries
    (tmp_path / "index.json").write_text(json.dumps(index))
    return tmp_path


def _receipt(batch, status, when, cards, store=1, **extra):
    data = {"receipt_version": 1, "receipt_id": batch.lower(), "batch_id": batch,
            "status": status, "store_id": store, "source_verified_at": when,
            "new_cards": cards, "new_users": cards, "applied": status == "success"}
    if status == "success":
        data["successful_submit_at"] = when
    data.update(extra)
    return data


def test_member_receipt_store_selection_is_independent_and_scoped(coupon_admin, tmp_path):
    from app.services.member_sync_receipts import load_member_sync_receipts
    _receipt_fixture(tmp_path, [
        ("store1.json", _receipt("S1-OLD", "success", "2026-11-01T00:00:00Z", 3, store=1)),
        ("store2.json", _receipt("S2-NEW", "success", "2026-11-10T00:00:00Z", 7, store=2)),
    ])
    one = load_member_sync_receipts(tmp_path, store_id=1)
    two = load_member_sync_receipts(tmp_path, store_id=2)
    three = load_member_sync_receipts(tmp_path, store_id=3)
    assert one["last_success"]["batch_id"] == "S1-OLD"
    assert two["last_success"]["batch_id"] == "S2-NEW"
    assert one["conflicts"] == [] and two["conflicts"] == []
    assert three["available"] is False
    assert three["reason"] == "no_store_receipt"
    assert three["last_success"] is None


def test_member_receipt_no_new_and_blocked_do_not_replace_last_success(coupon_admin, tmp_path):
    from app.services.member_sync_receipts import load_member_sync_receipts
    _receipt_fixture(tmp_path, [
        ("success.json", _receipt("S-SUCCESS", "success", "2026-11-05T16:11:43Z", 3)),
        ("nonew.json", _receipt("S-NO-NEW", "no_new", "2026-11-06T10:00:00Z", 0)),
        ("blocked.json", _receipt("S-BLOCKED", "blocked", "2026-11-13T02:45:12Z", 15, blocked_reason="blocked_login_required")),
    ])
    result = load_member_sync_receipts(tmp_path, store_id=1)
    assert result["last_success"]["batch_id"] == "S-SUCCESS"
    assert result["last_success"]["successful_submit_at"] == "2026-11-05T16:11:43Z"
    assert result["last_verification"]["batch_id"] == "S-NO-NEW"
    assert result["latest_attempt"]["batch_id"] == "S-BLOCKED"
    # A no_new-only stream must not invent a successful submission.
    only = tmp_path / "only"; only.mkdir()
    _receipt_fixture(only, [("nonew.json", _receipt("ONLY-NO-NEW", "no_new", "2026-11-06T10:00:00Z", 0))])
    result_only = load_member_sync_receipts(only, store_id=1)
    assert result_only["last_success"] is None
    assert result_only["last_verification"]["batch_id"] == "ONLY-NO-NEW"


def test_member_receipt_conflict_is_untrusted_and_order_independent(coupon_admin, tmp_path):
    from app.services.member_sync_receipts import load_member_sync_receipts
    one = _receipt("C-CONFLICT", "success", "2026-11-05T16:11:43Z", 3)
    two = _receipt("C-CONFLICT", "success", "2026-11-05T16:11:43Z", 99)
    for order in ([("a.json", one), ("b.json", two)], [("b.json", two), ("a.json", one)]):
        case = tmp_path / ("case" + str(len(list(tmp_path.iterdir()))))
        case.mkdir(); _receipt_fixture(case, order)
        result = load_member_sync_receipts(case, store_id=1)
        assert result["has_conflict"] is True
        assert result["last_success"] is None
        assert result["available"] is False
        assert len(result["conflicts"]) == 1
    # An older trusted success remains visible while the newer conflict is flagged.
    mixed = tmp_path / "mixed"; mixed.mkdir()
    _receipt_fixture(mixed, [
        ("old.json", _receipt("C-OLD", "success", "2026-11-01T00:00:00Z", 2)),
        ("new-a.json", one), ("new-b.json", two),
    ])
    result = load_member_sync_receipts(mixed, store_id=1)
    assert result["available"] is True
    assert result["last_success"]["batch_id"] == "C-OLD"
    assert result["has_conflict"] is True


def test_member_receipt_status_note_is_separate_from_historical_blocked(coupon_admin, tmp_path):
    from app.services.member_sync_receipts import load_member_sync_receipts
    blocked = _receipt("B-BLOCKED", "blocked", "2026-11-13T02:45:12Z", 15,
                       blocked_reason="blocked_pending_exact_baseline_authorization",
                       source_keyset_sha256="keyset-1")
    note = {"note_version": 1, "note_id": "note-1", "batch_id": "B-BLOCKED", "store_id": 1,
            "source_keyset_sha256": "keyset-1", "current_status": "paused_by_user",
            "current_status_label": "已授权，用户要求暂缓", "authorization_status": "authorized_for_frozen_scope",
            "authorization_recorded_at": None, "time_status": "未记录",
            "authorization_scope": "original snapshot only", "not_import_authorization": True}
    _receipt_fixture(tmp_path, [("blocked.json", blocked)], [("note.json", note)])
    result = load_member_sync_receipts(tmp_path, store_id=1)
    attempt = result["latest_attempt"]
    assert attempt["status"] == "blocked"
    assert attempt["blocked_reason"] == "blocked_pending_exact_baseline_authorization"
    assert attempt["current_processing"]["current_status"] == "paused_by_user"
    assert attempt["current_processing"]["authorization_recorded_at"] is None
    assert attempt["current_processing"]["time_status"] == "未记录"


def test_member_receipt_route_scopes_conflicts_and_uses_latest_success(coupon_admin, monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services import member_sync_receipts
    _receipt_fixture(tmp_path, [
        ("s1-old.json", _receipt("S1-OLD", "success", "2026-11-01T00:00:00Z", 3, store=1)),
        ("s2-new.json", _receipt("S2-NEW", "success", "2026-11-10T00:00:00Z", 7, store=2)),
        ("s2-conflict-a.json", _receipt("S2-CONFLICT", "success", "2026-11-12T00:00:00Z", 1, store=2)),
        ("s2-conflict-b.json", _receipt("S2-CONFLICT", "success", "2026-11-12T00:00:00Z", 9, store=2)),
    ])
    monkeypatch.setattr(settings, "member_sync_receipt_dir", str(tmp_path))
    monkeypatch.setattr(member_sync_receipts.settings, "member_sync_receipt_dir", str(tmp_path))
    client, _, ids, headers = coupon_admin
    response = client.get(f"{PREFIX}/v2/member-sync/receipts", headers=headers["manager"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["last_success"]["batch_id"] == "S1-OLD"
    assert body["has_conflict"] is False
    assert "S2-CONFLICT" not in str(body)
    assert "s2-conflict" not in str(body)
    # The other store is still scoped out even though it has newer/conflicting receipts.
    other = client.get(f"{PREFIX}/v2/member-sync/receipts?store_id={ids['other_store']}", headers=headers["manager"])
    assert other.status_code == 403


def test_member_receipts_handle_shape_timezone_and_note_conflicts_without_500(coupon_admin, tmp_path):
    import json
    from hashlib import sha256
    from app.services.member_sync_receipts import load_member_sync_receipts

    shape = tmp_path / "shape"; shape.mkdir()
    raw = b"[]"; (shape / "array.json").write_bytes(raw)
    (shape / "index.json").write_text(json.dumps({"schema_version": 1, "receipts": [
        {"file": "array.json", "sha256": sha256(raw).hexdigest()},
    ]}))
    result = load_member_sync_receipts(shape, store_id=1)
    assert any(item["code"] == "RECEIPT_SHAPE_INVALID" for item in result["errors"])

    mixed = tmp_path / "mixed-time"; mixed.mkdir()
    _receipt_fixture(mixed, [
        ("aware.json", _receipt("M-AWARE", "success", "2026-11-05T16:11:43Z", 3)),
        ("naive.json", _receipt("M-NAIVE", "success", "2026-11-06T10:00:00", 4)),
    ])
    result = load_member_sync_receipts(mixed, store_id=1)
    assert result["last_success"]["batch_id"] == "M-AWARE"
    assert result["last_success"]["successful_submit_at"] == "2026-11-05T16:11:43Z"

    attempt_time = tmp_path / "attempt-time"; attempt_time.mkdir()
    _receipt_fixture(attempt_time, [
        ("b1.json", _receipt("B1", "blocked", "2026-11-01T00:00:00Z", 1, attempt_at="2026-11-13T00:00:00Z")),
        ("b2.json", _receipt("B2", "blocked", "2026-11-10T00:00:00Z", 2, attempt_at="2026-11-11T00:00:00Z")),
    ])
    result = load_member_sync_receipts(attempt_time, store_id=1)
    assert result["latest_attempt"]["batch_id"] == "B1"

    note_case = tmp_path / "note-conflict"; note_case.mkdir()
    blocked = _receipt("N-CONFLICT", "blocked", "2026-11-13T02:45:12Z", 15,
                       blocked_reason="blocked_login_required", source_keyset_sha256="keyset-1")
    note_a = {"note_version": 1, "note_id": "a", "batch_id": "N-CONFLICT", "store_id": 1,
              "source_keyset_sha256": "keyset-1", "current_status": "paused_by_user",
              "current_status_label": "paused", "authorization_recorded_at": None}
    note_b = {**note_a, "note_id": "b", "current_status": "authorized_pending_resume", "current_status_label": "authorized"}
    _receipt_fixture(note_case, [("blocked.json", blocked)], [("a.json", note_a), ("b.json", note_b)])
    result = load_member_sync_receipts(note_case, store_id=1)
    assert result["has_conflict"] is True
    assert result["latest_attempt"]["status"] == "blocked"
    assert "current_processing" not in result["latest_attempt"]
    assert any(item["code"] == "RECEIPT_NOTE_CONFLICT" for item in result["conflicts"])
