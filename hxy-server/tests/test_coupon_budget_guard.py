import os
import queue
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import admin, admin_v2, auth, coupons, orders
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import Base
from app.models import CouponTemplate, Order, Staff, Store, User, UserCoupon


ENTRIES = ["admin", "claim", "share", "new_user", "invite"]


def make_case(engine):
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory.begin() as db:
        store = Store(store_code="budget-test", name="Budget test", address="Synthetic only", status="open")
        db.add(store)
        db.flush()
        staff = Staff(username="budget-manager", password_hash="unused", name="Manager",
                      role="manager", store_id=store.id, status="active")
        users = [User(openid=f"budget-user-{i}", membership_store_id=store.id) for i in range(3)]
        db.add_all([staff, *users])
        db.flush()
        for i, user in enumerate(users):
            db.add(Order(order_no=f"BUDGET-{i}", user_id=user.id, store_id=store.id,
                         order_type="service", status="paid", pay_status="paid"))
        template = CouponTemplate(
            store_id=store.id, code=coupons.SHARE_COUPON_CODE, name="Budget test",
            coupon_type="fixed", amount_cents=500, budget_cents=500,
            is_claimable=True, auto_grant_new_user=True, claim_limit=10, status="published",
        )
        db.add(template)
        db.flush()
        return SimpleNamespace(
            factory=factory, store_id=store.id, template_id=template.id,
            user_ids=[u.id for u in users], staff_id=staff.id,
            authorization=f"Bearer {admin.create_staff_token(staff.id, staff.role)}",
        )


@pytest.fixture
def case(monkeypatch):
    monkeypatch.setattr(settings, "coupon_issuance_enabled", True)
    monkeypatch.setattr(orders, "INVITE_REWARD_CODE", coupons.SHARE_COUPON_CODE)
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    try:
        yield make_case(engine)
    finally:
        engine.dispose()


def issue(entry, case, user_id, db):
    authorization = f"Bearer {create_access_token(str(user_id), 'synthetic')}"
    if entry == "admin":
        return admin_v2.issue_coupon_to_customer(
            case.template_id, admin_v2.IssueCouponIn(user_id=user_id),
            store_id=None, db=db, authorization=case.authorization,
        )
    if entry == "claim":
        return coupons.claim_coupon(coupons.ClaimRequest(template_id=case.template_id),
                                    authorization=authorization, db=db)
    if entry == "share":
        return coupons.claim_share_coupon(authorization=authorization, db=db)
    if entry == "update":
        return admin.admin_update_coupon(
            case.template_id, admin.CouponTemplateUpdate(amount_cents=100),
            store_id=None, authorization=case.authorization, db=db,
        )
    if entry == "new_user":
        auth.grant_new_user_coupons(db, user_id)
        db.commit()
        return None
    result = orders._grant_inviter_reward(db, user_id)
    db.commit()
    return result


def count(case):
    with case.factory() as db:
        return db.scalar(select(func.count()).select_from(UserCoupon))


def update(case, **values):
    with case.factory() as db:
        return admin.admin_update_coupon(
            case.template_id, admin.CouponTemplateUpdate(**values),
            store_id=None, authorization=case.authorization, db=db,
        )


@pytest.mark.parametrize("entry", ENTRIES)
def test_all_issuance_entries_obey_same_budget(case, entry):
    with case.factory() as db:
        issue(entry, case, case.user_ids[0], db)
    assert count(case) == 1
    with case.factory() as db:
        if entry in {"admin", "claim"}:
            with pytest.raises(HTTPException) as error:
                issue(entry, case, case.user_ids[1], db)
            assert error.value.status_code == 409
            assert error.value.detail["code"] == "COUPON_BUDGET_EXHAUSTED"
        else:
            result = issue(entry, case, case.user_ids[1], db)
            if entry == "share":
                assert result["granted"] is False
            if entry == "invite":
                assert result is False
    assert count(case) == 1


