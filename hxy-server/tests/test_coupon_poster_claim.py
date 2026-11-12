from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import importlib.util
import os
from pathlib import Path
import time
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.api.admin import create_staff_token
from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.domain.coupon_redeem import create_poster_token
from app.main import app
from app.models import AuditLog, CouponPosterLink, CouponTemplate, Staff, Store, User, UserCoupon
from test_manager_coupons import coupons

PREFIX = "/api/v1/admin/v2/manager/coupons"
CLAIM = "/api/v1/coupons/claim-half-price"


def poster(client, headers, request_id=None):
    response = client.post(PREFIX + "/half-price/poster-link", headers=headers["manager"],
                           json={"request_id": request_id or str(uuid.uuid4())})
    assert response.status_code == 200, response.text
    return response.json()


def customer_headers(factory, user_id):
    with factory() as db:
        user = db.get(User, user_id)
        return {"Authorization": "Bearer " + create_access_token(str(user.id), user.openid, user.customer_login_version)}


def test_single_poster_login_ownership_replay_and_redemption(coupons):
    client, factory, ids, headers = coupons
    data = poster(client, headers)
    code = data["code"]
    assert code.startswith("p.")
    status = client.post("/api/v1/coupons/poster-status", json={"code": code})
    assert status.json() == {"state": "available", "validity_days": 60}
    assert client.post(CLAIM, json={"code": code}).status_code == 401
    guest = client.post("/api/v1/coupons/guest-claim", json={"code": code, "visitor_id": "new-browser-001"})
    assert guest.status_code == 401
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(UserCoupon)) == 0
        assert db.scalar(select(func.count()).select_from(User)) == 2
    first = client.post(CLAIM, headers=headers["customer"], json={"code": code})
    assert first.status_code == 200, first.text
    coupon_id = first.json()["coupon_id"]
    again = client.post(CLAIM, headers=headers["customer"], json={"code": code})
    assert again.json() == first.json()
    other = customer_headers(factory, ids["other_customer"])
    denied = client.post(CLAIM, headers=other, json={"code": code})
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "POSTER_ALREADY_CLAIMED"
    public = client.post("/api/v1/coupons/poster-status", json={"code": code}).json()
    assert public == {"state": "claimed"}
    assert client.post("/api/v1/coupons/poster-status", headers=other, json={"code": code}).json() == public
    owned = client.post("/api/v1/coupons/poster-status", headers=headers["customer"], json={"code": code}).json()
    assert owned["state"] == "owned" and owned["coupon"]["coupon_id"] == coupon_id
    assert client.post(f"/api/v1/coupons/{coupon_id}/redeem-token", headers=other).status_code == 404
    qr = client.post(f"/api/v1/coupons/{coupon_id}/redeem-token", headers=headers["customer"]).json()["token"]
    preview = client.post(PREFIX + "/validate", headers=headers["manager"], json={"token": qr})
    assert preview.json()["requires_holder_confirmation"] is True
    with factory() as db:
        assert db.get(UserCoupon, coupon_id).status == "unused"
    no_confirmation = client.post(PREFIX + "/redeem", headers=headers["manager"],
                                  json={"token": qr, "request_id": str(uuid.uuid4())})
    assert no_confirmation.status_code == 422
    wrong_store = client.post(PREFIX + "/redeem", headers=headers["other_manager"],
                              json={"token": qr, "request_id": str(uuid.uuid4()), "holder_present": True})
    assert wrong_store.status_code == 403
    redemption = {"token": qr, "request_id": str(uuid.uuid4()), "holder_present": True}
    assert client.post(PREFIX + "/redeem", headers=headers["manager"], json=redemption).status_code == 200
    assert client.post(PREFIX + "/redeem", headers=headers["manager"], json=redemption).status_code == 409
    assert client.post(PREFIX + "/validate", headers=headers["manager"], json={"token": qr}).status_code == 409
    assert client.post(CLAIM, headers=headers["customer"], json={"code": code}).json()["status"] == "used"
    assert client.post(CLAIM, headers=other, json={"code": code}).status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(UserCoupon)) == 1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "customer_claim_poster_coupon")) == 1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "manager_redeem_coupon")) == 1


