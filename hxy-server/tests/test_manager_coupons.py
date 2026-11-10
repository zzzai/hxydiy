import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token
from app.core.security import create_access_token
from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models import SelectionSession, Staff, Store, User, UserCoupon

PREFIX = "/api/v1/admin/v2/manager/coupons"


@pytest.fixture
def coupons():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        stores = [Store(store_code=f"coupon-{n}", name=f"Store {n}", address="Synthetic") for n in range(2)]
        db.add_all(stores)
        db.flush()
        manager = Staff(username="coupon-manager", name="Manager", password_hash="unused", role="manager", store_id=stores[0].id)
        other_manager = Staff(username="coupon-other", name="Other", password_hash="unused", role="manager", store_id=stores[1].id)
        customer = User(openid="coupon-customer", nickname="顾客甲", phone="13800138000")
        other_customer = User(openid="coupon-other-customer", nickname="顾客乙", phone="13900139000")
        db.add_all([manager, other_manager, customer, other_customer])
        db.flush()
        db.add(SelectionSession(id="coupon-selection", store_id=stores[0].id, customer_id=customer.id,
                                access_token_hash="synthetic", status="confirmed", items=[], diy_preferences={}))
        db.add(SelectionSession(id="coupon-other-selection", store_id=stores[1].id, customer_id=other_customer.id,
                                access_token_hash="synthetic", status="confirmed", items=[], diy_preferences={}))
        db.commit()
        ids = {"manager": manager.id, "other_manager": other_manager.id, "customer": customer.id,
               "other_customer": other_customer.id, "store": stores[0].id, "other_store": stores[1].id}
        headers = {
            "manager": {"Authorization": "Bearer " + create_staff_token(manager.id, manager.role)},
            "other_manager": {"Authorization": "Bearer " + create_staff_token(other_manager.id, other_manager.role)},
            "customer": {"Authorization": "Bearer " + create_access_token(str(customer.id), customer.openid)},
        }
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, factory, ids, headers
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def test_issue_scan_and_customer_invalidation(coupons):
    client, factory, ids, headers = coupons
    issued = client.post(PREFIX + "/half-price/issue", headers=headers["manager"], json={"user_id": ids["customer"]})
    assert issued.status_code == 200, issued.text
    body = issued.json()
    assert body["percent_off"] == 50
    assert body["status"] == "unused"
    coupon_id = body["coupon_id"]

    token_response = client.post(f"/api/v1/coupons/{coupon_id}/redeem-token", headers=headers["customer"])
    assert token_response.status_code == 200, token_response.text
    token = token_response.json()["token"]
    assert token_response.json()["expires_at"]

    preview = client.post(PREFIX + "/validate", headers=headers["manager"], json={"token": token})
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid"] is True
    assert preview.json()["phone_masked"] == "138****8000"

    redeemed = client.post(PREFIX + "/redeem", headers=headers["manager"],
                           json={"token": token, "request_id": str(uuid.uuid4())})
    assert redeemed.status_code == 200, redeemed.text
    assert redeemed.json()["status"] == "used"

    repeated = client.post(PREFIX + "/redeem", headers=headers["manager"],
                           json={"token": token, "request_id": str(uuid.uuid4())})
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["code"] == "COUPON_ALREADY_USED"

    mine = client.get("/api/v1/coupons", headers=headers["customer"])
    assert mine.status_code == 200
    assert mine.json()["items"][0]["status"] == "used"
    again = client.post(f"/api/v1/coupons/{coupon_id}/redeem-token", headers=headers["customer"])
    assert again.status_code == 409


def test_store_scope_and_one_unused_coupon(coupons):
    client, _, ids, headers = coupons
    first = client.post(PREFIX + "/half-price/issue", headers=headers["manager"], json={"user_id": ids["customer"]})
    assert first.status_code == 200
    second = client.post(PREFIX + "/half-price/issue", headers=headers["manager"], json={"user_id": ids["customer"]})
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "COUPON_CLAIM_LIMIT_REACHED"

    token = client.post(f"/api/v1/coupons/{first.json()['coupon_id']}/redeem-token", headers=headers["customer"]).json()["token"]
    denied = client.post(PREFIX + "/validate", headers=headers["other_manager"], json={"token": token})
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "COUPON_STORE_MISMATCH"