@pytest.mark.parametrize("entry", ENTRIES)
def test_null_budget_preserves_unlimited_issuance(case, entry):
    update(case, budget_cents=None)
    for user_id in case.user_ids:
        with case.factory() as db:
            issue(entry, case, user_id, db)
    assert count(case) == 3


@pytest.mark.parametrize("status", ["unused", "locked", "used", "expired"])
def test_all_existing_statuses_keep_budget_committed(case, status):
    with case.factory.begin() as db:
        db.add(UserCoupon(user_id=case.user_ids[0], template_id=case.template_id, status=status))
    with case.factory() as db, pytest.raises(HTTPException) as error:
        issue("claim", case, case.user_ids[1], db)
    assert error.value.detail["code"] == "COUPON_BUDGET_EXHAUSTED"
    assert count(case) == 1


@pytest.mark.parametrize("field,value", [("amount_cents", 100), ("coupon_type", "percent")])
@pytest.mark.parametrize("old_budget,new_budget", [(500, 500), (None, 500), (500, None)])
def test_issued_budgeted_template_cannot_rewrite_face_value(case, field, value, old_budget, new_budget):
    update(case, budget_cents=old_budget)
    with case.factory() as db:
        issue("admin", case, case.user_ids[0], db)
    with pytest.raises(HTTPException) as error:
        update(case, budget_cents=new_budget, **{field: value})
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "COUPON_ISSUED_VALUE_IMMUTABLE"
    with case.factory() as db:
        template = db.get(CouponTemplate, case.template_id)
        assert template.amount_cents == 500
        assert template.coupon_type == "fixed"
        assert template.budget_cents == old_budget


def test_same_value_update_and_lower_budget_preserve_existing_coupon(case):
    with case.factory() as db:
        issue("admin", case, case.user_ids[0], db)
    update(case, amount_cents=500, coupon_type="fixed", budget_cents=0)
    with case.factory() as db:
        listed = admin.admin_coupons(store_id=None, authorization=case.authorization, db=db)["items"][0]
    assert (listed["committed_cents"], listed["remaining_budget_cents"]) == (500, 0)
    assert count(case) == 1
    with case.factory() as db, pytest.raises(HTTPException):
        issue("claim", case, case.user_ids[1], db)
    update(case, budget_cents=None)
    with case.factory() as db:
        issue("claim", case, case.user_ids[1], db)
    assert count(case) == 2


def test_pending_new_user_grants_and_rewards_remain_idempotent(case):
    with case.factory() as db:
        auth.grant_new_user_coupons(db, case.user_ids[0])
        auth.grant_new_user_coupons(db, case.user_ids[0])
        assert orders._grant_inviter_reward(db, case.user_ids[1]) is False
        db.commit()
    assert count(case) == 1


@pytest.fixture
def pg_case(monkeypatch):
    value = os.getenv("HXY_COUPON_BUDGET_TEST_URL")
    if not value:
        pytest.skip("HXY_COUPON_BUDGET_TEST_URL is required for isolated PostgreSQL tests")
    url = make_url(value)
    if (url.get_backend_name() != "postgresql" or url.host != "127.0.0.1"
            or url.database != "hxy_coupon_budget_guard_test" or url.query):
        pytest.fail("Only the isolated loopback coupon budget test database is allowed")
    monkeypatch.setattr(settings, "coupon_issuance_enabled", True)
    monkeypatch.setattr(orders, "INVITE_REWARD_CODE", coupons.SHARE_COUPON_CODE)
    engine = create_engine(value, connect_args={"options": "-c statement_timeout=15000 -c lock_timeout=12000"})
    # Each test owns a disposable schema inside the synthetic test database.
    import uuid
    schema = "budget_" + uuid.uuid4().hex
    with engine.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = create_engine(value, connect_args={
        "options": f"-c search_path={schema} -c statement_timeout=15000 -c lock_timeout=12000",
    })
    try:
        yield make_case(scoped), scoped
    finally:
        scoped.dispose()
        with engine.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