def test_poster_creation_idempotency_permissions_and_legacy_unchanged(coupons):
    client, factory, ids, headers = coupons
    old = client.post(PREFIX + "/half-price/issue", headers=headers["manager"], json={"user_id": ids["customer"]}).json()
    request_id = str(uuid.uuid4())
    first, second = poster(client, headers, request_id), poster(client, headers, request_id)
    assert first == second
    third = poster(client, headers)
    assert third["code"] != first["code"]
    assert client.post(PREFIX + "/half-price/poster-link", headers=headers["customer"], json={"request_id": request_id}).status_code in (401, 403)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CouponPosterLink)) == 2
        assert db.scalar(select(func.count()).select_from(UserCoupon)) == 1
        original = db.get(UserCoupon, old["coupon_id"])
        assert original.user_id == ids["customer"] and original.status == old["status"]
        assert original.expire_at.isoformat()[:19] == old["expire_at"][:19]


@pytest.mark.parametrize("invalid", ["expired", "tampered", "wrong-store", "unpublished"])
def test_unavailable_or_invalid_poster_never_issues(coupons, invalid):
    client, factory, ids, headers = coupons
    data = poster(client, headers)
    code = data["code"]
    with factory() as db:
        link = db.get(CouponPosterLink, data["poster_id"])
        if invalid == "expired":
            link.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif invalid == "unpublished":
            db.get(CouponTemplate, link.template_id).status = "archived"
        elif invalid == "wrong-store":
            code = create_poster_token(link.id, ids["other_store"], datetime.now(UTC) + timedelta(days=1))
        else:
            code = code[:-1] + ("x" if code[-1] != "x" else "y")
        db.commit()
    assert client.post(CLAIM, headers=headers["customer"], json={"code": code}).status_code in (400, 404)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(UserCoupon)) == 0
        assert db.get(CouponPosterLink, data["poster_id"]).coupon_id is None


def test_phone_verification_and_activity_capacity(coupons):
    client, factory, ids, headers = coupons
    data = poster(client, headers)
    with factory() as db:
        user = db.get(User, ids["customer"])
        user.phone = ""
        db.commit()
    denied = client.post(CLAIM, headers=headers["customer"], json={"code": data["code"]})
    assert denied.status_code == 401
    with factory() as db:
        user = db.get(User, ids["customer"])
        user.phone = "13800138000"
        link = db.get(CouponPosterLink, data["poster_id"])
        db.add_all([UserCoupon(user_id=ids["other_customer"], template_id=link.template_id, status="used") for _ in range(100)])
        db.commit()
    assert client.post(CLAIM, headers=headers["customer"], json={"code": data["code"]}).json()["detail"]["code"] == "COUPON_SOLD_OUT"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(UserCoupon)) == 100
        assert db.get(CouponPosterLink, data["poster_id"]).coupon_id is None


