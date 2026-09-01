import os
import queue
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.domain.automatic_coupon import mark_automatic_coupon_used, select_automatic_coupon
from app.models import CouponTemplate, Order, Store, User, UserCoupon


PRICING = {
    "store_total_cents": 3990,
    "member_total_cents": 2990,
    "payable_total_cents": 3990,
}


def _isolated_postgres_url() -> str:
    value = os.getenv("HXY_TEST_POSTGRES_URL")
    if not value:
        pytest.skip("HXY_TEST_POSTGRES_URL is required for real PostgreSQL lock verification")
    parsed = make_url(value)
    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.host not in {"127.0.0.1", "localhost"}
        or not (parsed.database or "").startswith("hxy_coupon_concurrency_")
    ):
        pytest.fail(
            "HXY_TEST_POSTGRES_URL must target an isolated local PostgreSQL database "
            "named hxy_coupon_concurrency_*"
        )
    return value


def _wait_for_blocking_pid(engine, blocked_pid: int, blocker_pid: int) -> list[int]:
    deadline = time.monotonic() + 10
    with engine.connect() as observer:
        while time.monotonic() < deadline:
            blocking_pids = list(observer.scalar(
                text("SELECT pg_blocking_pids(:blocked_pid)"),
                {"blocked_pid": blocked_pid},
            ) or [])
            if blocker_pid in blocking_pids:
                return blocking_pids
            time.sleep(0.05)
    return []


def test_concurrent_settlements_lock_and_recheck_the_only_claimed_coupon():
    engine = create_engine(_isolated_postgres_url(), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    schema_tables = [
        User.__table__,
        Store.__table__,
        CouponTemplate.__table__,
        UserCoupon.__table__,
        Order.__table__,
    ]
    Base.metadata.create_all(engine, tables=schema_tables)

    suffix = uuid.uuid4().hex
    with SessionLocal.begin() as setup:
        store = Store(
            store_code=f"coupon-lock-{suffix[:12]}",
            name="自动券并发测试门店",
            address="isolated postgres test",
        )
        customer = User(openid=f"coupon-lock-user-{suffix}")
        template = CouponTemplate(
            code=f"LOCK-{suffix[:20]}",
            name="并发锁测试券",
            coupon_type="fixed",
            amount_cents=500,
            status="published",
        )
        setup.add_all([store, customer, template])
        setup.flush()
        coupon = UserCoupon(
            user_id=customer.id,
            template_id=template.id,
            status="unused",
        )
        first_order = Order(
            order_no=f"LOCK-A-{suffix[:16]}",
            order_type="service",
            user_id=customer.id,
            store_id=store.id,
            items=[],
            total_amount_cents=3990,
            pay_amount_cents=3990,
            status="pending_checkout",
            pay_status="unpaid",
        )
        second_order = Order(
            order_no=f"LOCK-B-{suffix[:16]}",
            order_type="service",
            user_id=customer.id,
            store_id=store.id,
            items=[],
            total_amount_cents=3990,
            pay_amount_cents=3990,
            status="pending_checkout",
            pay_status="unpaid",
        )
        setup.add_all([coupon, first_order, second_order])
        setup.flush()
        customer_id = customer.id
        coupon_id = coupon.id
        first_order_id = first_order.id
        second_order_id = second_order.id

    second_started = threading.Event()
    second_pid_queue: queue.Queue[int] = queue.Queue()
    second_result_queue: queue.Queue[int | None] = queue.Queue()
    second_error_queue: queue.Queue[BaseException] = queue.Queue()

    def second_settlement() -> None:
        with SessionLocal() as transaction:
            try:
                transaction.execute(text("SET LOCAL lock_timeout = '15s'"))
                second_pid_queue.put(transaction.scalar(text("SELECT pg_backend_pid()")))
                second_started.set()
                selection = select_automatic_coupon(
                    transaction,
                    customer_id=customer_id,
                    pricing=PRICING,
                    lock=True,
                )
                if selection.coupon_id is not None:
                    transaction.get(Order, second_order_id).coupon_id = selection.coupon_id
                    mark_automatic_coupon_used(
                        transaction,
                        selection,
                        order_id=second_order_id,
                    )
                transaction.commit()
                second_result_queue.put(selection.coupon_id)
            except BaseException as exc:
                transaction.rollback()
                second_error_queue.put(exc)

    first_transaction = SessionLocal()
    second_thread = threading.Thread(target=second_settlement, daemon=True)
    first_committed = False
    try:
        first_pid = first_transaction.scalar(text("SELECT pg_backend_pid()"))
        first_selection = select_automatic_coupon(
            first_transaction,
            customer_id=customer_id,
            pricing=PRICING,
            lock=True,
        )
        assert first_selection.coupon_id == coupon_id

        second_thread.start()
        assert second_started.wait(timeout=5)
        second_pid = second_pid_queue.get(timeout=5)
        blocking_pids = _wait_for_blocking_pid(engine, second_pid, first_pid)
        assert first_pid in blocking_pids
        assert second_thread.is_alive()
        print(
            f"LOCK_EVIDENCE blocker_pid={first_pid} blocked_pid={second_pid} "
            f"pg_blocking_pids={blocking_pids}"
        )

        first_transaction.get(Order, first_order_id).coupon_id = coupon_id
        mark_automatic_coupon_used(
            first_transaction,
            first_selection,
            order_id=first_order_id,
        )
        first_transaction.commit()
        first_committed = True

        second_thread.join(timeout=10)
        assert not second_thread.is_alive()
        if not second_error_queue.empty():
            raise second_error_queue.get_nowait()
        assert second_result_queue.get_nowait() is None

        with SessionLocal() as verification:
            persisted_coupon = verification.get(UserCoupon, coupon_id)
            associated_orders = list(verification.scalars(
                select(Order).where(Order.coupon_id == coupon_id).order_by(Order.id)
            ))
            assert persisted_coupon.status == "used"
            assert persisted_coupon.used_order_id == first_order_id
            assert [order.id for order in associated_orders] == [first_order_id]
            assert verification.get(Order, second_order_id).coupon_id is None
    finally:
        if not first_committed and first_transaction.in_transaction():
            first_transaction.rollback()
        first_transaction.close()
        if second_thread.is_alive():
            second_thread.join(timeout=20)
        engine.dispose()