@pytest.mark.parametrize("second_entry", ["admin", "claim", "share", "new_user", "invite", "update"])
def test_postgres_cross_entry_waits_then_rechecks_budget(pg_case, second_entry):
    case, engine = pg_case
    first_ready, release = threading.Event(), threading.Event()
    pids, results = queue.Queue(), queue.Queue()

    def worker(entry, user_id, first):
        try:
            with case.factory() as db:
                pids.put((first, db.scalar(text("SELECT pg_backend_pid()"))))
                if first:
                    def hold_commit(session):
                        first_ready.set()
                        assert release.wait(10), "Timed out waiting to release first issuer"
                    event.listen(db, "before_commit", hold_commit, once=True)
                try:
                    result = issue(entry, case, user_id, db)
                    results.put((first, "ok", result))
                except HTTPException as error:
                    results.put((first, "http", error.detail))
        except BaseException as error:
            results.put((first, "error", repr(error)))

    first = threading.Thread(target=worker, args=("admin", case.user_ids[0], True), daemon=True)
    second = threading.Thread(target=worker, args=(second_entry, case.user_ids[1], False), daemon=True)
    first.start()
    try:
        assert first_ready.wait(5), "First issuer did not reach commit"
        second.start()
        pid_map = dict([pids.get(timeout=3), pids.get(timeout=3)])
        deadline = time.monotonic() + 5
        blockers = []
        with engine.connect() as observer:
            while time.monotonic() < deadline:
                blockers = observer.scalar(text("SELECT pg_blocking_pids(:pid)"), {"pid": pid_map[False]})
                if pid_map[True] in blockers:
                    break
                time.sleep(0.02)
        assert pid_map[True] in blockers, "Second issuer did not wait for the template lock"
    finally:
        release.set()
        first.join(8)
        if second.ident is not None:
            second.join(8)
    assert not first.is_alive() and not second.is_alive()
    outcomes = {item[0]: item[1:] for item in [results.get(timeout=1), results.get(timeout=1)]}
    assert outcomes[True][0] == "ok", outcomes
    if second_entry in {"admin", "claim", "update"}:
        assert outcomes[False][0] == "http", outcomes
        expected = "COUPON_ISSUED_VALUE_IMMUTABLE" if second_entry == "update" else "COUPON_BUDGET_EXHAUSTED"
        assert outcomes[False][1]["code"] == expected
    else:
        assert outcomes[False][0] == "ok", outcomes
        if second_entry == "share":
            assert outcomes[False][1]["granted"] is False
        elif second_entry == "invite":
            assert outcomes[False][1] is False
    assert count(case) == 1

@pytest.mark.parametrize("entry", ["claim", "share", "admin"])
def test_other_store_template_cannot_be_issued(case, entry):
    with case.factory.begin() as db:
        other = Store(store_code="budget-other", name="Other", address="Synthetic only", status="open")
        db.add(other)
        db.flush()
        db.get(CouponTemplate, case.template_id).store_id = other.id
    with case.factory() as db:
        if entry == "share":
            assert issue(entry, case, case.user_ids[0], db)["granted"] is False
        else:
            with pytest.raises(HTTPException) as error:
                issue(entry, case, case.user_ids[0], db)
            assert error.value.status_code == 404
    assert count(case) == 0


def test_non_manager_cannot_issue(case):
    with case.factory.begin() as db:
        db.get(Staff, case.staff_id).role = "technician"
    case.authorization = f"Bearer {admin.create_staff_token(case.staff_id, 'technician')}"
    with case.factory() as db, pytest.raises(HTTPException) as error:
        issue("admin", case, case.user_ids[0], db)
    assert error.value.status_code == 403
    assert count(case) == 0


@pytest.mark.parametrize("entry", ["claim", "share"])
def test_member_restriction_is_preserved(case, entry):
    with case.factory.begin() as db:
        db.get(User, case.user_ids[0]).is_member = True
    with case.factory() as db:
        if entry == "claim":
            with pytest.raises(HTTPException) as error:
                issue(entry, case, case.user_ids[0], db)
            assert error.value.status_code == 400
        else:
            assert issue(entry, case, case.user_ids[0], db)["granted"] is False
    assert count(case) == 0