def test_postgres_two_claimants_and_duplicate_creation():
    value = os.getenv("HXY_TEST_POSTGRES_URL")
    if not value:
        pytest.skip("Isolated PostgreSQL URL required")
    parsed = make_url(value)
    assert parsed.host in {"localhost", "127.0.0.1"}
    assert parsed.database.startswith("hxy_coupon_concurrency_")
    engine = create_engine(value)
    factory = sessionmaker(engine, expire_on_commit=False)
    # Apply the actual additive migration on an isolated database.
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name != "coupon_poster_links"])
    spec = importlib.util.spec_from_file_location("poster_migration", Path(__file__).parents[1] / "alembic/versions/20261112_coupon_poster_links.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
    with factory.begin() as db:
        store = Store(store_code="isolated-poster", name="Synthetic", address="Synthetic")
        db.add(store); db.flush()
        staff = Staff(username="poster-manager", name="Manager", password_hash="unused", role="manager", store_id=store.id)
        users = [User(openid=f"poster-{i}", phone=f"1380000000{i}") for i in range(2)]
        db.add_all([staff, *users]); db.flush()
        headers = {"manager": {"Authorization": "Bearer " + create_staff_token(staff.id, staff.role)}}
        customer_tokens = [{"Authorization": "Bearer " + create_access_token(str(u.id), u.openid)} for u in users]
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            request_id = str(uuid.uuid4())
            with ThreadPoolExecutor(2) as pool:
                creations = list(pool.map(lambda _: poster(client, headers, request_id), range(2)))
            assert creations[0]["poster_id"] == creations[1]["poster_id"]
            data = creations[0]
            with factory() as blocker:
                link = blocker.get(CouponPosterLink, data["poster_id"])
                blocker.execute(select(CouponTemplate).where(CouponTemplate.id == link.template_id).with_for_update())
                blocker_pid = blocker.scalar(text("SELECT pg_backend_pid()"))
                with ThreadPoolExecutor(2) as pool:
                    futures = [pool.submit(client.post, CLAIM, headers=h, json={"code": data["code"]}) for h in customer_tokens]
                    deadline = time.monotonic() + 10
                    blocked = 0
                    while time.monotonic() < deadline:
                        with engine.connect() as observer:
                            blocked = observer.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND pid <> :pid AND wait_event_type = 'Lock' AND query LIKE '%coupon_templates%'"), {"pid": blocker_pid})
                        if blocked >= 2: break
                        time.sleep(.05)
                    blocker.commit()
                    results = [future.result(timeout=15) for future in futures]
                assert blocked >= 2, "Both actual ASGI requests must overlap under the template lock"
            assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
            with factory() as db:
                assert db.scalar(select(func.count()).select_from(UserCoupon)) == 1
                assert db.scalar(select(func.count()).select_from(CouponPosterLink)) == 1
                assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "customer_claim_poster_coupon")) == 1
            winner = next(i for i, result in enumerate(results) if result.status_code == 200)
            coupon_id = results[winner].json()["coupon_id"]
            qr = client.post(f"/api/v1/coupons/{coupon_id}/redeem-token", headers=customer_tokens[winner]).json()["token"]
            with factory() as blocker:
                blocker.execute(select(UserCoupon).where(UserCoupon.id == coupon_id).with_for_update())
                with ThreadPoolExecutor(2) as pool:
                    futures = [pool.submit(client.post, PREFIX + "/redeem", headers=headers["manager"], json={
                        "token": qr, "request_id": str(uuid.uuid4()), "holder_present": True,
                    }) for _ in range(2)]
                    deadline = time.monotonic() + 10
                    blocked = 0
                    while time.monotonic() < deadline:
                        with engine.connect() as observer:
                            blocked = observer.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock' AND query LIKE 'UPDATE user_coupons%'"))
                        if blocked >= 2: break
                        time.sleep(.05)
                    blocker.commit()
                    redeemed = [future.result(timeout=15) for future in futures]
                assert blocked >= 2, "Both redemption requests must overlap"
            assert sorted(r.status_code for r in redeemed) == [200, 409], [r.text for r in redeemed]
            with factory() as db:
                assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "manager_redeem_coupon")) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_new_phone_customer_can_redeem_only_their_store_poster(coupons):
    client, factory, ids, headers = coupons
    data = poster(client, headers)
    sent = client.post("/api/v1/auth/h5/send-code", json={"phone": "13700137000"})
    assert sent.status_code == 200, sent.text
    login = client.post("/api/v1/auth/h5/login", json={"phone": "13700137000", "code": sent.json()["debug_code"]})
    assert login.status_code == 200, login.text
    customer = {"Authorization": "Bearer " + login.json()["token"]}
    claimed = client.post(CLAIM, headers=customer, json={"code": data["code"]})
    assert claimed.status_code == 200, claimed.text
    coupon_id = claimed.json()["coupon_id"]
    qr = client.post(f"/api/v1/coupons/{coupon_id}/redeem-token", headers=customer).json()["token"]
    preview = client.post(PREFIX + "/validate", headers=headers["manager"], json={"token": qr})
    assert preview.status_code == 200, preview.text
    assert preview.json()["requires_holder_confirmation"] is True
    assert client.post(PREFIX + "/validate", headers=headers["other_manager"], json={"token": qr}).status_code == 403
    assert client.post(PREFIX + "/redeem", headers=headers["manager"], json={"token": qr, "request_id": str(uuid.uuid4()), "holder_present": True}).status_code == 200
    assert client.post(PREFIX + "/validate", headers=headers["manager"], json={"token": qr}).status_code == 409


def test_new_poster_never_rewrites_existing_campaign(coupons):
    client, factory, ids, headers = coupons
    original = poster(client, headers)
    with factory() as db:
        link = db.get(CouponPosterLink, original["poster_id"])
        template_id = link.template_id
        db.get(CouponTemplate, template_id).validity_days = 30
        db.commit()
    rejected = client.post(PREFIX + "/half-price/poster-link", headers=headers["manager"], json={"request_id": str(uuid.uuid4())})
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "COUPON_CONFIG_MISMATCH"
    with factory() as db:
        assert db.get(CouponTemplate, template_id).validity_days == 30
        assert db.scalar(select(func.count()).select_from(CouponPosterLink)) == 1