def test_issue_by_phone_creates_wechat_customer_without_order(coupons):
    client, factory, _, headers = coupons
    issued = client.post(PREFIX + "/half-price/issue-by-phone", headers=headers["manager"],
                         json={"phone": "13700137000", "name": "微信新客"})
    assert issued.status_code == 200, issued.text
    body = issued.json()
    assert body["created_customer"] is True
    assert body["customer_name"] == "微信新客"
    assert body["percent_off"] == 50
    with factory() as db:
        user = db.get(User, body["user_id"])
        assert user and user.phone == "13700137000"
        customer_token = create_access_token(str(user.id), user.openid, user.customer_login_version)
    mine = client.get("/api/v1/coupons", headers={"Authorization": f"Bearer {customer_token}"})
    assert mine.status_code == 200, mine.text
    assert [item["id"] for item in mine.json()["items"]] == [body["coupon_id"]]
    again = client.post(PREFIX + "/half-price/issue-by-phone", headers=headers["manager"],
                        json={"phone": "13700137000"})
    assert again.status_code == 409


def test_link_claim_needs_login_and_is_one_per_customer(coupons):
    client, _, _, headers = coupons
    link = client.post(PREFIX + "/half-price/link", headers=headers["manager"])
    assert link.status_code == 200, link.text
    body = link.json()
    assert body["limit"] == 100
    assert body["remaining"] == 100
    token = body["token"]

    unauthenticated = client.post("/api/v1/coupons/claim-half-price", json={"token": token})
    assert unauthenticated.status_code == 401
    claimed = client.post("/api/v1/coupons/claim-half-price", headers=headers["customer"], json={"token": token})
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["percent_off"] == 50
    again = client.post("/api/v1/coupons/claim-half-price", headers=headers["customer"], json={"token": token})
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "COUPON_ALREADY_HELD"


def test_guest_claim_shows_qr_before_login_and_binds_to_account(coupons):
    client, factory, _, headers = coupons
    link = client.post(PREFIX + "/half-price/link", headers=headers["manager"]).json()["token"]
    guest = client.post("/api/v1/coupons/guest-claim", json={"code": link, "visitor_id": "guest-visitor-001"})
    assert guest.status_code == 200, guest.text
    body = guest.json()
    assert body["status"] == "unused"
    assert body["guest_token"]
    qr = client.post("/api/v1/coupons/guest/redeem-token", json={"guest_token": body["guest_token"]})
    assert qr.status_code == 200, qr.text
    preview = client.post(PREFIX + "/validate", headers=headers["manager"], json={"token": qr.json()["token"]})
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid"] is True

    # A second browser guest coupon can be bound to the logged-in account.
    second = client.post("/api/v1/coupons/guest-claim", json={"code": link, "visitor_id": "guest-visitor-002"})
    assert second.status_code == 200, second.text
    bound = client.post("/api/v1/coupons/bind-guest", headers=headers["customer"], json={"guest_token": second.json()["guest_token"]})
    assert bound.status_code == 200, bound.text
    assert bound.json()["already_held"] is False
    mine = client.get("/api/v1/coupons", headers=headers["customer"])
    assert mine.status_code == 200
    assert [item["id"] for item in mine.json()["items"]] == [bound.json()["coupon_id"]]
    # A guest QR is redeemable by the store manager without a store relation.
    redeemed = client.post(PREFIX + "/redeem", headers=headers["manager"],
                           json={"token": qr.json()["token"], "request_id": str(uuid.uuid4())})
    assert redeemed.status_code == 200, redeemed.text
    assert redeemed.json()["status"] == "used"