def test_percent_and_unissued_value_updates_keep_existing_behavior(case):
    update(case, amount_cents=1000, coupon_type="percent", percent_off=10, budget_cents=0)
    with case.factory() as db:
        issue("claim", case, case.user_ids[0], db)
    assert count(case) == 1


def test_auto_apply_activity_display_is_unchanged(case):
    update(case, auto_apply=True, budget_cents=0)
    authorization = f"Bearer {create_access_token(str(case.user_ids[0]), 'synthetic')}"
    with case.factory() as db:
        activity = coupons.activity_promotion(authorization=authorization, db=db)
    assert activity["total"] == 1
    assert activity["items"][0]["id"] == case.template_id
    assert activity["items"][0]["amount_cents"] == 500
    assert count(case) == 0


def test_exhausted_rewards_do_not_block_http_login_or_order(case, monkeypatch):
    from fastapi.testclient import TestClient
    from app.db.session import get_db
    from app.main import app

    update(case, budget_cents=0)
    monkeypatch.setattr(settings, "wx_appsecret", "")
    with case.factory.begin() as db:
        invitee = User(openid="budget-invitee", inviter_id=case.user_ids[0])
        db.add(invitee)
        db.flush()
        invitee_id = invitee.id

    def database():
        with case.factory() as db:
            yield db

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = database
    try:
        with TestClient(app) as client:
            login = client.post("/api/v1/auth/login", json={"code": "budget-new-login"})
            assert login.status_code == 200, login.text
            authorization = f"Bearer {create_access_token(str(invitee_id), 'synthetic')}"
            order = client.post("/api/v1/orders", headers={"Authorization": authorization}, json={
                "order_type": "service", "store_id": case.store_id, "items": [],
            })
            assert order.status_code == 200, order.text
        assert count(case) == 0
        with case.factory() as db:
            assert db.scalar(select(User.id).where(User.openid == "dev_budget-new-login"))
            assert db.scalar(select(Order.id).where(Order.user_id == invitee_id))
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def wait_for_blocker(engine, blocked, blocker):
    deadline = time.monotonic() + 5
    with engine.connect() as observer:
        while time.monotonic() < deadline:
            if blocker in observer.scalar(text("SELECT pg_blocking_pids(:pid)"), {"pid": blocked}):
                return
            time.sleep(0.02)
    pytest.fail("Expected transaction lock wait was not observed")


@pytest.mark.parametrize("change", [{"budget_cents": 0}, {"amount_cents": 1000}])
def test_postgres_issuance_reloads_template_after_configuration_update(pg_case, change):
    case, engine = pg_case
    pids, results = queue.Queue(), queue.Queue()

    def worker():
        try:
            with case.factory() as db:
                cached = db.get(CouponTemplate, case.template_id)
                assert cached.amount_cents == 500 and cached.budget_cents == 500
                pids.put(db.scalar(text("SELECT pg_backend_pid()")))
                try:
                    issue("claim", case, case.user_ids[0], db)
                    results.put("unexpected issuance")
                except HTTPException as error:
                    results.put(error.detail["code"])
        except BaseException as error:
            results.put(repr(error))

    with case.factory() as updater:
        blocker = updater.scalar(text("SELECT pg_backend_pid()"))
        updater.scalar(select(CouponTemplate).where(CouponTemplate.id == case.template_id).with_for_update())
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            wait_for_blocker(engine, pids.get(timeout=3), blocker)
            admin.admin_update_coupon(
                case.template_id, admin.CouponTemplateUpdate(**change),
                store_id=None, authorization=case.authorization, db=updater,
            )
        finally:
            updater.rollback()
            thread.join(8)
    assert not thread.is_alive()
    assert results.get(timeout=1) == "COUPON_BUDGET_EXHAUSTED"
    assert count(case) == 0


