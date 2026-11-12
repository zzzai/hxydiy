from datetime import UTC, datetime, timedelta
import uuid

import pytest
from sqlalchemy import select

from app.domain.automatic_coupon import select_automatic_coupon
from app.models import AuditLog, CouponTemplate, PriceBook, Project, UserCoupon
from test_manager_coupons import coupons, PREFIX


def issue(client, ids, headers):
    response = client.post(PREFIX + "/half-price/issue", headers=headers["manager"], json={"user_id": ids["customer"]})
    assert response.status_code == 200, response.text
    return response.json()["coupon_id"]


def test_menu_scope_and_prices_do_not_rewrite_existing_records(coupons):
    client, factory, ids, headers = coupons
    coupon_id = issue(client, ids, headers)
    with factory() as db:
        coupon = db.get(UserCoupon, coupon_id)
        template = db.get(CouponTemplate, coupon.template_id)
        template.name = "半价券（全单5折）"
        for category, store, member in [("bath", 8900, 5900), ("care", 17900, 13900), ("small", 9900, 6900), ("balance", 18800, 15800), ("kit", 128000, 128000), ("local-strength", 7900, 4900)]:
            p = Project(store_id=ids["store"], code="scope-" + category, category=category, name=category, publication_status="published")
            db.add(p)
            db.flush()
            db.add_all([PriceBook(project_id=p.id, price_type="store", amount_cents=store), PriceBook(project_id=p.id, price_type="member", amount_cents=member)])
        db.commit()
        original_expiry = coupon.expire_at
    menu = client.get("/api/v1/projects", params={"store_id": ids["store"]}).json()["items"]
    prices = {p["category"]: p["half_price_coupon_price_cents"] for p in menu}
    assert prices == {"bath": 4450, "care": 8950, "small": None, "balance": None, "kit": None, "local-strength": None}
    mine = client.get("/api/v1/coupons", headers=headers["customer"]).json()["items"][0]
    assert mine["usage_scope"] == "foot_spa_main"
    assert mine["store_id"] == ids["store"]
    assert "痛症调理" in mine["scope_note"]
    assert "主项" in mine["name"]
    with factory() as db:
        coupon = db.get(UserCoupon, coupon_id)
        assert db.get(CouponTemplate, coupon.template_id).name == "半价券（全单5折）"
        assert coupon.status == "unused" and coupon.expire_at == original_expiry


def test_scan_coupon_is_not_automatically_consumed_for_any_cart(coupons):
    client, factory, ids, headers = coupons
    coupon_id = issue(client, ids, headers)
    with factory() as db:
        result = select_automatic_coupon(db, customer_id=ids["customer"], pricing={"payable_total_cents": 18800, "member_total_cents": 15800})
        assert result.coupon_id is None
        assert result.payable_after_coupon_cents == 18800
        assert db.get(UserCoupon, coupon_id).status == "unused"


def test_scope_confirmation_is_required_and_audited(coupons):
    client, factory, ids, headers = coupons
    coupon_id = issue(client, ids, headers)
    token = client.post(f"/api/v1/coupons/{coupon_id}/redeem-token", headers=headers["customer"]).json()["token"]
    preview = client.post(PREFIX + "/validate", headers=headers["manager"], json={"token": token}).json()
    assert preview["requires_scope_confirmation"] is True
    assert "门店价" in preview["scope_note"]
    payload = {"token": token, "request_id": str(uuid.uuid4())}
    assert client.post(PREFIX + "/redeem", headers=headers["manager"], json=payload).status_code == 422
    assert client.post(PREFIX + "/redeem", headers=headers["manager"], json={**payload, "scope_confirmed": "true"}).status_code == 422
    with factory() as db:
        assert db.get(UserCoupon, coupon_id).status == "unused"
    assert client.post(PREFIX + "/redeem", headers=headers["manager"], json={**payload, "scope_confirmed": True}).status_code == 200
    assert client.post(PREFIX + "/redeem", headers=headers["manager"], json={**payload, "scope_confirmed": True}).status_code == 409
    with factory() as db:
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "manager_redeem_coupon"))
        assert audit.detail["scope_confirmed"] is True


def test_legacy_order_endpoint_cannot_spend_scan_voucher(coupons):
    client, factory, ids, headers = coupons
    coupon_id = issue(client, ids, headers)
    with factory() as db:
        project = Project(store_id=ids["store"], code="excluded-pain", category="balance", name="Pain care", publication_status="published")
        db.add(project)
        db.flush()
        db.add(PriceBook(project_id=project.id, price_type="store", amount_cents=18800))
        db.commit()
        project_id = project.id
    response = client.post("/api/v1/orders", headers=headers["customer"], json={"store_id": ids["store"], "items": [{"project_id": project_id}], "coupon_id": coupon_id})
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "COUPON_SCAN_REQUIRED"
    with factory() as db:
        assert db.get(UserCoupon, coupon_id).status == "unused"


def test_ordinary_coupons_keep_existing_member_floor(coupons):
    client, factory, ids, headers = coupons
    issue(client, ids, headers)
    with factory() as db:
        template = CouponTemplate(store_id=ids["store"], code="ordinary-voucher", name="Ordinary", coupon_type="fixed", amount_cents=5000, status="published")
        db.add(template)
        db.flush()
        coupon = UserCoupon(user_id=ids["customer"], template_id=template.id, status="unused", expire_at=datetime.now(UTC) + timedelta(days=1))
        db.add(coupon)
        db.flush()
        result = select_automatic_coupon(db, customer_id=ids["customer"], pricing={"payable_total_cents": 18800, "member_total_cents": 15800})
        assert result.coupon_id == coupon.id
        assert result.discount_cents == 3000 and result.payable_after_coupon_cents == 15800