def test_postgres_same_customer_lock_order_does_not_deadlock(pg_case):
    case, engine = pg_case
    pids, results = queue.Queue(), queue.Queue()

    def worker():
        try:
            with case.factory() as db:
                pids.put(db.scalar(text("SELECT pg_backend_pid()")))
                try:
                    issue("admin", case, case.user_ids[0], db)
                    results.put("unexpected issuance")
                except HTTPException as error:
                    results.put(error.detail["code"])
        except BaseException as error:
            results.put(repr(error))

    with case.factory() as claimant:
        blocker = claimant.scalar(text("SELECT pg_backend_pid()"))
        claimant.scalar(select(User.id).where(User.id == case.user_ids[0]).with_for_update())
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            wait_for_blocker(engine, pids.get(timeout=3), blocker)
            issue("claim", case, case.user_ids[0], claimant)
        finally:
            claimant.rollback()
            thread.join(8)
    assert not thread.is_alive()
    assert results.get(timeout=1) == "COUPON_BUDGET_EXHAUSTED"
    assert count(case) == 1

@pytest.mark.parametrize("budget", [0, 500])
def test_postgres_mutual_inviters_can_both_complete_first_http_orders(pg_case, budget):
    from fastapi import Request
    from fastapi.testclient import TestClient
    from app.db.session import get_db
    from app.main import app

    case, engine = pg_case
    with case.factory.begin() as db:
        db.get(CouponTemplate, case.template_id).budget_cents = budget
        buyers = [User(openid=f"mutual-buyer-{i}") for i in range(2)]
        db.add_all(buyers)
        db.flush()
        buyers[0].inviter_id, buyers[1].inviter_id = buyers[1].id, buyers[0].id
        buyer_ids = [buyer.id for buyer in buyers]

    ready, release = threading.Event(), threading.Event()
    pids, results = queue.Queue(), queue.Queue()

    def database(request: Request):
        with case.factory() as db:
            first = request.headers["x-budget-test-actor"] == "first"
            connection = db.connection()
            connection.info["budget_first_order"] = first
            pids.put((first, db.scalar(text("SELECT pg_backend_pid()"))))
            yield db

    def hold_first_insert(connection, cursor, statement, parameters, context, many):
        if connection.info.get("budget_first_order") and statement.lstrip().startswith("INSERT INTO orders "):
            ready.set()
            assert release.wait(10), "Timed out releasing first HTTP order"

    def worker(client, index):
        try:
            response = client.post("/api/v1/orders", headers={
                "Authorization": f"Bearer {create_access_token(str(buyer_ids[index]), 'synthetic')}",
                "x-budget-test-actor": "first" if index == 0 else "second",
            }, json={"store_id": case.store_id, "order_type": "service", "items": []})
            results.put((response.status_code, response.text))
        except BaseException as error:
            results.put(("error", repr(error)))

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = database
    event.listen(engine, "before_cursor_execute", hold_first_insert)
    try:
        with TestClient(app) as client:
            first = threading.Thread(target=worker, args=(client, 0), daemon=True)
            second = threading.Thread(target=worker, args=(client, 1), daemon=True)
            first.start()
            try:
                assert ready.wait(5), "First HTTP order did not reach its INSERT"
                second.start()
                pid_map = dict([pids.get(timeout=3), pids.get(timeout=3)])
                wait_for_blocker(engine, pid_map[False], pid_map[True])
            finally:
                release.set()
                first.join(8)
                if second.ident is not None:
                    second.join(8)
            assert not first.is_alive() and not second.is_alive()
            outcomes = [results.get(timeout=1), results.get(timeout=1)]
            assert [status for status, body in outcomes] == [200, 200], outcomes
        with case.factory() as db:
            assert db.scalar(select(func.count()).select_from(Order).where(
                Order.user_id.in_(buyer_ids), Order.status == "pending_payment",
            )) == 2
            assert db.scalar(select(func.count()).select_from(UserCoupon).where(
                UserCoupon.user_id.in_(buyer_ids),
            )) == (1 if budget == 500 else 0)
    finally:
        event.remove(engine, "before_cursor_execute", hold_first_insert)
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
